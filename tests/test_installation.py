"""Exercise installation state and rollback against an isolated home."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import subprocess
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('manage',ROOT/'tools/manage.py')
manage=importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)
PREFLIGHT = manage.preflight

class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.home=Path(self.tmp.name)
        self.patches=[patch.object(manage,'HOME',self.home),patch.object(manage,'CONFIG',self.home/'.config'),patch.object(manage,'STATE',self.home/'.local/state/vantaglass'),patch.object(manage,'run'),patch.object(manage,'compatibility_issues',return_value=[]),patch.object(manage,'preflight'),patch.object(manage.subprocess,'run'),patch.object(manage.subprocess,'check_output',return_value='')]
        for item in self.patches:item.start()
        manage.subprocess.run.return_value.returncode=0
        manage.subprocess.run.return_value.stdout='ok'
        self.shell=self.home/'.config/omarchy/shell.json'
        self.shell.parent.mkdir(parents=True)
        self.shell.write_text(json.dumps({'bar':{'transparent':True,'layout':{'left':[{'id':'omarchy.workspaces'}]}}}))
        self.hypr=self.home/'.config/hypr/hyprland.lua'
        self.hypr.parent.mkdir(parents=True)
        self.hypr.write_text('-- User configuration\n')
        current=self.home/'.local/state/omarchy/current'
        current.mkdir(parents=True)
        (current/'theme.name').write_text('original-theme\n')
    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()
    def test_install_preserves_user_configuration_and_snapshot(self):
        manage.install()
        manifest=json.loads((manage.STATE/'installation.json').read_text())
        self.assertEqual(manifest['previous_theme'],'original-theme')
        self.assertTrue(Path(manifest['backup']).is_file())
        self.assertTrue(self.hypr.read_text().startswith('-- User configuration\n'))
        self.assertEqual(json.loads(self.shell.read_text())['bar']['transparent'],True)
    def test_reinstall_does_not_inject_config_hook_or_replace_backup(self):
        manage.install()
        first=(manage.STATE/'installation.json').read_text()
        manage.install()
        self.assertEqual((manage.STATE/'installation.json').read_text(),first)
        self.assertEqual(self.hypr.read_text(),'-- User configuration\n')
    def test_install_keeps_style_out_of_bar(self):
        manage.install()
        manifest=json.loads((manage.CONFIG/'omarchy/plugins/vantaglass.style/manifest.json').read_text())
        self.assertEqual(manifest['kinds'],['service'])
        self.assertNotIn('barWidget',manifest['entryPoints'])
        self.assertFalse(any('--section' in call.args[0] for call in manage.subprocess.run.call_args_list))

    def test_custom_bar_does_not_gain_missing_panel_widgets(self):
        (self.home/'.local/state/omarchy/current/theme.name').write_text('vantaglass')
        manage.install()
        config=json.loads(self.shell.read_text())
        self.assertEqual(config['bar']['layout']['left'],[{'id':'omarchy.workspaces'}])
        self.assertIn({'id':manage.MENU},config['plugins'])

    def test_string_form_menu_entry_retains_its_bar_placement(self):
        config=json.loads(self.shell.read_text())
        config['bar']['layout']['left']=['omarchy.menu']
        self.shell.write_text(json.dumps(config))
        manage.install()
        self.assertEqual(json.loads(self.shell.read_text())['bar']['layout']['left'],['omarchy.menu'])

    def test_only_present_enabled_panel_widgets_get_replaced(self):
        config=json.loads(self.shell.read_text())
        config['bar']['layout']['right']=[{'id':'omarchy.audio'},{'id':'omarchy.network'}]
        config['disabledPlugins']=['omarchy.network']
        self.shell.write_text(json.dumps(config))
        manage.install()
        (self.home/'.local/state/omarchy/current/theme.name').write_text('vantaglass')
        manage.sync()
        right=json.loads(self.shell.read_text())['bar']['layout']['right']
        self.assertEqual(right,[{'id':'vantaglass.audio'},{'id':'omarchy.network'}])

    def test_qml_upgrade_restarts_shell_to_clear_old_component_cache(self):
        manage.install()
        panel=manage.CONFIG/'omarchy/plugins/vantaglass.style/Service.qml'
        panel.write_text(panel.read_text()+'\n// Previous installed revision\n')
        manage.run.reset_mock()
        manage.install()
        manage.run.assert_any_call('omarchy','restart','shell')
    def test_new_type_in_existing_plugin_also_clears_component_cache(self):
        manage.install()
        (manage.CONFIG/'omarchy/plugins/vantaglass.style/CapsuleSlider.qml').unlink()
        manage.run.reset_mock()
        manage.install()
        manage.run.assert_any_call('omarchy','restart','shell')


    def test_switch_preserves_wallpaper_preference(self):
        manage.install()
        wallpaper=self.home/'original-forest.jpg'
        wallpaper.write_bytes(b'wallpaper-fixture')
        manage.save_json(manage.STATE/'preferences.json',{'wallpaper':str(wallpaper)})
        manage.run.reset_mock()
        manage.switch()
        manage.run.assert_any_call('omarchy','theme','bg','set',str(wallpaper))
        self.assertEqual(json.loads((manage.STATE/'preferences.json').read_text())['wallpaper'],str(wallpaper))

    def test_generated_theme_wallpaper_survives_theme_directory_replacement(self):
        manage.install()
        generated=self.home/'.local/state/omarchy/current/theme'
        image=generated/'backgrounds/original.webp';image.parent.mkdir(parents=True)
        image.write_bytes(b'original wallpaper bytes')
        (generated.parent/'background').symlink_to(image)
        def replace_theme(*args):
            if args[:3] == ('omarchy','theme','set'): shutil.rmtree(generated)
        manage.run.side_effect=replace_theme
        manage.switch()
        saved=Path(json.loads((manage.STATE/'preferences.json').read_text())['wallpaper'])
        self.assertTrue(saved.is_relative_to(manage.STATE/'wallpapers'))
        self.assertEqual(saved.read_bytes(),b'original wallpaper bytes')
        manage.run.assert_any_call('omarchy','theme','bg','set',str(saved))


    def test_restore_preserves_later_unrelated_changes(self):
        manage.install()
        self.hypr.write_text(self.hypr.read_text()+'-- Later user change\n')
        self.shell.write_text(json.dumps({'bar':{'background':'glassy','layout':{'left':[{'id':'user.new-widget'}]}},'idle':{'lock':900}}))
        manage.restore()
        self.assertIn('-- Later user change',self.hypr.read_text())
        self.assertNotIn('-- Vantaglass companion begin',self.hypr.read_text())
        restored=json.loads(self.shell.read_text())
        self.assertEqual(restored['idle']['lock'],900)
        self.assertEqual(restored['bar']['layout']['left'][0]['id'],'user.new-widget')
        self.assertEqual(restored['bar']['background'],'glassy')

    def test_existing_launcher_collision_aborts_before_config_changes(self):
        launcher=self.home/'.local/bin/vantaglass'
        launcher.parent.mkdir(parents=True)
        launcher.write_text('unrelated user script')
        with self.assertRaisesRegex(RuntimeError,'unrelated'):
            manage.install()
        self.assertFalse(manage.STATE.exists())
        self.assertEqual(self.hypr.read_text(),'-- User configuration\n')

    def test_unrelated_runtime_collision_aborts_before_changes(self):
        runtime=manage.runtime_path()
        runtime.mkdir(parents=True)
        (runtime/'unrelated.txt').write_text('User file')
        with self.assertRaisesRegex(RuntimeError,'unrelated'):
            manage.install()
        self.assertFalse(manage.STATE.exists())
        self.assertEqual((runtime/'unrelated.txt').read_text(),'User file')

    def test_installed_launcher_survives_missing_source_checkout(self):
        incoming=self.home/'source'
        for folder in ['tools','themes','plugins','licenses','hooks']:
            shutil.copytree(ROOT/folder,incoming/folder)
        for name in ['LICENSE','ATTRIBUTION.md','VERSION','compatibility.json']:
            shutil.copyfile(ROOT/name,incoming/name)
        with patch.object(manage,'ROOT',incoming):
            manage.install()
        shutil.rmtree(incoming)
        launcher=self.home/'.local/bin/vantaglass'
        # subprocess.run is mocked at this class's mutation boundary; Popen
        # executes only the installed status command in this temporary HOME.
        with subprocess.Popen([str(launcher),'status'],env=dict(os.environ,HOME=str(self.home)),stdout=subprocess.PIPE,text=True) as process:
            status=json.loads(process.communicate(timeout=5)[0])
        self.assertEqual(process.returncode,0)
        self.assertTrue(status['installed'])

    def test_unknown_upstream_refuses_before_any_installation_changes(self):
        manage.compatibility_issues.return_value=['shell/Ui/Panel.qml']
        before=self.shell.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'Unsupported'):
            manage.install()
        self.assertEqual(self.shell.read_bytes(),before)
        self.assertFalse(manage.STATE.exists())
        manage.run.assert_not_called()

    def test_unowned_theme_directory_is_not_overwritten(self):
        path=manage.CONFIG/'omarchy/themes/vantaglass'
        path.mkdir(parents=True);(path/'mine').write_text('My theme')
        with self.assertRaisesRegex(RuntimeError,'unowned'):
            manage.install()
        self.assertEqual((path/'mine').read_text(),'My theme')
        self.assertFalse(manage.STATE.exists())

    def test_failed_reinstall_rolls_back_config_assets_and_runtime(self):
        manage.install()
        panel=manage.CONFIG/'omarchy/plugins/vantaglass.style/Service.qml'
        panel.write_text('// user-edited owned file')
        original_shell=self.shell.read_bytes()
        original_manifest=(manage.STATE/'installation.json').read_bytes()
        def fail_hook(*args):
            if args[:3]==('omarchy','hook','install'):raise RuntimeError('Injected hook failure')
        manage.run.side_effect=fail_hook
        with self.assertRaisesRegex(RuntimeError,'Injected'):
            manage.install()
        self.assertEqual(panel.read_text(),'// user-edited owned file')
        self.assertEqual(self.shell.read_bytes(),original_shell)
        self.assertEqual((manage.STATE/'installation.json').read_bytes(),original_manifest)
        self.assertTrue(manage.runtime_owned(manage.runtime_path()))

    def test_post_update_incompatibility_returns_native_widgets(self):
        manage.install()
        config=json.loads(self.shell.read_text());config['bar']['layout']['left']=[{'id':'omarchy.menu'}]
        self.shell.write_text(json.dumps(config))
        (self.home/'.local/state/omarchy/current/theme.name').write_text('vantaglass')
        manage.sync()
        self.assertEqual(json.loads(self.shell.read_text())['bar']['layout']['left'][0]['id'],manage.MENU)
        manage.compatibility_issues.return_value=['changed API']
        manage.sync()
        self.assertEqual(json.loads(self.shell.read_text())['bar']['layout']['left'][0]['id'],'omarchy.menu')
        self.assertFalse((manage.STATE/'companion.json').exists())

    def test_uninstall_while_using_other_theme_preserves_theme_choice(self):
        manage.install();manage.run.reset_mock()
        manage.save_json(manage.STATE/'preferences.json',{'wallpaper':'old choice'})
        (self.home/'.local/state/omarchy/current/theme.name').write_text('another-theme')
        manage.uninstall()
        self.assertFalse(any(call.args[:3]==('omarchy','theme','set') for call in manage.run.call_args_list))
        self.assertFalse((manage.STATE/'installation.json').exists())
        self.assertFalse((manage.STATE/'preferences.json').exists())
        self.assertTrue(list(manage.STATE.glob('uninstalled-*/preferences.json')))
        self.assertFalse((manage.CONFIG/'omarchy/themes/vantaglass').exists())

    def test_upgrade_while_another_theme_is_selected_never_switches_theme(self):
        manage.install();manage.run.reset_mock()
        manage.upgrade()
        self.assertFalse(any(call.args[:3]==('omarchy','theme','set') for call in manage.run.call_args_list))
        self.assertEqual((self.home/'.local/state/omarchy/current/theme.name').read_text(),'original-theme\n')

    def test_uninstalled_theme_cannot_be_resurrected_by_upgrader(self):
        with self.assertRaisesRegex(RuntimeError,'uninstalled'):
            manage.upgrade()
        manage.run.assert_not_called()

    def test_update_hook_failure_does_not_fail_system_update(self):
        manage.install()
        with patch.object(manage.updater,'update',side_effect=OSError('offline')):
            manage.update(hook=True)
            with self.assertRaises(OSError):manage.update(hook=False)

    def test_update_hook_does_not_race_a_running_installation(self):
        import fcntl
        manage.install()
        with (manage.STATE/'operation.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            with patch.object(manage.updater,'update') as fetch:
                manage.update(hook=True)
                fetch.assert_not_called()





    def test_safe_mode_refuses_before_contacting_compositor(self):
        with patch.object(manage,'compositor_in_safe_mode',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'safe mode'):
                PREFLIGHT()
        manage.subprocess.run.assert_not_called()

    def test_safe_mode_detection_uses_process_arguments(self):
        proc=self.home/'proc/123'
        proc.mkdir(parents=True)
        (proc/'cmdline').write_bytes(b'Hyprland\0--watchdog-fd\04\0--safe-mode\0')
        self.assertTrue(manage.compositor_in_safe_mode(self.home/'proc'))
        (proc/'cmdline').write_bytes(b'Hyprland\0--watchdog-fd\x004\0')
        self.assertFalse(manage.compositor_in_safe_mode(self.home/'proc'))

    def test_recovery_argv_does_not_block_loaded_normal_omarchy_config(self):
        proc=self.home/'proc/123'
        proc.mkdir(parents=True)
        (proc/'cmdline').write_bytes(b'Hyprland\0--safe-mode\0')
        manage.subprocess.run.return_value=subprocess.CompletedProcess([],0,'true\n','')
        self.assertFalse(manage.compositor_in_safe_mode(self.home/'proc'))
        self.assertEqual(manage.subprocess.run.call_args.args[0][1],'repl')

    def test_recovery_runtime_query_timeout_stays_blocked(self):
        proc=self.home/'proc/123'
        proc.mkdir(parents=True)
        (proc/'cmdline').write_bytes(b'Hyprland\0--safe-mode\0')
        manage.subprocess.run.side_effect=subprocess.TimeoutExpired('hyprctl repl',3)
        self.assertTrue(manage.compositor_in_safe_mode(self.home/'proc'))

    def test_timed_out_switch_stops_without_recovery_operations(self):
        manage.install()
        source=manage.CONFIG/'omarchy/themes/vantaglass/shell.toml'
        original=source.read_bytes()
        manage.run.reset_mock()
        manage.run.side_effect=subprocess.TimeoutExpired('omarchy theme set',45)
        with self.assertRaises(subprocess.TimeoutExpired):
            manage.switch()
        self.assertEqual(manage.run.call_count,1)
        self.assertEqual(source.read_bytes(),original)
        self.assertFalse((manage.STATE/'preferences.json').exists())

if __name__=='__main__':unittest.main()
