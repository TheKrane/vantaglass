"""Verified release selection before any installed files are touched."""
import hashlib
import gzip
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('updater',Path(__file__).resolve().parents[1]/'tools/updater.py')
updater=importlib.util.module_from_spec(spec);spec.loader.exec_module(updater)

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.root=self.base/'runtime';self.root.mkdir();(self.root/'VERSION').write_text('0.1')
        self.state=self.base/'state';self.state.mkdir();(self.state/'installation.json').write_text('{"original":"retained"}')
        self.upstream=self.base/'upstream';self.upstream.mkdir();(self.upstream/'api.qml').write_text('known API')
        self.tag='v0.2';self.release_version='0.2';self.bad_checksum=False;self.bad_path=None;self.incompatible=False
        self.apply=Mock();self.download=patch.object(updater,'download',side_effect=self.fetch);self.mock_download=self.download.start()
    def tearDown(self):self.download.stop();self.temp.cleanup()
    def archive(self):
        stream=io.BytesIO()
        files={'VERSION':self.release_version.encode(),'tools/manage.py':b'# trusted fixture manager','compatibility.json':json.dumps({'files':{'api.qml':('0'*64 if self.incompatible else hashlib.sha256(b'known API').hexdigest())}}).encode()}
        with tarfile.open(fileobj=stream,mode='w') as tf:
            for name,content in files.items():
                item=tarfile.TarInfo('vantaglass/'+name);item.size=len(content);tf.addfile(item,io.BytesIO(content))
            if self.bad_path:
                item=tarfile.TarInfo(self.bad_path);item.size=1;tf.addfile(item,io.BytesIO(b'x'))
        return gzip.compress(stream.getvalue(),mtime=0)
    def fetch(self,url,destination,limit):
        if url==updater.LATEST:destination.write_text(json.dumps({'tag_name':self.tag,'draft':False,'prerelease':False}));return
        data=self.archive()
        if url.endswith('.sha256'):
            digest='0'*64 if self.bad_checksum else hashlib.sha256(data).hexdigest()
            destination.write_text(digest+'  '+('vantaglass-'+self.tag[1:]+'.tar.gz')+'\n')
        else:destination.write_bytes(data)
    def execute(self):return updater.update(self.root,self.state,self.upstream,self.apply)
    def test_two_part_release_versions_compare_with_patch_releases(self):
        self.assertEqual(updater.version('0.1'),updater.version('0.1.0'))
        self.assertLess(updater.version('0.1'),updater.version('0.1.1'))
        self.assertLess(updater.version('0.1.9'),updater.version('0.2'))

    def test_patch_update_after_initial_public_release(self):
        (self.root/'VERSION').write_text('0.1')
        self.tag='v0.1.1';self.release_version='0.1.1'
        self.assertTrue(self.execute())
        self.apply.assert_called_once()

    def test_new_verified_compatible_release_is_applied(self):
        self.assertTrue(self.execute());self.apply.assert_called_once()
        self.assertEqual((self.state/'installation.json').read_text(),'{"original":"retained"}')
    def test_current_or_older_release_is_not_downloaded(self):
        for tag in ['v0.1','v0.0.9']:
            self.tag=tag;self.mock_download.reset_mock();self.assertFalse(self.execute())
            self.assertEqual(self.mock_download.call_count,1)
        self.apply.assert_not_called()
    def test_invalid_or_prerelease_tag_never_applies(self):
        for tag in ['v0.2-beta','v../elsewhere','v00.2','0.2']:
            self.tag=tag
            with self.assertRaises(RuntimeError):self.execute()
        self.apply.assert_not_called()
    def test_checksum_failure_never_applies(self):
        self.bad_checksum=True
        with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):self.execute()
        self.apply.assert_not_called()
    def test_unsafe_archive_path_never_applies(self):
        self.bad_path='vantaglass/../../escape'
        with self.assertRaisesRegex(RuntimeError,'Unsafe'):self.execute()
        self.apply.assert_not_called()
    def test_incompatible_release_leaves_installation_untouched(self):
        self.incompatible=True
        self.assertFalse(self.execute());self.apply.assert_not_called()
    def test_mismatched_internal_version_never_applies(self):
        self.release_version='9.9.9'
        with self.assertRaisesRegex(RuntimeError,'version does not match'):self.execute()
        self.apply.assert_not_called()
    def test_download_failure_never_applies(self):
        self.mock_download.side_effect=OSError('network unavailable')
        with self.assertRaises(OSError):self.execute()
        self.apply.assert_not_called()
    def test_uninstall_during_download_cannot_resurrect_theme(self):
        original=self.fetch
        def remove_receipt(url,path,limit):
            original(url,path,limit)
            if url.endswith('.tar.gz'):(self.state/'installation.json').unlink()
        self.mock_download.side_effect=remove_receipt
        with self.assertRaisesRegex(RuntimeError,'Installation changed'):self.execute()
        self.apply.assert_not_called()

if __name__=='__main__':unittest.main()
