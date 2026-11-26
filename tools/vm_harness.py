#!/usr/bin/env python3
"""Disposable virtual-GPU Hyprland probe. Never use host compositor sockets."""
import argparse
import fcntl
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import time
import hashlib
import tomllib

def guest_command(output, env, label, *args, timeout=60):
    result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=timeout)
    (output/(label+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(f'{label} failed ({result.returncode}); inspect its guest log')
    return result.stdout

def capture_preview(output, env, config):
    """Capture a four-window desktop using only the disposable guest's files."""
    config.write_text(config.read_text()+'\nhl.monitor({ output = "", mode = "2560x1440@60", position = "0x0", scale = 1 })\n')
    guest_command(output,env,'preview-resolution','hyprctl','reload')
    home=Path.home()
    for name in ['Documents','Downloads','Music','Pictures','Projects','Videos']:
        (home/name).mkdir(exist_ok=True)
    project=home/'Projects/vantaglass'
    from package import entries
    for name,data in entries().items():
        path=project/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    guest_command(output,env,'preview-icon-size','gsettings','set','org.gnome.nautilus.icon-view','default-zoom-level','extra-large')
    btop=home/'.config/btop'
    (btop/'themes').mkdir(parents=True,exist_ok=True)
    shutil.copyfile(home/'.local/state/omarchy/current/theme/btop.theme',btop/'themes/vantaglass.theme')
    (btop/'btop.conf').write_text('color_theme = "vantaglass"\ntheme_background = True\nshown_boxes = "cpu mem net proc"\n')
    foot=['foot','--config',str(home/'.local/state/omarchy/current/theme/foot.ini'),'-o','main.font=JetBrainsMono Nerd Font:size=13']
    commands=[
        ('preview-editor',foot+['--app-id','preview-editor','nvim','-u','NONE','-i','NONE','-n','+set number termguicolors','+syntax on','+highlight Normal guibg=#000000 guifg=#ffffff','+130',str(project/'tools/manage.py')]),
        ('preview-monitor',foot+['--app-id','preview-monitor','btop']),
        ('preview-terminal',foot+['--app-id','preview-terminal','bash','--noprofile','--norc','-c','cd "$HOME/Projects/vantaglass"; ls -lah --color=always; printf "\\n"; exec bash --noprofile --norc']),
        ('org.gnome.Nautilus',['nautilus','--new-window',str(home)]),
    ]
    positions=[(16,48),(1290,48),(16,750),(1290,750)]
    processes=[]
    log=(output/'preview-apps.log').open('w')
    try:
        for (app,args),(x,y) in zip(commands,positions):
            processes.append(subprocess.Popen(args,env=dict(env,GTK_THEME='Adwaita:dark'),stdout=log,stderr=log))
            for _ in range(80):
                clients=json.loads(guest_command(output,env,'preview-clients','hyprctl','-j','clients'))
                client=next((c for c in clients if c['class']==app),None)
                if client:break
                time.sleep(.1)
            else:raise RuntimeError('Preview application did not map: '+app)
            window='"address:'+client['address']+'"'
            for action in ['float({action="on",window='+window+'})',
                           'resize({x=1254,y=670,relative=false,window='+window+'})',
                           'move({x='+str(x)+',y='+str(y)+',relative=false,window='+window+'})']:
                guest_command(output,env,'preview-arrange','hyprctl','dispatch','hl.dsp.window.'+action)
        time.sleep(2)
        guest_command(output,env,'preview-capture','grim',str(output/'preview.png'))
        return {'preview':'preview.png','applications':[app for app,_ in commands]}
    finally:
        for process in processes:
            if process.poll() is None:process.terminate()
        for process in processes:
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()

def add_entertainment_fixture(home):
    apps = home/'.local/share/applications'
    apps.mkdir(parents=True, exist_ok=True)
    program = home/'entertainment-probe.py'
    program.write_text('import time\nprint("Terminal one\\n\\nEntertainment", flush=True)\ntime.sleep(120)\n')
    (apps/'entertainment-probe.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=000 Preview test\nStartupWMClass=entertainment-probe\n'
        'Exec=foot --app-id=entertainment-probe --title="Terminal one" -o colors-dark.background=941d35 '
        f'python {program}\n'
    )
    (apps/'entertainment-second.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=001 Second app\nStartupWMClass=entertainment-second\n'
        'Exec=foot --app-id=entertainment-second --title=Second -o colors-dark.background=145875 sleep 120\n'
    )


def check_entertainment_drag(output, env, cmd, window, window_geometry, wait_for, switch_workspace,
                             regular_workspace, stage, tile, menu_shown, snapshot):
    def emit(*events):
        for event in (*events, (0, 0, 0)):
            device.write(struct.pack('@llHHi', 0, 0, *event))
        time.sleep(.08)

    def center(app):
        (x, y), (width, height) = window_geometry(app)
        return x + width // 2, y + height // 2

    def move_to(x, y):
        current = json.loads(cmd('hyprctl', '-j', 'cursorpos'))
        emit((2, 0, x - current['x']), (2, 1, y - current['y']))

    def drag(source, destination, check_held, button=272):
        move_to(*source)
        emit((1, button, 1))
        try:
            move_to(*destination)
            check_held()
        finally:
            emit((1, button, 0))

    def drag_with_super(button, source, destination, check_held):
        with subprocess.Popen(['wtype', '-M', 'logo', '-s', '900', '-m', 'logo'], env=env):
            time.sleep(.12)
            drag(source, destination, check_held, button)

    def border_resize_enabled():
        return json.loads(cmd('hyprctl', '-j', 'getoption', 'general:resize_on_border'))['bool']

    first, second = 'entertainment-probe', 'entertainment-second'
    with open('/dev/uinput', 'wb', buffering=0) as device:
        # EV_KEY, EV_REL, BTN_LEFT/RIGHT, REL_X/Y on a guest-only libinput mouse.
        for request, codes in [(100, (1, 2)), (101, (272, 273)), (102, (0, 1))]:
            for code in codes:
                fcntl.ioctl(device, 0x40045500 + request, code)
        fcntl.ioctl(device, 0x405c5503, struct.pack('@HHHH80sI', 3, 1, 1, 1, b'Vantaglass Test Mouse', 0))
        fcntl.ioctl(device, 0x5501)
        wait_for(lambda: 'vantaglass-test-mouse' in cmd('hyprctl', 'devices'), 'The guest mouse is available')

        start = [window_geometry(app) for app in (first, second)]
        order = snapshot()['windows']

        def unchanged():
            if snapshot()['windows'] != order or [window_geometry(app) for app in (first, second)] != start:
                raise RuntimeError('Dragging changed the Entertainment layout before an accepted drop')

        if border_resize_enabled():
            raise RuntimeError('Border resize is enabled in Entertainment')
        drag_with_super(272, center(first), (115, 120), unchanged)
        drag_with_super(273, center(first), (115, 120), unchanged)
        drag(center(second), (30, 400), unchanged)
        unchanged()
        if not menu_shown():
            raise RuntimeError('A canceled shelf drag took the stage fullscreen')
        print('Free dragging and canceled drops leave both Entertainment windows in place', flush=True)

        drag(center(second), center(first), unchanged)
        wait_for(lambda: stage(window(second)) and tile(window(first)) and menu_shown(),
                 'A shelf-to-stage drop swaps both live slots and keeps the shelf open')
        if [window_geometry(app) for app in (second, first)] != start or snapshot()['windows'][:2] != order[:2][::-1]:
            raise RuntimeError('The drop did not use the source shelf slot and stage rectangle')
        cmd('grim', str(output/'entertainment-drag-swap.png'))

        time.sleep(.4)
        drag(center(first), center(second), lambda: None)
        wait_for(lambda: stage(window(first)) and tile(window(second)), 'The next drop swaps the windows back')

        switch_workspace(regular_workspace)
        wait_for(border_resize_enabled, 'Omarchy border resizing returns on the regular workspace')
        regular = 'vantaglass-validation'
        drag_with_super(272, center(regular), (130, 180),
                        lambda: wait_for(lambda: window(regular).get('floating'), 'Super+drag still works in regular tiling'))
        wait_for(lambda: not window(regular).get('floating'), 'The regular window returns to tiling on release')
        switch_workspace('name:entertainment')
        wait_for(menu_shown, 'The shelf remains available after leaving and returning')


def check_entertainment(output, env, home, config):
    ipc = ['omarchy-shell', 'vantaglass.entertainment']
    manager = [str(home/'.local/bin/vantaglass'), 'entertainment']

    def cmd(*args):
        return subprocess.check_output(args, env=env, text=True, timeout=8).strip()

    def wait_for(predicate, message):
        for _ in range(90):
            if predicate():
                print(message, flush=True)
                return
            time.sleep(.1)
        if controller_live():
            print(cmd(*ipc, 'status'), cmd(*manager, 'snapshot'), flush=True)
        print(cmd('hyprctl', '-j', 'clients'), flush=True)
        raise RuntimeError(message)

    def controller_live():
        return subprocess.run([*ipc, 'status'], env=env, capture_output=True, timeout=5).returncode == 0

    def workspace():
        return json.loads(cmd('hyprctl', '-j', 'activeworkspace'))['name']

    def shelf_layer():
        layers = json.loads(cmd('hyprctl', '-j', 'layers'))
        return next((layer for monitor in layers.values() for level in monitor['levels'].values() for layer in level
                     if layer['namespace'] == 'vantaglass-entertainment'), None)

    def shelf_mapped():
        return shelf_layer() is not None

    def bar_at_edge():
        monitor = json.loads(cmd('hyprctl', '-j', 'monitors'))[0]
        layers = json.loads(cmd('hyprctl', '-j', 'layers'))[monitor['name']]['levels']
        return monitor['reserved'][1] > 0 and any(
            layer['namespace'] == 'omarchy-bar' and layer['y'] + layer['h'] > 0 and layer['alpha'] > .95
            for level in layers.values() for layer in level)

    def bar_geometry():
        monitor = json.loads(cmd('hyprctl', '-j', 'monitors'))[0]
        layers = json.loads(cmd('hyprctl', '-j', 'layers'))[monitor['name']]['levels']
        bar = next((layer for level in layers.values() for layer in level if layer['namespace'] == 'omarchy-bar'), {})
        return (monitor['reserved'], [bar.get(key) for key in ('x', 'y', 'w', 'h')])

    def bar_slots():
        return json.loads(cmd('omarchy-shell', 'shell', 'debugBarGeometry'))

    def indicator(visible):
        slots = bar_slots()
        icon = next((slot for slot in slots if slot['id'] == 'vantaglass.entertainment'), None)
        if icon is None or icon['visible'] != visible:
            return False
        if not visible:
            return icon['width'] == 0
        workspaces = next((slot for slot in slots if slot['id'] == 'omarchy.workspaces'), None)
        return bool(workspaces and workspaces['visible'] and icon['section'] == workspaces['section']
                    and 0 <= icon['x'] - (workspaces['x'] + workspaces['width']) <= 12)

    def window(app='entertainment-probe'):
        return next((client for client in json.loads(cmd('hyprctl', '-j', 'clients'))
                     if client['class'] == app), {})

    def window_geometry(app):
        client = window(app)
        return client.get('at'), client.get('size')

    def switch_workspace(name):
        cmd('hyprctl', 'dispatch', 'hl.dsp.focus({workspace=' + json.dumps(name) + '})')

    def remote(action):
        cmd(*ipc, 'input', action)

    def menu_shown():
        status = json.loads(cmd(*ipc, 'status'))
        return status['browsing'] and any(shelf['shown'] and shelf['width'] > 0 for shelf in status['shelf'])

    def shelf_contents(app_list, entries):
        status = json.loads(cmd(*ipc, 'status'))
        return any(shelf['shown'] and shelf['appList'] == app_list
                   and shelf['entries'][:len(entries)] == entries
                   and (entries or not shelf['entries']) for shelf in status['shelf'])

    def focus_view(view):
        cmd('hyprctl', 'dispatch', 'hl.dsp.global("vantaglass:entertainment-' + view + '")')

    def snapshot():
        return json.loads(cmd(*manager, 'snapshot'))

    def dimensions():
        monitor = json.loads(cmd('hyprctl', '-j', 'monitors'))[0]
        width, height = monitor['width'], monitor['height']
        return (height, width) if monitor['transform'] % 2 else (width, height)

    def aspect_matches(client):
        width, height = client.get('size', [0, 0])
        display_width, display_height = dimensions()
        return height > 0 and abs(width * display_height - height * display_width) <= max(display_width, display_height)

    def stage(client):
        return client.get('size', [0, 0])[1] > 330 and client.get('fullscreen') == 0 and aspect_matches(client)

    def tile(client):
        return 45 <= client.get('size', [0, 0])[1] <= 116 and aspect_matches(client)

    def fullscreen_stage(app='entertainment-probe'):
        client = window(app)
        if client.get('fullscreen') != 2 or tuple(client['size']) != dimensions():
            return False
        return (json.loads(cmd('hyprctl', '-j', 'activewindow')).get('address') == client['address']
                and not menu_shown() and shelf_mapped())

    regular_app = 'vantaglass-validation'
    regular_workspace = window(regular_app)['workspace']['name']
    switch_workspace(regular_workspace)
    regular_geometry = window_geometry(regular_app)
    switch_workspace('31')
    wait_for(lambda: bar_at_edge() and indicator(False), 'The bar shows and the empty Entertainment indicator takes no space')
    reservation = bar_geometry()
    binds = json.loads(cmd('hyprctl', '-j', 'binds'))
    if not any(bind['description'] == 'Enter or return to Entertainment'
               and bind['key'].upper() == 'E' and bind['modmask'] == 64 for bind in binds):
        raise RuntimeError('Hyprland did not register Super+E for Entertainment')
    for key, target in [('UP', 'stage'), ('DOWN', 'apps')]:
        matches = [bind for bind in binds if bind['key'].upper() == key and bind['modmask'] == 64]
        if len(matches) != 1 or matches[0]['description'] != f'Focus Entertainment {target} or move window focus':
            raise RuntimeError('Hyprland did not register a single Entertainment binding for Super+'+key)
    focus_view('apps')
    if workspace() != '31':
        raise RuntimeError('Entertainment focus shortcut changed an ordinary workspace')
    cmd('hyprctl', 'repl', 'hl.animation({leaf="fadeLayersIn",enabled=true,speed=20,bezier="default"})')
    cmd('hyprctl', 'dispatch', 'hl.dsp.global("vantaglass:entertainment")')
    wait_for(shelf_mapped, 'The Entertainment shelf maps on the workspace switch')
    if shelf_layer()['alpha'] < .99:
        raise RuntimeError('The Entertainment shelf inherited the layer fade on entry')
    wait_for(lambda: workspace() == 'entertainment' and menu_shown() and snapshot()['geometry'].get('shelfWidth', 0) > 0,
             'Super+E enters the dedicated workspace')
    wait_for(lambda: not any(slot['visible'] for slot in bar_slots()) and bar_geometry() == reservation,
             'The bar hides without moving its surface or changing the work area')
    wait_for(lambda: shelf_contents('recent', []), 'The shelf starts on Open & recent')
    cmd('wtype', '-k', 'Down')
    wait_for(lambda: shelf_contents('all', ['entertainment-probe', 'entertainment-second']),
             'Plain Down shows the alphabetical app catalog')
    cmd('wtype', '-k', 'Up')
    wait_for(lambda: shelf_contents('recent', []), 'Plain Up returns to Open & recent')
    remote('down')
    wait_for(lambda: shelf_contents('all', ['entertainment-probe']), 'Controller Down also switches lists')
    remote('select')
    wait_for(fullscreen_stage, 'The first app opens fullscreen and receives input')
    main_address = window()['address']
    remote('right')
    if not fullscreen_stage():
        raise RuntimeError('Controller navigation interrupts the stage app')
    cmd('grim', str(output/'entertainment-fullscreen.png'))
    focus_view('apps')
    wait_for(lambda: menu_shown() and stage(window()), 'Super+Down restores the shelf and windowed stage')
    remote('down')
    wait_for(lambda: shelf_contents('recent', []), 'The stage app is omitted from the recent shelf')
    second = subprocess.Popen(['foot', '--app-id=entertainment-second', '--title=Second', '-o',
                               'colors-dark.background=145875', 'sleep', '120'], env=env)
    try:
        wait_for(lambda: tile(window('entertainment-second')) and stage(window()),
                 'The stage and the real shelf window match the display’s aspect ratio')
        second_address = window('entertainment-second')['address']
        wait_for(lambda: shelf_contents('recent', [second_address]), 'Open windows are listed before recent apps')
        original_config = config.read_text()
        config.write_text(original_config + '\nhl.monitor({ output = "Virtual-1", mode = "1280x720@60", position = "0x0", scale = 1 })\n')
        try:
            cmd('hyprctl', 'reload')
            wait_for(lambda: dimensions() == (1280, 720) and stage(window()) and tile(window('entertainment-second')),
                'Stage and shelf follow the monitor’s new aspect ratio')
        finally:
            config.write_text(original_config)
            cmd('hyprctl', 'reload')
        wait_for(lambda: dimensions() == (1280, 800) and stage(window()) and tile(window('entertainment-second')),
                 'Stage and shelf return to the original display ratio')
        check_entertainment_drag(output, env, cmd, window, window_geometry, wait_for, switch_workspace,
                                 regular_workspace, stage, tile, menu_shown, snapshot)
        cmd('grim', str(output/'entertainment-live-windows.png'))
        focus_view('stage')
        wait_for(fullscreen_stage, 'Super+Up takes the current stage window fullscreen')
        fullscreen_geometry = window_geometry('entertainment-probe')
        switch_workspace(regular_workspace)
        wait_for(lambda: workspace() == regular_workspace and bar_at_edge() and not shelf_mapped(),
                 'A native workspace switch leaves Entertainment and restores the bar')
        if window_geometry(regular_app) != regular_geometry or bar_geometry() != reservation:
            raise RuntimeError('The regular tiled window or work area changed on leaving Entertainment')
        cmd(*ipc, 'openDashboard')
        wait_for(lambda: workspace() == 'entertainment' and window().get('fullscreen') == 2 and not shelf_mapped(),
                 'The controller indicator returns to the fullscreen window in place')
        if window_geometry('entertainment-probe') != fullscreen_geometry or bar_geometry() != reservation:
            raise RuntimeError('The fullscreen window or work area changed on re-entering Entertainment')
        remote('home')
        wait_for(lambda: menu_shown() and stage(window()), 'Home returns from fullscreen to Apps')
        remote('home')
        wait_for(fullscreen_stage, 'Home toggles back to fullscreen without leaving the workspace')
        remote('home')
        wait_for(lambda: menu_shown() and stage(window()), 'Home returns to the same shelf selection')
        cmd(*manager, 'fullscreen')
        if window().get('fullscreen') != 2:
            raise RuntimeError('The fullscreen request deferred the native mode switch')
        focus_view('apps')
        wait_for(lambda: menu_shown() and stage(window()), 'Quickly changing direction restores the shelf')
        cmd('hyprctl', 'repl', 'hl.config({animations={enabled=false}})')
        try:
            cmd(*manager, 'fullscreen')
            if window().get('fullscreen') != 2:
                raise RuntimeError('Fullscreen was deferred with animations disabled')
            cmd(*manager, 'restore')
        finally:
            cmd('hyprctl', 'reload')
        wait_for(lambda: menu_shown() and stage(window()) and tile(window('entertainment-second')),
                 'Disabling animations allows an immediate fullscreen round trip')
        remote('down')
        wait_for(lambda: shelf_contents('all', [second_address]), 'The catalog keeps live windows in their slots')
        remote('nextPage')
        wait_for(lambda: snapshot()['offset'] > 0 and window('entertainment-second')['at'][0] > 1280,
                 'Moving to another shelf page parks the off-page window outside the output')
        shelf_offset = snapshot()['offset']
        window_positions = [window_geometry(app) for app in ('entertainment-probe', 'entertainment-second')]
        switch_workspace('31')
        wait_for(lambda: workspace() == '31' and bar_at_edge() and not shelf_mapped(),
                 'The regular workspace switch leaves the shelf layout in place')
        switch_workspace('name:entertainment')
        wait_for(lambda: menu_shown() and snapshot()['offset'] == shelf_offset, 'Returning to Entertainment keeps the open shelf page')
        if [window_geometry(app) for app in ('entertainment-probe', 'entertainment-second')] != window_positions:
            raise RuntimeError('Switching workspaces retiled the Entertainment windows')
        remote('up')
        wait_for(lambda: snapshot()['offset'] == 0 and window('entertainment-second')['at'][0] == snapshot()['geometry']['tileX'],
                 'Changing lists returns to page one and restores the live window')
        remote('select')
        wait_for(lambda: fullscreen_stage('entertainment-second'),
                 'Selecting a running app swaps it onto the stage and takes it fullscreen')
        if snapshot()['windows'][:2] != [window('entertainment-second')['address'], main_address]:
            raise RuntimeError('The previous stage window did not take the selected shelf slot')
        focus_view('apps')
        wait_for(lambda: stage(window('entertainment-second')) and tile(window()) and menu_shown(),
                 'Super+Down returns directly from fullscreen to the same shelf')
        cmd('grim', str(output/'entertainment-swapped.png'))
        remote('close')
        remote('select')
        wait_for(lambda: not window() and stage(window('entertainment-second')),
                 'Closing a shelf window leaves the main window in place')
        wait_for(lambda: shelf_contents('recent', ['entertainment-probe']), 'Closed stage apps appear in recents')
        remote('exit')
        wait_for(lambda: workspace() == '31' and not shelf_mapped(), 'Leaving Entertainment restores the previous workspace')
        (output/'entertainment-bar-slots.json').write_text(json.dumps(bar_slots(), indent=2)+'\n')
        wait_for(lambda: bar_at_edge() and indicator(True), 'An open Entertainment window adds a controller beside the workspace numbers')
        icon = next(slot for slot in bar_slots() if slot['id'] == 'vantaglass.entertainment')
        image = output/'entertainment-workspace-indicator.png'
        # The layer can report its new position before Wayland presents the bar.
        time.sleep(.4)
        cmd('grim', str(image))
        region = f'{icon["width"]}x{icon["height"]}+{icon["x"]}+{icon["y"]}'
        coverage = cmd('magick', str(image), '-crop', region, '+repage', '-colorspace', 'gray',
                       '-threshold', '55%', '-format', '%[fx:mean]', 'info:')
        if float(coverage) < .005:
            raise RuntimeError('The controller slot did not render a visible glyph')
        cmd(*ipc, 'openDashboard')
        wait_for(lambda: workspace() == 'entertainment' and menu_shown() and stage(window('entertainment-second')),
                 'Opening Entertainment from the bar returns to the same live window')
        cmd(*manager, 'close', second_address)
        expected_order = ['entertainment-second', 'entertainment-probe']
        wait_for(lambda: shelf_contents('recent', expected_order), 'Closed apps appear most recently used first')
        history = home/'.local/state/vantaglass/entertainment-recents.json'
        if json.loads(history.read_text())[:2] != expected_order:
            raise RuntimeError('Recent apps were not saved in usage order')
        guest_command(output, env, 'entertainment-shell-restart', 'omarchy', 'restart', 'shell')
        wait_for(lambda: controller_live() and shelf_contents('recent', expected_order),
                 'Open & recent restores its order after restarting the shell')
        cmd('hyprctl', 'dispatch', 'hl.dsp.focus({workspace="1"})')
        wait_for(lambda: not shelf_mapped() and bar_at_edge() and indicator(False),
                 'Closing the last Entertainment window removes the controller')
    finally:
        if second.poll() is None:
            second.terminate()
        second.wait(timeout=5)
    return True


def installer_flow(output, env, config, baseline, preview=False):
    """Run real commands against the guest compositor and shell, without mocks."""
    home=Path.home()
    env=dict(env,PATH=str(home/'.local/bin')+':/usr/bin:/bin',OMARCHY_PATH='/usr/share/omarchy',QT_QPA_PLATFORM='wayland',QT_QUICK_BACKEND='software',QT_FORCE_STDERR_LOGGING='1',OMARCHY_SHELL_IPC_TIMEOUT='5s',QS_DISABLE_FILE_WATCHER='1',QS_NO_RELOAD_POPUP='1')
    displays=[p for p in Path(env['XDG_RUNTIME_DIR']).glob('wayland-*') if p.is_socket()]
    if len(displays)!=1:raise RuntimeError('Guest Wayland display is not unique')
    env['WAYLAND_DISPLAY']=displays[0].name
    guest_command(output,env,'activation-environment','dbus-update-activation-environment','WAYLAND_DISPLAY','HYPRLAND_INSTANCE_SIGNATURE','XDG_CURRENT_DESKTOP','QT_QPA_PLATFORM')
    # The guest has no systemd PID 1. Adapt only journal transport; the stock
    # restart helper, supervised launcher and Quickshell still run unmodified.
    (output/'restarted-shell.log').write_text('')
    journal_adapter=home/'.local/bin/systemd-cat';journal_adapter.parent.mkdir(parents=True,exist_ok=True)
    journal_adapter.write_text('#!/bin/bash\nwhile (( $# )) && [[ $1 != -- ]]; do shift; done\n[[ ${1:-} != -- ]] || shift\nexec "$@" >> /output/restarted-shell.log 2>&1\n')
    journal_adapter.chmod(0o755)
    settings=home/'.config/omarchy';settings.mkdir(parents=True,exist_ok=True)
    original=settings/'themes/vm-original';original.mkdir(parents=True)
    shutil.copyfile('/usr/share/omarchy/themes/tokyo-night/colors.toml',original/'colors.toml')
    (original/'hyprland.lua').write_text('hl.config({ decoration = { rounding = 0, blur = { enabled = false } } })\n')
    (original/'backgrounds').mkdir()
    shutil.copyfile(ROOT/'themes/vantaglass/backgrounds/01-misty-forest.jpg',original/'backgrounds/preserved-original.jpg')
    guest_command(output,dict(env,OMARCHY_THEME_HEADLESS='1'),'original-generation','omarchy','theme','set','vm-original')
    theme_loader='local path = os.getenv("HOME") .. "/.local/state/omarchy/current/theme/hyprland.lua"; local f = io.open(path); if f then f:close(); dofile(path) end\n'
    config.write_text(baseline+theme_loader)
    guest_command(output,env,'original-reload','hyprctl','reload')
    essential={'omarchy.bar','omarchy.background','omarchy.menu','omarchy.clock','omarchy.notifications','omarchy.workspaces'}
    ids=set()
    for manifest in Path('/usr/share/omarchy/shell/plugins').rglob('*manifest.json'):
        data=json.loads(manifest.read_text())
        if data.get('id'):ids.add(data['id'])
    shell_config={'version':1,'disabledPlugins':sorted(ids-essential),'idle':{'lock':0,'screensaver':0},'bar':{'background':'opaque','position':'top','layout':{'left':[{'id':'omarchy.menu'},{'id':'omarchy.workspaces'}],'center':[{'id':'omarchy.clock'}],'right':[],'centerBegin':[],'centerEnd':[],'tray':[]}}}
    shell_file=settings/'shell.json';shell_file.write_text(json.dumps(shell_config))
    shell_log=(output/'shell.log').open('w')
    if not preview:
        add_entertainment_fixture(home)
    shell=subprocess.Popen(['quickshell','--no-color','--path','/usr/share/omarchy/shell'],env=env,stdout=shell_log,stderr=shell_log)
    terminal=None
    terminal_log=None
    try:
        for _ in range(40):
            if shell.poll() is not None:
                health=subprocess.run(['hyprctl','version'],env=env,capture_output=True,text=True,timeout=3)
                print('Compositor health after shell exit:',health.returncode,health.stdout,health.stderr,flush=True)
                raise RuntimeError('Guest shell exited with '+str(shell.returncode)+'; inspect shell.log')
            reply=subprocess.run(['omarchy-shell','shell','ping'],env=env,capture_output=True,text=True,timeout=3)
            if reply.returncode==0 and reply.stdout.strip()=='ok':break
            time.sleep(.2)
        else:raise RuntimeError('Guest shell did not answer IPC')
        original_wallpaper=home/'.local/state/omarchy/current/theme/backgrounds/preserved-original.jpg'
        expected_wallpaper_hash=hashlib.sha256(original_wallpaper.read_bytes()).hexdigest()
        guest_command(output,env,'original-wallpaper','omarchy','theme','bg','set',str(original_wallpaper))
        manager=['python',str(ROOT/'tools/manage.py')]
        guest_command(output,env,'install',*manager,'install')
        manager=[str(home/'.local/bin/vantaglass')]
        state=home/'.local/state/vantaglass'
        manifest=json.loads((state/'installation.json').read_text())
        if manifest['previous_theme']!='vm-original' or not Path(manifest['backup']).is_file():raise RuntimeError('Original guest snapshot is missing')
        expected_layout=json.loads(json.dumps(shell_config['bar']['layout']))
        expected_layout['left'][0]['id']='vantaglass.menu'
        expected_layout['left'].append({'id':'vantaglass.entertainment'})
        expected_layout['center'][0]['id']='vantaglass.clock'
        if json.loads(shell_file.read_text())['bar']['layout']!=shell_config['bar']['layout']:raise RuntimeError('Inactive installation changed the original layout')
        guest_command(output,env,'reinstall',*manager,'install')
        if json.loads((state/'installation.json').read_text())!=manifest:raise RuntimeError('Reinstall replaced the original snapshot')
        if preview:
            guest_command(output,env,'preview-switch',*manager,'switch')
            return capture_preview(output,env,config)
        results=[]
        for theme in ['vantaglass']:
            tag=theme
            guest_command(output,env,tag+'-switch',*manager,'switch')
            active=(home/'.local/state/omarchy/current/theme.name').read_text().strip()
            if active!='vantaglass':raise RuntimeError('Guest active theme is incorrect')
            wallpaper=home/'.local/state/omarchy/current/background'
            if hashlib.sha256(wallpaper.read_bytes()).hexdigest()!=expected_wallpaper_hash:raise RuntimeError('Theme switch lost the original wallpaper')
            if wallpaper.resolve().is_relative_to(home/'.local/state/omarchy/current/theme'):raise RuntimeError('Wallpaper still depends on the transient generated theme')
            geometry=json.loads(guest_command(output,env,tag+'-rounding','hyprctl','-j','getoption','decoration:rounding'))
            if geometry['int']!=18:raise RuntimeError('Installed theme geometry did not apply')
            generated=home/'.local/state/omarchy/current/theme'
            palette=tomllib.loads((generated/'colors.toml').read_text())
            policy=json.loads(Path('/etc/chromium/policies/managed/color.json').read_text())
            browser_source=(generated/'chromium.theme').read_text().strip()
            (output/(tag+'-browser-policy.json')).write_text(json.dumps({'policy':policy,'source':browser_source},indent=2)+'\n')
            expected_browser=palette['background']
            if policy['BrowserThemeColor'].lower()!=expected_browser.lower():raise RuntimeError('Guest browser policy did not receive the theme')
            if terminal is None:
                terminal_log=(output/'terminal.log').open('w')
                program='import time; print("\\033[97m████████\\033[0m\\n\\033[48;2;0;0;0m"+" "*80+"\\033[0m\\n\\033[1mOmarchy\\033[0m\\nA clear view of your work.\\n\\n\\033[32m✓\\033[0m Theme verification\\n\\033[34m●\\033[0m Native desktop controls\\n\\033[33m●\\033[0m Keyboard workflows preserved",flush=True); time.sleep(300)'
                terminal=subprocess.Popen(['foot','--config',str(generated/'foot.ini'),'--app-id','vantaglass-validation','--title','Omarchy · Theme verification','python','-c',program],env=env,stdout=terminal_log,stderr=terminal_log)
            for _ in range(30):
                if terminal.poll() is not None:raise RuntimeError('Guest terminal exited; inspect terminal.log')
                clients=json.loads(guest_command(output,env,tag+'-clients','hyprctl','-j','clients'))
                window=next((c for c in clients if c.get('class')=='vantaglass-validation'),None)
                if window:break
                time.sleep(.1)
            else:raise RuntimeError('Guest terminal did not map')
            address='address:'+window['address']
            # Terminal rules must survive a user's different global geometry.
            guest_command(output,env,'personal-rounding','hyprctl','repl','hl.config({decoration={rounding=10}})')
            rounding=guest_command(output,env,'terminal-rounding','hyprctl','getprop',address,'rounding').strip()
            if rounding!='18':raise RuntimeError('Terminal did not retain theme-local rounding: '+rounding)
            guest_command(output,env,'restore-rounding','hyprctl','repl','hl.config({decoration={rounding=18}})')
            border=guest_command(output,env,'terminal-border','hyprctl','getprop',address,'active_border_color')
            angle=re.search(r'(\d+)deg',border)
            if not angle or abs(int(angle[1])-110)>3 or len(border.split())!=3:
                raise RuntimeError('Terminal edge gradient did not apply: '+border)
            # A white backdrop makes 70% black measurable independently of the
            # bundled photograph; the first line also verifies opaque glyphs.
            backdrop=home/'white.png'
            preserved_wallpaper=str(wallpaper.resolve())
            guest_command(output,env,'white-backdrop','magick','-size','1280x800','xc:white',str(backdrop))
            guest_command(output,env,'test-backdrop','omarchy','theme','bg','set',str(backdrop))
            time.sleep(.7)
            app_image=output/(tag+'-application.png')
            x=window['at'][0]+window['size'][0]-30;y=window['at'][1]+window['size'][1]-30
            expression=','.join(f'%[fx:round(255*p{{{x},{y}}}.{channel})]' for channel in ['r','g','b'])
            expected=palette['background'].lstrip('#')
            expected_rgb=[77,77,77]
            for _ in range(12):
                guest_command(output,env,tag+'-application-capture','grim','-o','Virtual-1',str(app_image))
                sample=guest_command(output,env,tag+'-application-color','magick',str(app_image),'-format',expression,'info:').strip()
                actual_rgb=[int(value) for value in sample.split(',')]
                if all(abs(a-b)<=3 for a,b in zip(actual_rgb,expected_rgb)):break
                time.sleep(.2)
            else:raise RuntimeError('Live terminal background did not match theme: '+sample+' vs '+expected)
            pixels=guest_command(output,env,'terminal-glyphs','magick',str(app_image),'-crop',f'160x50+{window["at"][0]+18}+{window["at"][1]+18}','-format','%[fx:maxima]','info:')
            if float(pixels)<.999:raise RuntimeError('Terminal text was faded with its background')
            explicit=guest_command(output,env,'terminal-explicit-black','magick',str(app_image),'-format',f'%[fx:round(255*p{{{window["at"][0]+80},{window["at"][1]+40}}}.r)]','info:')
            if abs(int(explicit)-77)>3:raise RuntimeError('Explicit black cells lost transparency: '+explicit)
            guest_command(output,env,'restore-backdrop','omarchy','theme','bg','set',preserved_wallpaper)
            guest_command(output,env,tag+'-menu-ipc','omarchy-shell','shell','summon','omarchy.menu','{"menu":"root"}')
            time.sleep(.7)
            guest_command(output,env,tag+'-menu-capture','grim','-o','Virtual-1',str(output/(tag+'-menu.png')))
            guest_command(output,env,tag+'-menu-hide','omarchy-shell','shell','hide','omarchy.menu')
            guest_command(output,env,tag+'-notification','notify-send','-a','Omarchy','-t','800','Vantaglass','A clear view of your work.')
            time.sleep(.3)
            guest_command(output,env,tag+'-notification-capture','grim','-o','Virtual-1',str(output/(tag+'-notification.png')))
            results.append({'theme':theme,'active_theme':active,'rounding':geometry['int'],'live_terminal_background':actual_rgb,'expected_terminal_background':expected_rgb,'terminal_text':'opaque','explicit_black_cells':'translucent','terminal_rounding':int(rounding),'terminal_edge':border.strip(),'browser_policy_color':policy['BrowserThemeColor'],'shell_renderer':'software'})
            print('Verified real guest switch: '+tag,flush=True)
        # Fixture transport only: real post-update hook, downloader validation,
        # installer, operation locks and shell refresh all run unchanged.
        update_fixtures=home/'update-fixtures';update_fixtures.mkdir()
        update_bin=home/'update-bin';update_bin.mkdir()
        fake_curl=update_bin/'curl'
        fake_curl.write_text('#!/usr/bin/python\nimport os,pathlib,sys,shutil\nargs=sys.argv[1:]\nfolder=pathlib.Path(os.environ["VANTAGLASS_UPDATE_FIXTURES"])\nif (folder/"offline").exists():sys.exit(22)\nurl=next(a for a in args if a.startswith("https://"))\nname="release.json" if url.endswith("/releases/latest") else url.rsplit("/",1)[-1]\nshutil.copyfile(folder/name,args[args.index("--output")+1])\n')
        fake_curl.chmod(0o755)
        (update_fixtures/'release.json').write_text(json.dumps({'tag_name':'v'+(ROOT/'VERSION').read_text().strip(),'draft':False,'prerelease':False}))
        hook_env=dict(env,PATH=str(update_bin)+':'+env['PATH'],VANTAGLASS_UPDATE_FIXTURES=str(update_fixtures))
        # Ordinary Omarchy commands, not our switch command, drive the overlay.
        for iteration in range(2):
            guest_command(output,dict(env,OMARCHY_THEME_WAIT='1'),'native-away-'+str(iteration),'omarchy','theme','set','vm-original')
            if guest_command(output,env,'native-terminal-rounding','hyprctl','getprop',address,'rounding').strip()!='0':
                raise RuntimeError('Terminal rules remained after switching away')
            if 'alpha=0.70' in (home/'.local/state/omarchy/current/theme/foot.ini').read_text():
                raise RuntimeError('Terminal glass remained in the other theme')
            if json.loads(shell_file.read_text())['bar']['layout']!=shell_config['bar']['layout']:raise RuntimeError('Ordinary switch-away retained custom widgets')
            guest_command(output,dict(env,OMARCHY_THEME_WAIT='1'),'native-back-'+str(iteration),'omarchy','theme','set','vantaglass')
            if json.loads(shell_file.read_text())['bar']['layout']!=expected_layout:raise RuntimeError('Ordinary switch-back did not restore custom widgets')
        guest_command(output,env,'post-boot-hook','omarchy','hook','post-boot')
        if json.loads(shell_file.read_text())['bar']['layout']!=expected_layout:raise RuntimeError('Post-boot hook duplicated or removed widgets')
        # Simulate an upstream API change in a private source tree, without
        # touching /usr/share/omarchy or the physical desktop.
        private_upstream=home/'upstream-fixture'
        for rel in json.loads((ROOT/'compatibility.json').read_text())['files']:
            target=private_upstream/rel;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(Path('/usr/share/omarchy')/rel,target)
        changed=private_upstream/'shell/Ui/Button.qml';changed.write_text(changed.read_text()+'\n// simulated new upstream interface\n')
        guest_command(output,dict(hook_env,OMARCHY_PATH=str(private_upstream)),'post-update-fallback','omarchy','hook','post-update')
        if json.loads(shell_file.read_text())['bar']['layout']!=shell_config['bar']['layout']:raise RuntimeError('Updated interface did not fall back to native widgets')
        if guest_command(output,env,'fallback-shell-health','omarchy-shell','shell','ping').strip()!='ok':raise RuntimeError('Fallback shell is not responsive')
        guest_command(output,hook_env,'post-update-compatible','omarchy','hook','post-update')
        if json.loads(shell_file.read_text())['bar']['layout']!=expected_layout:raise RuntimeError('Compatible interface did not reactivate widgets')
        import importlib.util
        import tarfile
        package_spec=importlib.util.spec_from_file_location('fixture_package',ROOT/'tools/package.py')
        fixture_package=importlib.util.module_from_spec(package_spec);package_spec.loader.exec_module(fixture_package)
        candidate_source=home/'candidate-source'
        with tarfile.open(ROOT/'dist'/('vantaglass-'+(ROOT/'VERSION').read_text().strip()+'.tar.gz')) as archive:
            archive.extractall(candidate_source,filter='data')
        candidate_source=candidate_source/'vantaglass'
        fixture_package.ROOT=candidate_source
        release_parts=[int(n) for n in (ROOT/'VERSION').read_text().strip().split('.')]
        release_parts += [0]*(3-len(release_parts))
        future_versions=['.'.join(str(n) for n in [*release_parts[:2],release_parts[2]+offset]) for offset in (1,2)]
        for target_version,other_theme in zip(future_versions,(False,True)):
            if other_theme:
                guest_command(output,dict(env,OMARCHY_THEME_WAIT='1'),'update-away','omarchy','theme','set','vm-original')
            before_background=str((home/'.local/state/omarchy/current/background').resolve())
            before_receipt=json.loads((state/'installation.json').read_text())
            (candidate_source/'VERSION').write_text(target_version+'\n')
            service=candidate_source/'plugins/vantaglass.style/Service.qml'
            service.write_text(service.read_text()+'\n// update fixture '+target_version+'\n')
            fixture_package.package(update_fixtures/('vantaglass-'+target_version+'.tar.gz'))
            (update_fixtures/'release.json').write_text(json.dumps({'tag_name':'v'+target_version,'draft':False,'prerelease':False}))
            guest_command(output,hook_env,'auto-update-'+target_version,'omarchy','hook','post-update',timeout=150)
            if (home/'.local/share/vantaglass/runtime/VERSION').read_text().strip()!=target_version:raise RuntimeError('Automatic update did not install new release')
            expected_theme='vm-original' if other_theme else 'vantaglass'
            if (home/'.local/state/omarchy/current/theme.name').read_text().strip()!=expected_theme:raise RuntimeError('Automatic update changed the selected theme')
            if str((home/'.local/state/omarchy/current/background').resolve())!=before_background:raise RuntimeError('Automatic update changed selected wallpaper')
            if json.loads((state/'installation.json').read_text())!=before_receipt:raise RuntimeError('Automatic update changed original receipt')
            if json.loads(shell_file.read_text())['bar']['layout']!=(shell_config['bar']['layout'] if other_theme else expected_layout):raise RuntimeError('Automatic update changed widget layout')
        (update_fixtures/'offline').touch()
        guest_command(output,hook_env,'offline-update-hook','bash',str(settings/'hooks/post-update.d/vantaglass-update'))
        if (home/'.local/share/vantaglass/runtime/VERSION').read_text().strip()!=future_versions[-1]:raise RuntimeError('Offline hook changed installation')
        (update_fixtures/'offline').unlink()
        guest_command(output,dict(env,OMARCHY_THEME_WAIT='1'),'update-back','omarchy','theme','set','vantaglass')
        print('Verified automatic release upgrades, other-theme preservation and offline hook continuation',flush=True)
        entertainment_checked = check_entertainment(output, env, home, config)
        later=json.loads(shell_file.read_text());later['idle']['lock']=900;later['bar']['layout']['left'].append({'id':'omarchy.spacer','width':11});shell_file.write_text(json.dumps(later))
        config.write_text(config.read_text()+'-- Later guest user edit\n')
        guest_command(output,env,'restore',*manager,'restore')
        if (home/'.local/state/omarchy/current/theme.name').read_text().strip()!='vm-original':raise RuntimeError('Restore did not select original theme')
        if '-- Later guest user edit' not in config.read_text() or json.loads(shell_file.read_text())['idle']['lock']!=900:raise RuntimeError('Restore lost later user edits')
        if json.loads(shell_file.read_text())['bar']['background']!='opaque':raise RuntimeError('Restore did not recover original bar background')
        expected_restored=json.loads(json.dumps(shell_config['bar']['layout']))
        expected_restored['left'].append({'id':'omarchy.spacer','width':11})
        if json.loads(shell_file.read_text())['bar']['layout']!=expected_restored:raise RuntimeError('Restore changed the original layout or a later widget edit')
        guest_command(output,env,'uninstall',*manager,'uninstall')
        if (state/'entertainment.json').exists(): raise RuntimeError('Uninstall retained active entertainment workspace settings')
        if (state/'entertainment-recents.json').exists(): raise RuntimeError('Uninstall retained active entertainment recents')
        layers = json.loads(guest_command(output,env,'final-layers','hyprctl','-j','layers'))
        if 'vantaglass-entertainment' in json.dumps(layers): raise RuntimeError('Uninstall left an entertainment layer')
        for path in [state/'installation.json',state/'preferences.json',state/'original-shell.json',*settings.glob('plugins/vantaglass.*'),home/'.local/share/vantaglass/runtime',home/'.local/bin/vantaglass']:
            if path.exists():raise RuntimeError('Uninstall retained an active owned file: '+str(path))
        if guest_command(output,env,'final-configerrors','hyprctl','configerrors').strip():raise RuntimeError('Final compositor configuration has errors')
        shell_log.flush()
        journal=subprocess.run(['journalctl','-t','omarchy-shell','--no-pager','-o','cat'],capture_output=True,text=True,timeout=10)
        (output/'journal-readback.log').write_text(journal.stdout+journal.stderr)
        supervised=(output/'restarted-shell.log').read_text() if (output/'restarted-shell.log').exists() else ''
        log=(output/'shell.log').read_text()+supervised
        for marker in ['TypeError','ReferenceError','Binding loop','service plugin load failed','ShaderEffect: Failed']:
            if marker in log:raise RuntimeError('Guest shell integration error: '+marker)
        print('Verified real guest install, reinstall, restore and uninstall',flush=True)
        return {'switches':results,'original_backup_retained':Path(manifest['backup']).is_file(),'later_edits_preserved':True,'restore':True,'uninstall':True,'ordinary_theme_switch_roundtrips':2,'post_boot_hook':True,'post_update_fallback':True,'automatic_release_updates':2,'update_preserved_other_theme':True,'offline_hook_continued':True,'entertainment':entertainment_checked,'command_boundary':'actual Omarchy, Quickshell and Hyprland; no command mocks'}
    finally:
        for process in [terminal,shell]:
            if process is not None and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        shell_log.close()
        if terminal_log is not None:terminal_log.close()

ROOT=Path(__file__).resolve().parents[1]

def copy_binary(root, path, destination=None):
    target=root/(destination or path.lstrip('/'))
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,target)
    target.chmod(0o755)
    linked=subprocess.check_output(['ldd',path],text=True,timeout=5)
    for library in re.findall(r'(/[^\s()]+)',linked):
        dest=root/library.lstrip('/')
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(library,dest)
        dest.chmod(0o755)

def initramfs(root,kernel):
    for name in ['usr/bin','usr/lib','dev','proc','sys','run','tmp','etc','project','output','home/tester','var/log']:
        (root/name).mkdir(parents=True,exist_ok=True)
    for name in ['bin','sbin']:(root/name).symlink_to('usr/bin')
    (root/'lib').symlink_to('usr/lib')
    (root/'lib64').symlink_to('usr/lib')
    (root/'usr/lib64').symlink_to('lib')
    copy_binary(root,'/usr/lib/initcpio/busybox','usr/bin/sh')
    for binary in ['/usr/bin/mount','/usr/bin/modprobe']:copy_binary(root,binary)
    modules=root/'usr/lib/modules'/kernel.name
    modules.mkdir(parents=True)
    for file in kernel.glob('modules.*'):
        if file.is_file():shutil.copyfile(file,modules/file.name)
    for module in ['virtio_pci','9pnet_virtio','9p','virtio_gpu']:
        dependencies=subprocess.check_output(['modprobe','--show-depends','-S',kernel.name,module],text=True,timeout=5)
        for line in dependencies.splitlines():
            if not line.startswith('insmod '):continue
            source=Path(line.split()[1])
            target=root/'usr/lib/modules'/kernel.name/source.relative_to('/lib/modules'/Path(kernel.name))
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
    (root/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/sh\ntester:x:1000:1000:Tester:/home/tester:/bin/sh\n')
    (root/'etc/group').write_text('root:x:0:\nusers:x:1000:tester\nvideo:x:986:tester\nrender:x:989:tester\n')
    (root/'etc/nsswitch.conf').write_text('passwd: files\ngroup: files\nhosts: files\n')
    (root/'etc/machine-id').write_text('00000000000000000000000000000001\n')
    # Guest-only grant for the packaged, color-validated browser-policy writer.
    # This file exists solely in the temporary initramfs, never on the host.
    (root/'etc/sudoers').write_text('root ALL=(ALL:ALL) ALL\ntester ALL=(root) NOPASSWD: /usr/bin/omarchy-theme-set-browser-policy [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]\n')
    (root/'etc/sudoers').chmod(0o440)
    (root/'etc/pam.d').mkdir()
    (root/'etc/pam.d/sudo').write_text('auth sufficient pam_permit.so\naccount required pam_permit.so\nsession required pam_permit.so\n')
    (root/'etc/chromium/policies/managed').mkdir(parents=True)
    (root/'etc/mtab').symlink_to('/proc/mounts')
    (root/'etc/fonts').mkdir()
    (root/'etc/fonts/fonts.conf').write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd"><fontconfig><dir>/usr/share/fonts</dir><cachedir>/tmp/fontconfig</cachedir></fontconfig>\n')
    init='''#!/bin/sh
export PATH=/home/tester/.local/bin:/usr/bin:/bin
mount -t proc proc /proc
mount -t sysfs sys /sys
mount -t devtmpfs dev /dev
mount -t tmpfs tmp /tmp
mount -t tmpfs run /run
modprobe virtio_pci
modprobe 9pnet_virtio
modprobe 9p
mount -t 9p -o trans=virtio,version=9p2000.L,ro usr /usr || exec /bin/sh
ln -s /proc/self/fd /dev/fd
mount -t 9p -o trans=virtio,version=9p2000.L,ro project /project || exec /bin/sh
mount -t 9p -o trans=virtio,version=9p2000.L output /output || exec /bin/sh
modprobe virtio_gpu
mkdir -p /dev/pts /dev/shm /run/user/1000 /etc/fonts
mkdir -p /home/tester/.local/state /home/tester/.cache
mount -t devpts devpts /dev/pts
mount -t tmpfs -o mode=1777 shm /dev/shm
chmod 1777 /tmp
chown -R 1000:1000 /home/tester /run/user/1000
chmod 700 /run/user/1000
export HOME=/home/tester XDG_RUNTIME_DIR=/run/user/1000
export OMARCHY_PATH=/usr/share/omarchy QT_QUICK_BACKEND=software QT_QPA_PLATFORM=wayland
export LIBGL_ALWAYS_SOFTWARE=1 AQ_DRM_DEVICES=/dev/dri/card0
export XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=Hyprland
export VANTAGLASS_VM=1
/usr/lib/systemd/systemd-udevd --daemon
/usr/bin/udevadm trigger --action=add
/usr/bin/udevadm settle --timeout=5
if [ "VM_MODE" = "--integration" ]; then
  modprobe uinput
  chmod 0666 /dev/uinput
fi
/usr/bin/seatd -g users >/output/seatd.log 2>&1 &
sleep 1
export LIBSEAT_BACKEND=seatd SEATD_SOCK=/run/seatd.sock
/usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups dbus-run-session -- python /project/tools/vm_harness.py --inside VM_MODE >/output/guest.log 2>&1
echo "VANTAGLASS_VM_FINISHED:$?"
/usr/bin/systemctl --force --force poweroff
'''
    (root/'init').write_text(init)
    (root/'init').chmod(0o755)

def inside(integration=False, preview=False):
    if os.environ.get('VANTAGLASS_VM')!='1' or 'vantaglass_vm=1' not in Path('/proc/cmdline').read_text():
        raise RuntimeError('VM-only entry point; refusing to run on host')
    output=Path('/output')
    driver=Path('/sys/class/drm/card0/device/driver').resolve().name
    if driver not in ['virtio_gpu','virtio-pci']:raise RuntimeError('Expected a virtual GPU; refusing other devices: '+driver)
    vendor=Path('/sys/class/drm/card0/device/vendor').read_text().strip()
    if vendor!='0x1af4':raise RuntimeError('Unexpected GPU PCI vendor: '+vendor)
    devices={'dri':[str(p) for p in Path('/dev/dri').glob('*')],'drm_sys':[str(p) for p in Path('/sys/class/drm').glob('*')],'driver':driver,'pci_vendor':vendor}
    (output/'devices.json').write_text(json.dumps(devices,indent=2)+'\n')
    sources=[ROOT/'tools/vm_harness.py',ROOT/'tools/manage.py',ROOT/'tools/lifecycle.py',ROOT/'tools/updater.py',ROOT/'compatibility.json',ROOT/'hooks/vantaglass',ROOT/'hooks/vantaglass-update',*(p for folder in ['themes','plugins','entertainment'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)]
    source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    config=Path.home()/'.config/hypr/hyprland.lua'
    config.parent.mkdir(parents=True,exist_ok=True)
    baseline='hl.config({ debug = { enable_stdout_logs = true, disable_logs = false }, misc = { disable_hyprland_logo = true, disable_splash_rendering = true }, decoration = { rounding = 0, blur = { enabled = false } } })\n'
    # The minimal guest omits Omarchy's defaults; supply its terminal tagging
    # and opacity rules so the theme is checked against the normal baseline.
    baseline+='hl.window_rule({match={class="(foot|preview-.*|vantaglass-validation)"},tag="+terminal",opacity="0.985 0.96"})\n'
    baseline+='''dofile("/usr/share/omarchy/default/hypr/bootstrap.lua")
require("default.hypr.helpers")
hl.config({ general = { resize_on_border = true } })
hl.device({ name = "vantaglass-test-mouse", accel_profile = "flat", sensitivity = 0 })
o.bind("SUPER + mouse:272", "Move window", hl.dsp.window.drag(), { mouse = true })
o.bind("SUPER + mouse:273", "Resize window", hl.dsp.window.resize(), { mouse = true })
'''
    config.write_text(baseline)
    log=(output/'hyprland.log').open('w')
    process=subprocess.Popen(['/usr/bin/Hyprland','--config',str(config)],stdout=log,stderr=log)
    try:
        runtime=Path(os.environ['XDG_RUNTIME_DIR'])
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Guest compositor exited; see hyprland.log')
            sockets=list((runtime/'hypr').glob('*/.socket.sock'))
            if len(sockets)==1:
                env=dict(os.environ,HYPRLAND_INSTANCE_SIGNATURE=sockets[0].parent.name)
                response=subprocess.run(['hyprctl','-j','monitors'],env=env,capture_output=True,text=True,timeout=3)
                if response.returncode==0 and json.loads(response.stdout):
                    monitors=json.loads(response.stdout)
                    print('Guest Hyprland answered monitor IPC',flush=True)
                    results=[]
                    for appearance in ['vantaglass','baseline']*3:
                        text=baseline
                        if appearance!='baseline':text+=f'dofile("/project/themes/vantaglass/hyprland.lua")\n'
                        temporary=config.with_suffix('.tmp');temporary.write_text(text);temporary.replace(config)
                        reload=subprocess.run(['hyprctl','reload'],env=env,capture_output=True,text=True,timeout=5,check=True)
                        errors=subprocess.check_output(['hyprctl','configerrors'],env=env,text=True,timeout=3).strip()
                        if errors:raise RuntimeError('Guest configuration errors: '+errors)
                        rounding=json.loads(subprocess.check_output(['hyprctl','-j','getoption','decoration:rounding'],env=env,text=True,timeout=3))['int']
                        blur=json.loads(subprocess.check_output(['hyprctl','-j','getoption','decoration:blur:enabled'],env=env,text=True,timeout=3))['bool']
                        expected=0 if appearance=='baseline' else 18
                        if rounding!=expected or blur!=(appearance!='baseline'):raise RuntimeError('Guest theme geometry did not apply')
                        results.append({'appearance':appearance,'rounding':rounding,'blur':blur,'configerrors':errors})
                        print('Verified guest reload: '+appearance,flush=True)
                    installation=installer_flow(output,env,config,baseline,preview) if integration or preview else None
                    exit_response=subprocess.run(['hyprctl','dispatch','hl.dsp.exit()'],env=env,capture_output=True,text=True,timeout=3)
                    print('Exit response:',exit_response.returncode,exit_response.stdout,exit_response.stderr,flush=True)
                    returncode=process.wait(timeout=5)
                    if returncode:raise RuntimeError('Guest compositor did not exit cleanly: '+str(returncode))
                    if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h for p,h in source_hashes.items()):raise RuntimeError('Probe sources changed during the run')
                    report={'monitors':monitors,'devices':devices,'kernel':os.uname().release,'hyprland':subprocess.check_output(['Hyprland','--version'],text=True,timeout=3).strip(),'virtual_gpu':True,'physical_devices_shared':False,'reloads':results,'clean_exit':True,'physical_session_verified':False,'installer_verified':integration,'installation':installation,'source_sha256':source_hashes}
                    temporary=output/'probe-report.tmp';temporary.write_text(json.dumps(report,indent=2)+'\n');temporary.replace(output/'probe-report.json')
                    return
            time.sleep(.2)
        raise RuntimeError('Guest compositor did not become ready')
    finally:
        for path in Path(os.environ['XDG_RUNTIME_DIR']).glob('hypr/*/hyprland.log'):
            shutil.copyfile(path,output/'hyprland-runtime.log')
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        log.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside',action='store_true')
    parser.add_argument('--integration',action='store_true')
    parser.add_argument('--preview',action='store_true',help='Capture a theme-switcher preview in the guest')
    args=parser.parse_args()
    if args.inside:return inside(args.integration,args.preview)
    output=ROOT/('validation/vm-preview' if args.preview else ('validation/vm-integration' if args.integration else 'validation/vm-sandbox'))
    output.mkdir(parents=True,exist_ok=True)
    (output/'probe-report.json').unlink(missing_ok=True)
    kernels=sorted(p.parent for p in Path('/usr/lib/modules').glob('*/vmlinuz') if p.is_file())
    if not kernels:raise RuntimeError('No readable kernel available')
    kernel=kernels[0]
    with tempfile.TemporaryDirectory(prefix='vantaglass-vm-') as temporary:
        temporary=Path(temporary)
        root=temporary/'root';root.mkdir()
        initramfs(root,kernel)
        init=root/'init';init.write_text(init.read_text().replace('VM_MODE','--preview' if args.preview else ('--integration' if args.integration else '')))
        paths=b'\0'.join(str(p.relative_to(root)).encode() for p in sorted(root.rglob('*')))+b'\0'
        archive=subprocess.run(['cpio','--null','-o','-H','newc','--quiet','--owner=0:0'],cwd=root,input=paths,capture_output=True,check=True,timeout=20).stdout
        ramdisk=temporary/'initramfs.cpio.gz';ramdisk.write_bytes(gzip.compress(archive,mtime=0))
        cmd=['qemu-system-x86_64','-accel','kvm','-m','4096','-smp','4','-kernel',str(kernel/'vmlinuz'),'-initrd',str(ramdisk),'-append','console=ttyS0 panic=-1 vantaglass_vm=1','-display','none','-serial','stdio','-no-reboot','-nic','none','-device','virtio-vga']
        for name,path,readonly in [('usr',Path('/usr'),True),('project',ROOT,True),('output',output,False)]:
            cmd+=['-fsdev',f'local,id={name},path={path},security_model=none'+(',readonly=on' if readonly else ''),'-device',f'virtio-9p-pci,fsdev={name},mount_tag={name}']
        with (output/'console.log').open('w') as console:
            subprocess.run(cmd,stdout=console,stderr=subprocess.STDOUT,timeout=240 if args.integration or args.preview else 75,check=True,env={k:v for k,v in os.environ.items() if k not in ['DISPLAY','WAYLAND_DISPLAY','HYPRLAND_INSTANCE_SIGNATURE']})
    if not (output/'probe-report.json').exists():raise RuntimeError('VM probe failed; inspect validation/vm-sandbox logs')
    if 'VANTAGLASS_VM_FINISHED:0' not in (output/'console.log').read_text():raise RuntimeError('Guest validation failed; inspect guest.log')
    print('Disposable virtual-GPU Hyprland lifecycle probe passed.')

if __name__=='__main__':main()
