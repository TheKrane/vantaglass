"""Prevent the destructive guest-only entry point from running on the host."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('vm_harness',Path(__file__).resolve().parents[1]/'tools/vm_harness.py')
vm=importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)

class VmGuardTests(unittest.TestCase):
    def test_guest_entry_refuses_host_before_any_command(self):
        with patch.dict(os.environ,{},clear=True), patch.object(vm.subprocess,'Popen') as popen, patch.object(vm.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'refusing to run on host'):
                vm.inside(True)
            popen.assert_not_called()
            run.assert_not_called()

if __name__=='__main__':unittest.main()
