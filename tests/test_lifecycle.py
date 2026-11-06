"""Behavioral checks for normal theme switching and update fallback."""
import copy
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('lifecycle',Path(__file__).resolve().parents[1]/'tools/lifecycle.py')
lifecycle=importlib.util.module_from_spec(spec);spec.loader.exec_module(lifecycle)

class LifecycleTests(unittest.TestCase):
    def config(self):
        return {'bar':{'background':'opaque','position':'bottom','layout':{'left':['omarchy.menu',{'id':'custom.spotify','x':7}], 'right':[{'id':'omarchy.audio','showMixer':False},{'id':'omarchy.network'}]}},'disabledPlugins':['omarchy.network'],'plugins':[{'id':'custom.service'}],'idle':{'lock':850}}
    def test_roundtrip_preserves_layout_options_and_disabled_widgets(self):
        original=self.config();before=copy.deepcopy(original)
        active,journal=lifecycle.activate(original)
        self.assertEqual(original,before)
        self.assertEqual(active['bar']['layout']['left'][0],'vantaglass.menu')
        self.assertEqual(active['bar']['layout']['right'][0],{'id':'vantaglass.audio','showMixer':False})
        self.assertEqual(active['bar']['layout']['right'][1],{'id':'omarchy.network'})
        restored=lifecycle.deactivate(active,journal)
        for key in ('bar','disabledPlugins','plugins','idle'):self.assertEqual(restored[key],before[key])
    def test_later_edits_survive_theme_switch(self):
        active,journal=lifecycle.activate(self.config())
        audio=active['bar']['layout']['right'].pop(0);audio['showMixer']=True
        active['bar']['layout']['left'].append(audio)
        active['bar']['layout']['right'].append({'id':'custom.new'})
        active['idle']['lock']=999
        active['bar']['background']='glassy'
        restored=lifecycle.deactivate(active,journal)
        self.assertEqual(restored['bar']['layout']['left'][-1],{'id':'omarchy.audio','showMixer':True})
        self.assertEqual(restored['idle']['lock'],999)
        self.assertEqual(restored['bar']['background'],'glassy')
        self.assertEqual(restored['bar']['layout']['right'][-1],{'id':'custom.new'})
    def test_idempotent_activate_and_deactivate(self):
        active,journal=lifecycle.activate(self.config())
        self.assertEqual(lifecycle.activate(active,journal),(active,journal))
        restored=lifecycle.deactivate(active,journal)
        self.assertEqual(lifecycle.deactivate(restored,journal),restored)
    def test_keyboard_only_menu_never_creates_bar_button(self):
        original=self.config();original['bar']['layout']['left']=[]
        active,journal=lifecycle.activate(original)
        self.assertEqual(active['bar']['layout']['left'],[])
        self.assertIn({'id':'vantaglass.menu'},active['plugins'])
        self.assertEqual(lifecycle.deactivate(active,journal)['plugins'],original['plugins'])
    def test_independent_clones_are_not_competed_with(self):
        original=self.config()
        active,journal=lifecycle.activate(original,conflicts={'omarchy.menu','omarchy.audio'})
        self.assertNotIn('omarchy.menu',journal['disabled_added'])
        self.assertNotIn('omarchy.audio',journal['disabled_added'])
        self.assertEqual(active['bar']['layout'],original['bar']['layout'])
    def test_user_disabled_clone_stays_disabled(self):
        original=self.config();original['disabledPlugins'].append('vantaglass.audio')
        active,journal=lifecycle.activate(original)
        self.assertEqual(active['bar']['layout']['right'][0]['id'],'omarchy.audio')
    def test_later_native_widget_does_not_get_duplicated_on_switch_away(self):
        active,journal=lifecycle.activate(self.config())
        active['bar']['layout']['left'].append({'id':'omarchy.audio','userChoice':True})
        restored=lifecycle.deactivate(active,journal)
        entries=[e for rows in restored['bar']['layout'].values() for e in rows if lifecycle.entry_id(e)=='omarchy.audio']
        self.assertEqual(entries,[{'id':'omarchy.audio','userChoice':True}])

    def test_uninstall_removes_own_references_only(self):
        active,journal=lifecycle.activate(self.config());active['disabledPlugins'].append('vantaglass.bluetooth')
        restored=lifecycle.deactivate(active,journal,uninstall=True)
        self.assertEqual(restored['disabledPlugins'],['omarchy.network'])
        self.assertFalse(any(e in lifecycle.OWNED for e in restored.get('cloneSourceRestores',[])))

if __name__=='__main__':unittest.main()
