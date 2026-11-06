import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('package',ROOT/'tools/package.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PackagingTests(unittest.TestCase):
    def test_inventory_excludes_user_state_and_runtime_binaries(self):
        files=module.entries()
        self.assertIn('themes/vantaglass/colors.toml',files)
        self.assertIn('plugins/vantaglass.style/Service.qml',files)
        self.assertFalse(any(name.startswith('validation/runtime/') for name in files))
        self.assertFalse(any(name.startswith('validation/shell-sandbox/') for name in files))
        self.assertFalse(any(name.endswith('.tar.gz') or name.endswith('.so') for name in files))
    def test_archives_are_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as folder:
            a=module.package(Path(folder)/'first.tar.gz')
            b=module.package(Path(folder)/'second.tar.gz')
            self.assertEqual(a.read_bytes(),b.read_bytes())

if __name__=='__main__':unittest.main()
