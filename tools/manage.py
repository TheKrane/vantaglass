#!/usr/bin/env python3
"""Reversible, user-local management of dark Vantaglass."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import fcntl
import tempfile
import hashlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lifecycle
import updater

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
CONFIG = HOME/'.config'
STATE = HOME/'.local/state/vantaglass'
PLUGIN = 'vantaglass.style'
MENU = 'vantaglass.menu'
PANELS = ['vantaglass.audio', 'vantaglass.monitor', 'vantaglass.network', 'vantaglass.bluetooth', 'vantaglass.power', 'vantaglass.clock']

def run(*args):
    env = dict(os.environ, OMARCHY_THEME_WAIT='1')
    return subprocess.run(args, check=True, text=True, env=env, timeout=125 if args[:3]==('omarchy','restart','shell') else 45)

def compositor_in_safe_mode(proc=Path('/proc')):
    for path in proc.glob('[0-9]*/cmdline'):
        try:
            args = path.read_bytes().split(b'\0')
        except OSError:
            continue
        if args and Path(os.fsdecode(args[0])).name == 'Hyprland' and b'--safe-mode' in args:
            # The recovery dialog's Load Config action leaves --safe-mode in
            # argv after loading the normal config. Check the running Lua
            # state before treating that historical argument as a blocker.
            try:
                loaded = subprocess.run(['hyprctl', 'repl', 'return package.loaded["default.hypr.omarchy"] ~= nil'], capture_output=True, text=True, timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                return True
            return loaded.returncode != 0 or loaded.stdout.strip() != 'true'
    return False

def preflight():
    """Refuse live mutations in recovery mode or with an unresponsive session."""
    if compositor_in_safe_mode():
        raise RuntimeError('Hyprland is running in safe mode. Load your normal configuration before changing themes.')
    result = subprocess.run(['hyprctl', 'version'], capture_output=True, text=True, timeout=3)
    if result.returncode or not result.stdout.startswith('Hyprland '):
        raise RuntimeError('The compositor is not responding. No theme change was attempted.')


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path = path.resolve() if path.is_symlink() else path
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2)+'\n')
    temp.replace(path)

def runtime_path():
    return HOME/'.local/share/vantaglass/runtime'

def runtime_owned(path):
    marker = path/'.vantaglass-managed'
    return not path.is_symlink() and marker.is_file() and marker.read_text() == 'Vantaglass managed runtime\n'

def install_runtime():
    """Keep management commands usable after the source checkout is moved."""
    runtime = runtime_path()
    if ROOT.resolve() == runtime.resolve():
        return runtime
    runtime.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.staging-', dir=runtime.parent) as folder:
        staged = Path(folder)/'runtime'
        (staged/'tools').mkdir(parents=True)
        shutil.copyfile(ROOT/'tools/manage.py', staged/'tools/manage.py')
        shutil.copyfile(ROOT/'tools/lifecycle.py', staged/'tools/lifecycle.py')
        shutil.copyfile(ROOT/'tools/updater.py', staged/'tools/updater.py')
        shutil.copytree(ROOT/'hooks', staged/'hooks')
        shutil.copytree(ROOT/'themes', staged/'themes')
        shutil.copytree(ROOT/'plugins', staged/'plugins')
        shutil.copytree(ROOT/'licenses', staged/'licenses')
        for name in ['LICENSE', 'ATTRIBUTION.md', 'VERSION', 'compatibility.json']:
            shutil.copyfile(ROOT/name, staged/name)
        (staged/'.vantaglass-managed').write_text('Vantaglass managed runtime\n')
        archived = None
        if runtime.exists():
            archived = STATE/'runtimes'/str(time.time_ns())
            archived.parent.mkdir(parents=True, exist_ok=True)
            runtime.rename(archived)
        try:
            staged.rename(runtime)
        except OSError:
            if archived is not None and not runtime.exists(): archived.rename(runtime)
            raise
    return runtime

def plugin_entry_id(entry):
    return entry if isinstance(entry,str) else entry.get('id') if isinstance(entry,dict) else None

def bar_widget_ids(config):
    return {plugin_entry_id(entry) for section in config.get('bar',{}).get('layout',{}).values()
            if isinstance(section,list) for entry in section}

def compatibility_issues():
    """Pinned interfaces: unknown upstream revisions never run our cloned UI."""
    manifest = json.loads((ROOT/'compatibility.json').read_text())
    base = Path(os.environ.get('OMARCHY_PATH','/usr/share/omarchy'))
    return [name for name,digest in manifest['files'].items()
            if not (base/name).is_file() or hashlib.sha256((base/name).read_bytes()).hexdigest()!=digest]

def hook_paths():
    return [CONFIG/'omarchy/hooks'/(event+'.d')/('vantaglass-update' if event=='post-update' else 'vantaglass') for event in ('theme-set','post-update','post-boot')]

def validate_destinations():
    installed = (STATE/'installation.json').is_file()
    paths = [CONFIG/'omarchy/themes/vantaglass',*[CONFIG/'omarchy/plugins'/name for name in [PLUGIN,MENU,*PANELS]]]
    for path in paths:
        if path.is_symlink() or (path.exists() and not installed):
            raise RuntimeError('Refusing to overwrite an existing unowned path: '+str(path))
    for path in hook_paths():
        if path.is_symlink() or (path.exists() and 'Vantaglass managed hook' not in path.read_text()):
            raise RuntimeError('Refusing to overwrite an unrelated hook: '+str(path))

def install_hooks():
    for path in hook_paths():
        source = ROOT/'hooks'/path.name
        if path.exists() and path.read_bytes() != source.read_bytes():
            archive = STATE/'upgrades'/str(time.time_ns())/path.parent.name/path.name
            archive.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,archive)
        run('omarchy','hook','install',path.parent.name.removesuffix('.d'),str(source))

def restoration_journal(config):
    """Reconstruct restoration data from the installation snapshot."""
    manifest = json.loads((STATE/'installation.json').read_text())
    baseline = STATE/'original-shell.json'
    if baseline.exists(): original = json.loads(baseline.read_text())
    else:
        with tarfile.open(manifest['backup']) as archive:
            original = json.loads(archive.extractfile('.config/omarchy/shell.json').read())
    added = [source for clone,source in lifecycle.CLONES.items()
             if clone in bar_widget_ids(config) or clone in config.get('cloneSourceRestores',[])]
    added = [source for source in added if source not in original.get('disabledPlugins',[])]
    return {'disabled_added':added,'service_added':[PLUGIN]+([MENU] if MENU not in bar_widget_ids(original) and 'omarchy.menu' not in bar_widget_ids(original) else []),
            'bar_before':{k:v for k,v in original.get('bar',{}).items() if k in ('background','transparent')}}

def sync():
    """Reconcile only our overlay, also usable when updated shell IPC is broken."""
    if not (STATE/'installation.json').exists(): return
    path = CONFIG/'omarchy/shell.json'
    config = json.loads(path.read_text())
    journal_path = STATE/'companion.json'
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else None
    if journal is None and (bar_widget_ids(config) & set(lifecycle.CLONES) or any(plugin_entry_id(e) in lifecycle.OWNED for e in config.get('plugins',[]))):
        journal = restoration_journal(config)
    active = (HOME/'.local/state/omarchy/current/theme.name').read_text().strip()
    issues = compatibility_issues()
    if active == 'vantaglass' and not issues:
        # Respect independently installed clones of the same native widgets.
        conflicts = set()
        referenced = bar_widget_ids(config) | {plugin_entry_id(e) for e in config.get('plugins',[])}
        for candidate in (CONFIG/'omarchy/plugins').glob('*/manifest.json'):
            data = json.loads(candidate.read_text())
            if data.get('id') not in lifecycle.OWNED and data.get('id') in referenced:
                conflicts.add(data.get('omarchy',{}).get('clonedFrom'))
        updated,journal = lifecycle.activate(config,journal,conflicts)
        save_json(journal_path,journal)
    else:
        updated = lifecycle.deactivate(config,journal)
        journal_path.unlink(missing_ok=True)
        if issues: print('Vantaglass: upstream interfaces changed; native panels retained. Run vantaglass doctor for details.',file=sys.stderr)
    if updated != config: save_json(path,updated)

def enable_companion_widgets():
    sync()


def install():
    """Rollback our exact touched paths if an installation step fails."""
    preflight()
    issues = compatibility_issues()
    if issues: raise RuntimeError('Unsupported Omarchy interfaces; installation refused before changes: '+', '.join(issues[:8]))
    validate_destinations()
    launcher = HOME/'.local/bin/vantaglass'
    if launcher.exists() and 'Vantaglass managed launcher' not in launcher.read_text():
        raise RuntimeError('An unrelated ~/.local/bin/vantaglass already exists')
    if runtime_path().exists() and not runtime_owned(runtime_path()):
        raise RuntimeError('An unrelated Vantaglass runtime directory already exists')
    paths = [CONFIG/'omarchy/shell.json',CONFIG/'hypr/hyprland.lua',launcher,runtime_path(),STATE/'installation.json',STATE/'companion.json',STATE/'original-shell.json',*hook_paths(),CONFIG/'omarchy/themes/vantaglass',*[CONFIG/'omarchy/plugins'/name for name in [PLUGIN,MENU,*PANELS]]]
    paths += [path.resolve() for path in paths[:2] if path.is_symlink()]
    with tempfile.TemporaryDirectory(prefix='vantaglass-rollback-') as temporary:
        originals = []
        for index,path in enumerate(paths):
            saved = Path(temporary)/str(index)
            if path.is_symlink(): saved.symlink_to(os.readlink(path))
            elif path.is_dir(): shutil.copytree(path,saved,symlinks=True)
            elif path.exists(): shutil.copy2(path,saved)
            originals.append((path,saved))
        try:
            _install()
        except Exception:
            for path,saved in originals:
                if path.is_symlink() or path.is_file(): path.unlink()
                elif path.is_dir(): shutil.rmtree(path)
                if saved.is_symlink(): path.parent.mkdir(parents=True,exist_ok=True);path.symlink_to(os.readlink(saved))
                elif saved.is_dir(): shutil.copytree(saved,path,symlinks=True)
                elif saved.is_file(): path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(saved,path)
            # No compositor recovery operations: stop after restoring files.
            raise

def _install():
    preflight()
    issues = compatibility_issues()
    if issues: raise RuntimeError('Unsupported Omarchy interfaces; no installation changes made. Changed: '+', '.join(issues[:8]))
    validate_destinations()
    launcher = HOME/'.local/bin/vantaglass'
    if launcher.exists() and 'Vantaglass managed launcher' not in launcher.read_text():
        raise RuntimeError('An unrelated ~/.local/bin/vantaglass already exists')
    if runtime_path().exists() and not runtime_owned(runtime_path()):
        raise RuntimeError('An unrelated Vantaglass runtime directory already exists')
    STATE.mkdir(parents=True, exist_ok=True)
    if not (STATE/'installation.json').exists():
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        backup = STATE/('before-'+stamp+'.tar.gz')
        paths = ['.config/omarchy', '.config/hypr', '.config/gtk-3.0', '.config/gtk-4.0', '.config/fontconfig', '.local/state/omarchy/current', '.local/state/omarchy/toggles']
        with tarfile.open(backup, 'w:gz', dereference=False) as archive:
            for path in paths:
                if (HOME/path).exists(): archive.add(HOME/path, arcname=path)
        shutil.copyfile(CONFIG/'omarchy/shell.json',STATE/'original-shell.json')
        previous = (HOME/'.local/state/omarchy/current/theme.name').read_text().strip()
        save_json(STATE/'installation.json', {'previous_theme': previous, 'backup': str(backup), 'root': str(ROOT)})
    # Omarchy deliberately disables QML hot reload. Detect code upgrades before
    # copying so an existing instance cannot retain the previous panel layout.
    code_changed = any(
        (CONFIG/'omarchy/plugins'/path.relative_to(ROOT/'plugins').parts[0]).is_dir()
        and (not (CONFIG/'omarchy/plugins'/path.relative_to(ROOT/'plugins')).is_file()
             or (CONFIG/'omarchy/plugins'/path.relative_to(ROOT/'plugins')).read_bytes() != path.read_bytes())
        for path in (ROOT/'plugins').rglob('*')
        if path.is_file() and path.suffix in ['.qml','.qsb','.js','.json']
    )
    # Archive previous owned assets, including edits, before replacing them.
    for path in [CONFIG/'omarchy/themes/vantaglass', *[CONFIG/'omarchy/plugins'/name for name in [PLUGIN,MENU,*PANELS]]]:
        if path.exists():
            dest = STATE/'upgrades'/str(time.time_ns())/path.name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(path,dest)
            shutil.rmtree(path)
    shutil.copytree(ROOT/'themes/vantaglass', CONFIG/'omarchy/themes/vantaglass', dirs_exist_ok=True)
    for plugin in [PLUGIN, MENU, *PANELS]:
        shutil.copytree(ROOT/'plugins'/plugin, CONFIG/'omarchy/plugins'/plugin, dirs_exist_ok=True)
    bindir = HOME/'.local/bin'
    bindir.mkdir(parents=True, exist_ok=True)
    runtime = install_runtime()
    manifest = json.loads((STATE/'installation.json').read_text())
    if manifest.get('runtime') != str(runtime):
        manifest['runtime'] = str(runtime)
        save_json(STATE/'installation.json', manifest)
    # An argv-based Python launcher safely handles spaces in the checkout path.
    launcher.write_text('#!/usr/bin/env python3\n# Vantaglass managed launcher\nimport os, sys\nos.execv(sys.executable, [sys.executable, '+repr(str(runtime/'tools/manage.py'))+'] + sys.argv[1:])\n')
    launcher.chmod(0o755)
    if code_changed: run('omarchy', 'restart', 'shell')
    run('omarchy-shell', 'shell', 'rescanPlugins')
    install_hooks()
    sync()
    print('Installed Vantaglass. Original configuration:', json.loads((STATE/'installation.json').read_text())['backup'])

def durable_wallpaper(path):
    """Preserve chosen media before Omarchy atomically replaces current/theme."""
    if not path or not Path(path).is_file(): return path
    source = Path(path).resolve()
    transient = HOME/'.local/state/omarchy/current/theme'
    if not source.is_relative_to(transient.resolve()): return str(source)
    with source.open('rb') as file: digest = hashlib.file_digest(file,'sha256').hexdigest()
    folder = STATE/'wallpapers';folder.mkdir(parents=True,exist_ok=True)
    cached = folder/(digest+source.suffix.lower())
    if cached.exists():
        with cached.open('rb') as file: intact = hashlib.file_digest(file,'sha256').hexdigest() == digest
        if not intact: cached = folder/(digest+'-'+str(time.time_ns())+source.suffix.lower())
    if not cached.exists(): shutil.copy2(source,cached)
    return str(cached)


def switch():
    preflight()
    if not (STATE/'installation.json').exists():
        raise RuntimeError('Run install before applying the theme')
    name = 'vantaglass'
    dest = CONFIG/'omarchy/themes'/name
    source = ROOT/'themes'/name
    if not dest.exists(): raise RuntimeError('Theme directory is missing; run install again')
    preferences = json.loads((STATE/'preferences.json').read_text()) if (STATE/'preferences.json').exists() else {}
    background = HOME/'.local/state/omarchy/current/background'
    wallpaper = preferences.get('wallpaper') or (str(background.resolve()) if background.exists() else None)
    wallpaper = durable_wallpaper(wallpaper)
    previous_source = (dest/'shell.toml').read_bytes()
    shutil.copyfile(source/'shell.toml', dest/'shell.toml')
    try:
        run('omarchy', 'theme', 'set', name)
        if wallpaper and Path(wallpaper).is_file(): run('omarchy','theme','bg','set',wallpaper)
        run('hyprctl', 'reload')
        result = subprocess.check_output(['hyprctl', 'configerrors'], text=True, timeout=3).strip()
        if result: raise RuntimeError('Hyprland reported configuration errors:\n'+result)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError, OSError):
        # Restore the installation source, then stop. Never attempt recovery by
        # sending more compositor operations after a failed or timed-out call.
        (dest/'shell.toml').write_bytes(previous_source)
        raise
    save_json(STATE/'preferences.json', {'wallpaper': wallpaper})
    sync()
    print('Applied dark Vantaglass; wallpaper preserved')

def deactivate_companion():
    path = CONFIG/'omarchy/shell.json'
    current = json.loads(path.read_text())
    journal_path = STATE/'companion.json'
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else restoration_journal(current)
    updated = lifecycle.deactivate(current,journal,uninstall=True)
    if updated != current: save_json(path,updated)
    journal_path.unlink(missing_ok=True)

def restore():
    preflight()
    manifest = json.loads((STATE/'installation.json').read_text())
    deactivate_companion()
    # Restore the previous theme only if ours is still selected. A user who
    # switched away keeps their new choice and its wallpaper on uninstall.
    active = HOME/'.local/state/omarchy/current/theme.name'
    if active.read_text().strip() == 'vantaglass':
        run('omarchy','theme','set',manifest['previous_theme'])
        run('hyprctl','reload')
    print('Restored native panels. Original snapshot remains at '+manifest['backup'])

def uninstall():
    if not (STATE/'installation.json').exists():
        print('Vantaglass is not installed.');return
    preflight()
    manifest = json.loads((STATE/'installation.json').read_text())
    # Remove only our independent event hooks, preventing reactivation during restore.
    destination = STATE/('uninstalled-'+str(time.time_ns()))
    destination.mkdir(parents=True)
    for path in hook_paths():
        if path.is_file() and 'Vantaglass managed hook' in path.read_text():
            shutil.copy2(path,destination/(path.parent.name+'-hook'));path.unlink()
    restore()
    owned = [CONFIG/'omarchy/plugins'/name for name in [PLUGIN,MENU,*PANELS]]
    owned += [CONFIG/'omarchy/themes/vantaglass']
    if runtime_owned(runtime_path()): owned.append(runtime_path())
    for path in owned:
        if path.exists(): shutil.move(str(path),str(destination/path.name))
    launcher = HOME/'.local/bin/vantaglass'
    if launcher.exists() and 'Vantaglass managed launcher' in launcher.read_text(): launcher.unlink()
    for name in ['installation.json','preferences.json','original-shell.json']:
        if (STATE/name).exists(): shutil.move(str(STATE/name),str(destination/name))
    run('omarchy-shell','shell','rescanPlugins')
    print('Uninstalled. Preserved files:',destination)


def upgrade():
    if not (STATE/'installation.json').is_file():
        raise RuntimeError('Vantaglass was uninstalled; update cancelled')
    active = HOME/'.local/state/omarchy/current/theme.name'
    was_active = active.read_text().strip() == 'vantaglass'
    install()
    if was_active and active.read_text().strip() == 'vantaglass':
        # Use the user's currently selected image, including a choice made
        # after their original installation, rather than an older preference.
        background = HOME/'.local/state/omarchy/current/background'
        if background.exists():
            preferences = json.loads((STATE/'preferences.json').read_text()) if (STATE/'preferences.json').exists() else {}
            preferences['wallpaper'] = durable_wallpaper(str(background.resolve()))
            save_json(STATE/'preferences.json',preferences)
        switch()
    else:
        print('Vantaglass files updated; current theme left selected.')

def update(hook=False):
    # This command holds only update.lock. The candidate's upgrade command
    # takes operation.lock itself, avoiding parent/child hook deadlocks.
    try:
        with (STATE/'operation.lock').open('w') as operation:
            fcntl.flock(operation,fcntl.LOCK_EX | (fcntl.LOCK_NB if hook else 0))
            sync()
        updater.update(ROOT,STATE,Path(os.environ.get('OMARCHY_PATH','/usr/share/omarchy')))
    except (RuntimeError,OSError,ValueError,tarfile.TarError,subprocess.SubprocessError) as error:
        if not hook:raise
        print('Vantaglass update skipped: '+str(error)+'. Omarchy update can continue.',file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('install')
    commands.add_parser('upgrade',help=argparse.SUPPRESS)
    update_parser=commands.add_parser('update')
    update_parser.add_argument('--hook',action='store_true')
    commands.add_parser('switch')
    commands.add_parser('restore')
    commands.add_parser('uninstall')
    commands.add_parser('status')
    commands.add_parser('doctor')
    sync_parser = commands.add_parser('sync')
    sync_parser.add_argument('--hook',action='store_true')
    args = parser.parse_args()
    if args.command == 'update': update(args.hook)
    elif args.command == 'upgrade': upgrade()
    elif args.command == 'sync': sync()
    elif args.command == 'doctor':
        issues=compatibility_issues()
        print(json.dumps({'compatible':not issues,'changed_interfaces':issues},indent=2))
        if issues: raise SystemExit(1)
    elif args.command == 'install': install()
    elif args.command == 'switch': switch()
    elif args.command == 'restore': restore()
    elif args.command == 'uninstall': uninstall()
    else:
        active = HOME/'.local/state/omarchy/current/theme.name'
        info = {'version':(ROOT/'VERSION').read_text().strip(),'installed':(STATE/'installation.json').exists(),'active_theme':active.read_text().strip() if active.exists() else None}
        if (STATE/'preferences.json').exists(): info['preferences']=json.loads((STATE/'preferences.json').read_text())
        print(json.dumps(info,indent=2))

if __name__ == '__main__':
    try:
        STATE.mkdir(parents=True,exist_ok=True)
        with (STATE/('update.lock' if len(sys.argv)>1 and sys.argv[1]=='update' else 'operation.lock')).open('w') as lock:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX | (fcntl.LOCK_NB if '--hook' in sys.argv else 0))
            except BlockingIOError:
                raise SystemExit(0)  # Parent install/switch reconciles before releasing its lock.
            main()
    except (RuntimeError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(str(error),file=sys.stderr)
        sys.exit(1)
