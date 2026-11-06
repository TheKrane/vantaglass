#!/usr/bin/env python3
"""Exercise the installed Omarchy shell in an isolated, headless Wayland session.

This validates shell layer surfaces, not Hyprland compositor lifecycle behavior.
The sandbox has no host display socket, devices, network, or writable home.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import socket
import threading
import hashlib
import tomllib

ROOT = Path(__file__).resolve().parents[1]

def command(*args, check=True, timeout=5):
    return subprocess.run(args,text=True,capture_output=True,check=check,timeout=timeout)

def verify_menu_keyboard(output, tag):
    """Exercise the real menu with inert choices; never launch host applications."""
    evidence=[]
    for case, keys, expected in [
        ('arrows',['-k','Down','-k','Return'],'Beta'),
        ('search',['Gamma','-k','Return'],'Gamma'),
        ('escape',['-k','Escape'],None),
    ]:
        selected=output/(tag+'-'+case+'-selection')
        done=output/(tag+'-'+case+'-done')
        selected.unlink(missing_ok=True);done.unlink(missing_ok=True)
        payload={'mode':'select','prompt':'Omarchy','options':['Alpha','Beta','Gamma'],
                 'selectionFile':str(selected),'doneFile':str(done)}
        command('omarchy-shell','shell','summon','omarchy.menu',json.dumps(payload))
        command('wtype','-s','350',*keys)
        for _ in range(30):
            if done.exists():break
            time.sleep(.1)
        else:raise RuntimeError('Menu keyboard request did not complete: '+case)
        actual=selected.read_text().strip() if selected.exists() else None
        if actual!=expected:raise RuntimeError('Menu keyboard result mismatch: '+case+' '+str(actual))
        evidence.append({'case':case,'selection':actual})
    return evidence

def monitor_fixture(runtime):
    """Read-only monitor data for Omarchy's Hyprland-specific scale gate.

    Shell windows still use real Wayland layer surfaces. This fixture cannot
    dispatch commands or validate the Hyprland compositor implementation.
    """
    directory=runtime/'hypr/vantaglass-test'
    directory.mkdir(parents=True,exist_ok=True)
    state={'scale':1.0}
    stopping=threading.Event()
    listeners=[]
    def serve(listener, events):
        while not stopping.is_set():
            try:connection,_=listener.accept()
            except OSError:return
            if events:
                threading.Thread(target=hold,args=(connection,),daemon=True).start()
                continue
            with connection:
                request=connection.recv(65536).decode(errors='replace')
                if request in ['j/monitors','j/monitors all']:
                    response=[{'id':0,'name':'HEADLESS-1','description':'Isolated monitor fixture','x':0,'y':0,'width':1920,'height':1080,'scale':state['scale'],'transform':0,'focused':True,'activeWorkspace':{'id':1,'name':'1'},'specialWorkspace':{'id':0,'name':''},'reserved':[0,32,0,0]}]
                elif request=='j/workspaces':response=[{'id':1,'name':'1','monitor':'HEADLESS-1','monitorID':0,'windows':0,'hasfullscreen':False,'lastwindow':'0x0','lastwindowtitle':''}]
                elif request in ['j/clients']:response=[]
                else:response={}
                try:connection.sendall(json.dumps(response).encode())
                except BrokenPipeError:pass
    def hold(connection):
        with connection:stopping.wait()
    for name,events in [('.socket.sock',False),('.socket2.sock',True)]:
        path=directory/name
        path.unlink(missing_ok=True)
        listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        listener.bind(str(path));listener.listen()
        listeners.append(listener)
        threading.Thread(target=serve,args=(listener,events),daemon=True).start()
    return state,stopping,listeners

def validate_apps(output,home):
    results=[]
    for appearance in ['vantaglass']:
        name='vantaglass'
        source=ROOT/'themes'/name
        installed=home/'.config/omarchy/themes'/name
        if installed.exists():shutil.rmtree(installed)
        shutil.copytree(source,installed)
        environment=dict(os.environ,OMARCHY_THEME_HEADLESS='1',OMARCHY_THEME_WAIT='1')
        result=subprocess.run(['omarchy','theme','set',name],env=environment,capture_output=True,text=True,timeout=20)
        tag=appearance
        (output/(tag+'-app-generation.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('Headless template generation failed for '+tag)
        generated=home/'.local/state/omarchy/current/theme'
        required=['alacritty.toml','foot.ini','kitty.conf','ghostty.conf','neovim.lua','vscode-theme.json','btop.theme','chromium.theme','helix.toml']
        for name in required:
            if not (generated/name).is_file():raise RuntimeError('Missing generated application config: '+name)
        for path in generated.iterdir():
            if not path.is_file() or path.suffix not in ['.toml','.ini','.conf','.lua','.json','.theme','.css','.yaml']:continue
            text=path.read_text()
            if '{{' in text:raise RuntimeError('Unresolved template: '+path.name)
            if path.suffix=='.toml':tomllib.loads(text)
            if path.suffix=='.json':json.loads(text)
            if path.suffix=='.lua':command('luac','-p',str(path))
        command('foot','--check-config','--config',str(generated/'foot.ini'))
        shell=tomllib.loads((generated/'shell.toml').read_text())
        if shell['vantaglass']['identity']!='vantaglass':raise RuntimeError('Generated theme identity is incorrect')
        results.append({'appearance':appearance,'required_configs':required,'templates':'resolved','json_toml_lua':'parsed','foot':'accepted'})
        print('Validated generated application configs: '+tag,flush=True)
    (output/'app-report.json').write_text(json.dumps(results,indent=2)+'\n')

def inside(apps_only=False, renderer='software', preview=False):
    # Refuse accidental direct invocation on the live desktop.
    if os.environ.get('VANTAGLASS_SANDBOX') != 'headless-layer-test' or Path('/dev/dri').exists():
        raise RuntimeError('The shell harness must run in its device-isolated sandbox')
    output = Path('/tmp/output')
    (output/('app-report.json' if apps_only else 'report.json')).unlink(missing_ok=True)
    sources={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in ['themes','plugins'] for path in sorted((ROOT/folder).rglob('*')) if path.is_file()}
    sources['tests/SwitchStates.qml']=hashlib.sha256((ROOT/'tests/SwitchStates.qml').read_bytes()).hexdigest()
    sources['tools/shell_harness.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if Path('/run/user').exists() or Path('/dev/input').exists():
        raise RuntimeError('Host session or physical input devices are visible in the sandbox')
    home = output/'home'
    state = home/'.local/state/omarchy/current'
    state.mkdir(parents=True,exist_ok=True)
    config = home/'.config/omarchy'
    config.mkdir(parents=True,exist_ok=True)
    if apps_only:
        validate_apps(output,home)
        return
    shutil.copytree(ROOT/'plugins',config/'plugins',dirs_exist_ok=True)
    # Read-only UI fixture: exercise long addresses without physical network
    # access. It changes only this private copy's input data, never callbacks.
    network=config/'plugins/vantaglass.network/Panel.qml'
    text=network.read_text();end=text.rfind('}')
    sample={'iface':'eth-test','type':'ethernet','ip':'2001:db8:abcd:1234:dead:beef:1234:5678',
            'gateway':'2001:db8:ffff:1234:abcd:5678:1234:5678','rx_bytes':'1152921504606846976','tx_bytes':'1152921504606846976'}
    fixture='\n  Timer { interval: 50; repeat: true; running: true; onTriggered: root.info = ('+json.dumps(sample)+') }\n'
    network.write_text(text[:end]+fixture+text[end:])

    bin_dir=output/'bin'
    bin_dir.mkdir(exist_ok=True)
    # Explicit fixture for compositor-derived geometry. This is not a claim
    # that Sway validates Hyprland's Lua configuration or control protocol.
    geometry=bin_dir/'hyprctl'
    geometry.write_text('''#!/usr/bin/python
import json,sys
values={"decoration:rounding":{"int":18},"general:gaps_out":{"css":"12 12 12 12"},"animations:enabled":{"bool":True}}
key=sys.argv[-1] if len(sys.argv)>1 else ""
if key in values: print(json.dumps(values[key] | {"set":True}))
else: sys.exit(1)
''')
    geometry.chmod(0o755)
    dispatch=bin_dir/'vantaglass'
    dispatch.write_text('''#!/usr/bin/python
import json,sys
with open("/tmp/output/dispatched-commands.jsonl","a") as file: file.write(json.dumps(sys.argv[1:])+"\\n")
''')
    dispatch.chmod(0o755)
    (home/'.bash_profile').write_text('export PATH="/tmp/output/bin:$PATH"\n')
    (output/'dispatched-commands.jsonl').write_text('')
    essential = {'omarchy.bar','omarchy.background','omarchy.clock','omarchy.notifications','vantaglass.style','vantaglass.menu','vantaglass.audio','vantaglass.monitor','vantaglass.network','vantaglass.bluetooth','vantaglass.power','vantaglass.clock'}
    ids = set()
    for manifest in Path('/usr/share/omarchy/shell/plugins').rglob('*.json'):
        if manifest.name != 'manifest.json' and not manifest.name.endswith('.manifest.json'):continue
        data = json.loads(manifest.read_text())
        if data.get('id'):ids.add(data['id'])
    data={'version':1,'idle':{'lock':0,'screensaver':0},'disabledPlugins':sorted(ids-essential),'plugins':[{'id':'vantaglass.style'}],
        'bar':{'background':'opaque','position':'top','layout':{'left':[{'id':'vantaglass.menu'}],'center':[{'id':'vantaglass.clock'}],'right':[{'id':'vantaglass.network'},{'id':'vantaglass.bluetooth'},{'id':'vantaglass.power'},{'id':'vantaglass.audio'},{'id':'vantaglass.monitor'}],'centerBegin':[],'centerEnd':[],'tray':[]}}}
    if preview:
        fixture=config/'plugins/vantaglass.switch-fixture'
        fixture.mkdir(exist_ok=True)
        shutil.copyfile(ROOT/'tests/SwitchStates.qml',fixture/'Widget.qml')
        (fixture/'manifest.json').write_text(json.dumps({'schemaVersion':1,'id':'vantaglass.switch-fixture',
            'name':'Inert switch visual fixture','version':'1.0.0','author':'Vantaglass tests','description':'Read-only switch states','kinds':['bar-widget'],'entryPoints':{'barWidget':'Widget.qml'}}))
        data['bar']['layout']['left'].append({'id':'vantaglass.switch-fixture'})
    (config/'shell.json').write_text(json.dumps(data))
    # A valid empty menu keeps unrelated package-management routes out of tests.
    (config/'extensions').mkdir(exist_ok=True)
    sway_config=output/'sway.conf'
    sway_config.write_text('output HEADLESS-1 mode 1920x1080\noutput HEADLESS-1 bg #191b20 solid_color\nseat seat0 fallback true\nxwayland disable\n')
    env=dict(os.environ,WLR_BACKENDS='headless',WLR_RENDERER='pixman',WLR_LIBINPUT_NO_DEVICES='1',QT_QPA_PLATFORM='wayland',QT_QUICK_BACKEND='software')
    if renderer=='opengl':
        env.pop('QT_QUICK_BACKEND',None)
        env.update(LIBGL_ALWAYS_SOFTWARE='1',QSG_RHI_BACKEND='opengl',QSG_INFO='1',QT_FORCE_STDERR_LOGGING='1')
    sway_log=(output/'sway.log').open('w')
    shell_log=(output/'shell.log').open('w')
    sway=subprocess.Popen(['/tmp/project/validation/runtime/usr/bin/sway','--config',str(sway_config),'--debug'],env=env,stdout=sway_log,stderr=sway_log)
    shell=None
    monitor_state,fixture_stop,fixture_sockets=monitor_fixture(Path(env['XDG_RUNTIME_DIR']))
    try:
        parsed=[]
        for appearance in ['vantaglass']:
            source=ROOT/'themes'/'vantaglass'/'hyprland.lua'
            result=command('/usr/bin/Hyprland','--verify-config','--config',str(source),check=False,timeout=15)
            (output/(appearance+'-hyprland-parse.log')).write_text(result.stdout+result.stderr)
            if result.returncode:raise RuntimeError('Hyprland rejected theme configuration; inspect parse log')
            parsed.append(appearance)
        for _ in range(50):
            sockets=list(Path(env['XDG_RUNTIME_DIR']).glob('wayland-*'))
            sockets=[p for p in sockets if p.is_socket()]
            if sockets:break
            if sway.poll() is not None:raise RuntimeError('Headless compositor exited; inspect sway.log')
            time.sleep(.1)
        else:raise RuntimeError('Headless display did not become ready')
        os.environ.update(env)
        os.environ['WAYLAND_DISPLAY']=sockets[0].name
        os.environ['HYPRLAND_INSTANCE_SIGNATURE']='vantaglass-test'
        ipc=list(Path(env['XDG_RUNTIME_DIR']).glob('sway-ipc.*.sock'))
        if len(ipc)!=1:raise RuntimeError('Could not uniquely identify the private compositor socket')
        os.environ['SWAYSOCK']=str(ipc[0])
        results=[]
        scales=['1'] if preview else ['1','1.25','1.5','2']
        for scale in scales:
            appearance='vantaglass'
            tag=f'{appearance}-{scale}'
            data['bar']['background']='none'
            (config/'shell.json').write_text(json.dumps(data))
            monitor_state['scale']=float(scale)
            command('/tmp/project/validation/runtime/usr/bin/swaymsg','output','HEADLESS-1','scale',scale)
            source=ROOT/'themes'/'vantaglass'
            target=state/'theme'
            if target.exists():shutil.rmtree(target)
            shutil.copytree(source,target)
            # Each backend runs in its own isolated output/home directory.
            (state/'theme.name').write_text('vantaglass'+'\n')
            background=state/'background'
            background.unlink(missing_ok=True)
            background.symlink_to(target/'backgrounds/01-misty-forest.jpg')
            notifications=home/'.local/state/omarchy/notifications'
            if notifications.exists():shutil.rmtree(notifications)
            shell=subprocess.Popen(['quickshell','--no-color','--path','/usr/share/omarchy/shell'],env=os.environ,stdout=shell_log,stderr=shell_log)
            ready=False
            for _ in range(30):
                if shell.poll() is not None:raise RuntimeError('Shell exited; inspect shell.log')
                response=command('omarchy-shell','shell','ping',check=False,timeout=3)
                if response.returncode==0 and response.stdout.strip()=='ok':ready=True;break
                time.sleep(.15)
            if not ready:raise RuntimeError('Isolated shell did not answer IPC')
            if any(item.get('id') == 'vantaglass.style' for section in data['bar']['layout'].values() for item in section):
                raise RuntimeError('Internal style service leaked into the bar')
            time.sleep(.4)
            baseline=output/(tag+'-desktop.png')
            command('grim','-o','HEADLESS-1',str(baseline))
            base_pixel=command('magick',str(baseline),'-format','%[pixel:p{960,540}]','info:').stdout
            reply=command('omarchy-shell','shell','summon','omarchy.menu','{"menu":"root"}')
            if reply.stdout.strip()!='ok':raise RuntimeError('Menu summon was not accepted')
            menu_image=output/(tag+'-menu.png')
            for _ in range(10):
                time.sleep(.25)
                command('grim','-o','HEADLESS-1',str(menu_image))
                menu_pixel=command('magick',str(menu_image),'-format','%[pixel:p{960,540}]','info:').stdout
                if menu_pixel!=base_pixel:break
            else:raise RuntimeError('Menu did not become visible at the center of the private display')
            command('omarchy-shell','shell','hide','omarchy.menu')
            keyboard_evidence=verify_menu_keyboard(output,tag)
            for panel_name in ['audio','monitor','network','bluetooth','power','clock']:
                command('omarchy-shell','shell','summon','omarchy.'+panel_name,'{}')
                time.sleep(.3)
                command('grim','-o','HEADLESS-1',str(output/(tag+'-'+panel_name+'.png')))
                command('omarchy-shell','shell','hide','omarchy.'+panel_name)
            command('notify-send','-a','Omarchy','-t','5000','Vantaglass','A clear view of your work.')
            time.sleep(.2)
            command('grim','-o','HEADLESS-1',str(output/(tag+'-notification.png')))
            results.append({'appearance':appearance,'display_scale':scale,'shell_ipc':'responding','renderer':renderer,'screenshots':['menu','audio','monitor','network','bluetooth','power','clock','notification'],'network_data':'explicit inert IPv6 fixture','power_panel':'hidden when no battery is present','menu_keyboard':keyboard_evidence})
            print('Verified '+tag,flush=True)
            shell.terminate()
            shell.wait(timeout=5)
            shell=None
        shell_log.flush()
        log=(output/'shell.log').read_text()
        for marker in ['TypeError','ReferenceError','Binding loop','service plugin load failed','ShaderEffect: Failed','File name case mismatch']:
            if marker in log:raise RuntimeError('Shell integration error: '+marker)
        if __import__('re').search(r'Plugin widget .+ failed:',log): raise RuntimeError('A panel failed to load')
        renderer_evidence={'requested':renderer}
        if renderer=='opengl':
            for marker in ['Creating QRhi with backend OpenGL','Created OpenGL context','RENDERER: llvmpipe']:
                if marker not in log:raise RuntimeError('OpenGL software device was not confirmed: '+marker)
            renderer_evidence['observed']='OpenGL via Mesa llvmpipe'
        for name,digest in sources.items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Theme source changed while the matrix was running')
        (output/'report.json').write_text(json.dumps({'environment':'device-isolated headless Sway','isolation':{'host_home':'hidden','host_runtime':'hidden','physical_devices':'absent','network':'private namespace'},'geometry':'explicit read-only Hyprland monitor and geometry fixtures','source_sha256':sources,'renderer_evidence':renderer_evidence,'results':results,'theme_lua_parsed_by_hyprland':parsed,'hyprland_lifecycle_verified':False},indent=2)+'\n')
        print('Verified '+str(len(results))+' isolated shell scenarios.')
    finally:
        fixture_stop.set()
        for listener in fixture_sockets:listener.close()
        for process in [shell,sway]:
            if process is not None and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        sway_log.close();shell_log.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside',action='store_true')
    parser.add_argument('--apps-only',action='store_true')
    parser.add_argument('--renderer',choices=['software','opengl'],default='software')
    parser.add_argument('--preview',action='store_true')
    args=parser.parse_args()
    if args.inside:return inside(args.apps_only,args.renderer,args.preview)
    apps_only=args.apps_only
    renderer=args.renderer
    if not (ROOT/'validation/runtime/usr/bin/sway').is_file():raise RuntimeError('A user-local Sway extraction is required')
    output=ROOT/('validation/preview' if args.preview else ('validation/shell-gl-sandbox' if renderer=='opengl' else 'validation/shell-sandbox'))
    preview=args.preview
    output.mkdir(parents=True,exist_ok=True)
    (output/'run').mkdir(mode=0o700,exist_ok=True)
    args=['bwrap','--ro-bind','/','/','--unshare-all','--new-session','--die-with-parent','--dev','/dev','--proc','/proc','--tmpfs','/run','--tmpfs','/tmp','--tmpfs','/home',
        '--ro-bind',str(ROOT),'/tmp/project','--bind',str(output),'/tmp/output','--chdir','/tmp/project','--clearenv',
        '--setenv','PATH','/tmp/output/bin:/usr/bin:/bin','--setenv','HOME','/tmp/output/home','--setenv','USER','tester','--setenv','XDG_RUNTIME_DIR','/tmp/output/run',
        '--setenv','XDG_CONFIG_HOME','/tmp/output/home/.config','--setenv','XDG_STATE_HOME','/tmp/output/home/.local/state','--setenv','XDG_CACHE_HOME','/tmp/output/home/.cache',
        '--setenv','OMARCHY_PATH','/usr/share/omarchy','--setenv','LD_LIBRARY_PATH','/tmp/project/validation/runtime/usr/lib','--setenv','VANTAGLASS_SANDBOX','headless-layer-test',
        'dbus-run-session','--','python','/tmp/project/tools/shell_harness.py','--inside','--renderer',renderer]
    if apps_only:args.append('--apps-only')
    if preview:args.append('--preview')
    subprocess.run(args,check=True,timeout=120)

if __name__=='__main__':main()
