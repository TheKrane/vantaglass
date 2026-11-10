#!/usr/bin/env python3
"""Validate deliverables and the rendered palette, with optional live checks."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tomllib
import configparser
from build import PALETTES, ROOT

def rgb(color):
    return [int(color[i:i+2],16)/255 for i in (1,3,5)]

def luminance(color):
    c = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in color]
    return sum(v*w for v,w in zip(c,[.2126,.7152,.0722]))

def contrast(a,b):
    values = sorted([luminance(a),luminance(b)])
    return (values[1]+.05)/(values[0]+.05)

def validate(live=False):
    report = {'appearances':{}, 'live':{}, 'checks':[]}
    assert set(PALETTES) == {'vantaglass'}, 'Only the dark theme is supported'
    for appearance,p in PALETTES.items():
        folder = ROOT/'themes'/'vantaglass'
        terminal=configparser.ConfigParser(interpolation=None)
        terminal.read(folder/'foot.ini')
        assert terminal['colors-dark']['background']=='000000'
        assert terminal['colors-dark'].getfloat('alpha')==.70
        assert terminal['colors-dark']['alpha-mode']=='matching'
        assert terminal['colors-dark'].getboolean('blur')
        assert not any(key.startswith('font') for key in terminal['main'])
        palette = tomllib.loads((folder/'colors.toml').read_text())
        assert palette['mode'] == 'dark'
        for key,value in p.items(): assert palette[key] == value, ('palette drift',key)
        assert tomllib.loads((folder/'shell.toml').read_text())['font'] == {'base-size':12}
        colors = {k:rgb(palette[k]) for k in ['background','foreground','muted','accent','red','green','yellow','cyan','magenta']}
        ratios = {key:round(contrast(colors[key], colors['background']),2) for key in ['foreground','muted','accent','red','green','yellow','cyan','magenta']}
        assert min(ratios.values()) >= 4.5, (appearance, ratios)
        bar_contrast = None
        secondary_contrast = []
        for file in ['shell.toml']:
            shell = tomllib.loads((folder/file).read_text())
            for surface in ['bar','popups','notifications','tooltip','menu','launcher','polkit','lock']:
                table = shell[surface]
                assert table['background'] == '#000000', (surface,'glass tint is not black')
                if surface in ['menu','launcher','popups']: assert table['background-alpha'] == .70
                alpha = table['background-alpha']
                assert 0 <= alpha <= 1
                if surface=='bar' and alpha==0:
                    # A transparent menu bar has an owned, paired wallpaper.
                    # Check its actual header rather than an opaque surface.
                    import re
                    pixels=subprocess.check_output(['magick',str(folder/'backgrounds/01-misty-forest.jpg'),'-crop','3840x64+0+0','-resize','128x2!','-alpha','off','-depth','8','txt:-'],text=True,timeout=10)
                    samples=re.findall(r'\(\s*(\d+),\s*(\d+),\s*(\d+)\)',pixels)
                    assert len(samples)>=128,'Wallpaper header samples missing'
                    bar_contrast=min(contrast(rgb(table['text']),[int(c)/255 for c in sample]) for sample in samples)
                    assert bar_contrast>=4.5,(appearance,'transparent bar',bar_contrast)
                    continue
                # White and black backgrounds bound every individual RGB component
                # under ordinary alpha compositing. Check both extremes.
                for extreme in [0,1]:
                    background = [v*alpha+extreme*(1-alpha) for v in rgb(table['background'])]
                    ratio = contrast(rgb(table['text']),background)
                    assert ratio >= 4.5, (appearance,file,surface,ratio)
                    if surface in ['menu','popups']:
                        text_alpha=shell['vantaglass']['secondary-text-alpha']
                        secondary=[v*text_alpha+b*(1-text_alpha) for v,b in zip(rgb(table['text']),background)]
                        secondary_ratio=contrast(secondary,background)
                        secondary_contrast.append(secondary_ratio)
                        assert secondary_ratio>=4.5,(appearance,surface,'secondary text',secondary_ratio)
        assert (folder/'backgrounds/01-misty-forest.jpg').stat().st_size > 10000
        report['appearances'][appearance] = {'text_contrast':ratios,'surface_contrast':'panel text passed against black and white compositing extremes','transparent_bar_contrast':round(bar_contrast,2),'glass_secondary_text_minimum_contrast':round(min(secondary_contrast),2)}
    plugin = ROOT/'plugins/vantaglass.style'
    manifest = json.loads((plugin/'manifest.json').read_text())
    assert manifest['kinds'] == ['service'] and 'barWidget' not in manifest['entryPoints']
    for entry in manifest['entryPoints'].values(): assert (plugin/entry).is_file()
    for file in plugin.glob('*.qml'):
        text = file.read_text()
        assert 'http://' not in text and 'https://' not in text
    report['checks'] += ['source palettes and TOML valid','tested palette text roles meet 4.5:1 on the base background','panel foreground contrast on compositing extremes; clear bar on paired wallpaper','dark-only style service has no bar widget']
    if live:
        theme = Path.home()/'.local/state/omarchy/current/theme'
        for file in theme.glob('*'):
            if file.is_file() and file.suffix in ['.toml','.json','.lua','.conf','.ini','.theme']:
                assert '{{' not in file.read_text(), ('unresolved template',file.name)
                if file.suffix=='.json': json.loads(file.read_text())
                if file.suffix=='.toml': tomllib.loads(file.read_text())
        errors = subprocess.check_output(['hyprctl','configerrors'],text=True).strip()
        assert not errors, errors
        subprocess.run(['foot','-C'],check=True,capture_output=True)
        assert subprocess.check_output(['omarchy-shell','shell','ping'],text=True).strip()=='ok'
        import hashlib
        generated = tomllib.loads((theme/'colors.toml').read_text())
        for key,value in PALETTES['vantaglass'].items(): assert generated[key] == value, ('live palette drift',key)
        live_shell = tomllib.loads((theme/'shell.toml').read_text())
        assert live_shell['font'] == {'base-size':12}
        for surface in ['menu','launcher','popups']:
            assert live_shell[surface]['background'] == '#000000' and live_shell[surface]['background-alpha'] == .70
        config = json.loads((Path.home()/'.config/omarchy/shell.json').read_text())
        widgets = [entry.get('id') for entries in config['bar']['layout'].values() for entry in entries]
        assert 'vantaglass.style' not in widgets, 'Style service must not appear in the bar'
        state = Path.home()/'.local/state/vantaglass/preferences.json'
        prefs = json.loads(state.read_text())
        wallpaper = Path.home()/'.local/state/omarchy/current/background'
        assert wallpaper.resolve() == Path(prefs['wallpaper']).resolve(), 'Wallpaper preference was lost'
        family = subprocess.check_output(['omarchy','font','current'],text=True,timeout=3).strip()
        report['live'] = {'font_family':family,'shell_font_base':12,'wallpaper_preference':'preserved','wallpaper_sha256':hashlib.sha256(wallpaper.read_bytes()).hexdigest(),'theme':(theme.parent/'theme.name').read_text().strip(),'hyprland_errors':errors,'foot':'configuration accepted','shell':'responding','plugins':subprocess.check_output(['hyprctl','plugin','list'],text=True).strip()}
    (ROOT/'validation/report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    validate(parser.parse_args().live)
