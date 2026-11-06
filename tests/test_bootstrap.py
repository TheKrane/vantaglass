"""Exercise the public bootstrap's real checksum and extraction boundary."""
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipIf(os.geteuid()==0,'Public bootstrap deliberately refuses root')
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name)
        self.bin=self.folder/'bin';self.bin.mkdir()
        (self.bin/'python').symlink_to(sys.executable)
        # Fixed local HTTP transport substitute; no user network or desktop.
        curl=self.bin/'curl'
        curl.write_text('#!'+sys.executable+'\nimport os,pathlib,shutil,sys\nargs=sys.argv[1:]\nname=next(a.rsplit("/",1)[-1] for a in args if a.startswith("https://"))\nshutil.copyfile(pathlib.Path(os.environ["BOOTSTRAP_FIXTURES"])/name,args[args.index("-o")+1])\n')
        curl.chmod(0o755)
        self.env=dict(os.environ,HOME=str(self.folder),PATH=str(self.bin)+':'+os.environ['PATH'],BOOTSTRAP_FIXTURES=str(self.folder))
        self.archive=self.folder/'vantaglass-0.1.tar.gz'
    def tearDown(self):self.tmp.cleanup()
    def prepare(self,bad_name=None,symlink=False):
        with tarfile.open(self.archive,'w:gz') as tf:
            code=b'#!/bin/bash\nprintf installed > "$HOME/installed"\n'
            info=tarfile.TarInfo('vantaglass/install.sh');info.size=len(code);tf.addfile(info,io.BytesIO(code))
            if bad_name:
                info=tarfile.TarInfo(bad_name)
                if symlink:info.type=tarfile.SYMTYPE;info.linkname='/etc/passwd';tf.addfile(info)
                else:info.size=4;tf.addfile(info,io.BytesIO(b'evil'))
        self.checksum=self.archive.with_suffix('.gz.sha256')
        self.checksum.write_text(hashlib.sha256(self.archive.read_bytes()).hexdigest()+'  '+self.archive.name+'\n')
    def execute(self):return subprocess.run(['bash',str(ROOT/'bootstrap.sh')],env=self.env,capture_output=True,text=True,timeout=10)
    def test_verified_release_runs_installer(self):
        self.prepare();result=self.execute()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.folder/'installed').read_text(),'installed')
    def test_bad_checksum_never_runs_installer(self):
        self.prepare();self.checksum.write_text('0'*64+'  '+self.archive.name+'\n')
        self.assertNotEqual(self.execute().returncode,0)
        self.assertFalse((self.folder/'installed').exists())
    def test_unsafe_paths_and_links_never_run_installer(self):
        for name,link in [('vantaglass/../../outside',False),('/absolute',False),('vantaglass/link',True)]:
            with self.subTest(name=name):
                self.prepare(name,link)
                self.assertNotEqual(self.execute().returncode,0)
                self.assertFalse((self.folder/'installed').exists())

if __name__=='__main__':unittest.main()
