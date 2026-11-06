"""Fetch verified stable GitHub releases only after an explicit update action."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile

REPOSITORY = 'TheKrane/vantaglass'
LATEST = 'https://api.github.com/repos/'+REPOSITORY+'/releases/latest'
MAX_ARCHIVE = 16*1024*1024

def version(value):
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?',value):
        raise RuntimeError('Invalid stable release version')
    parts=[int(n) for n in value.split('.')]
    return tuple(parts+[0]*(3-len(parts)))

def download(url,destination,limit):
    subprocess.run(['curl','--fail','--silent','--show-error','--location','--proto','=https',
                    '--proto-redir','=https','--tlsv1.2','--connect-timeout','8','--max-time','30',
                    '--max-filesize',str(limit),'--user-agent','Vantaglass-Updater',
                    url,'--output',str(destination)],check=True,timeout=35)
    if destination.stat().st_size>limit:raise RuntimeError('Release download exceeded size limit')

def unpack(archive,checksum,asset,folder):
    parts=checksum.read_text().split()
    if len(parts)!=2 or parts[1]!=asset or not re.fullmatch('[0-9a-fA-F]{64}',parts[0]):
        raise RuntimeError('Invalid release checksum file')
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=parts[0].lower():
        raise RuntimeError('Release checksum mismatch; existing installation retained')
    with tarfile.open(archive,'r:gz') as tf:
        members=tf.getmembers();seen=set()
        if len(members)>1000 or sum(m.size for m in members)>50_000_000:raise RuntimeError('Unexpected release size')
        for member in members:
            path=PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!='vantaglass' or member.name in seen:
                raise RuntimeError('Unsafe release archive member')
            seen.add(member.name)
        tf.extractall(folder,filter='data')
    candidate=folder/'vantaglass'
    if not (candidate/'tools/manage.py').is_file():raise RuntimeError('Release manager is missing')
    return candidate

def compatible(candidate,upstream):
    manifest=json.loads((candidate/'compatibility.json').read_text())
    if not isinstance(manifest,dict):raise RuntimeError('Invalid compatibility manifest')
    files=manifest.get('files')
    if not isinstance(files,dict) or not files or len(files)>2000:raise RuntimeError('Invalid compatibility manifest')
    for name,digest in files.items():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:raise RuntimeError('Invalid compatibility path')
        source=upstream/name
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:return False
    return True

def update(root,state,upstream,apply=None):
    """Download and validate first; apply acquires the normal installation lock."""
    receipt=state/'installation.json'
    if not receipt.is_file():raise RuntimeError('Vantaglass is not installed')
    receipt_before=receipt.read_bytes()
    current=(root/'VERSION').read_text().strip()
    current_version=version(current)
    with tempfile.TemporaryDirectory(prefix='vantaglass-update-') as temp:
        folder=Path(temp);metadata=folder/'release.json'
        download(LATEST,metadata,1024*1024)
        release=json.loads(metadata.read_text())
        if not isinstance(release,dict):raise RuntimeError('Invalid release metadata')
        if release.get('draft') or release.get('prerelease'):raise RuntimeError('Refusing a draft or prerelease')
        tag=release.get('tag_name','')
        if not isinstance(tag,str) or not tag.startswith('v'):raise RuntimeError('Invalid release tag')
        latest=tag[1:]
        if version(latest)<=current_version:
            print('Vantaglass '+current+' is up to date.');return False
        asset='vantaglass-'+latest+'.tar.gz'
        base='https://github.com/'+REPOSITORY+'/releases/download/'+tag+'/'
        archive=folder/asset;checksum=folder/(asset+'.sha256')
        download(base+asset+'.sha256',checksum,4096)
        download(base+asset,archive,MAX_ARCHIVE)
        candidate=unpack(archive,checksum,asset,folder)
        if (candidate/'VERSION').read_text().strip()!=latest:raise RuntimeError('Release version does not match tag')
        if not compatible(candidate,upstream):
            print('Vantaglass: latest release does not match the updated Omarchy interfaces; native-panel fallback remains available.')
            return False
        if not receipt.is_file() or receipt.read_bytes()!=receipt_before:
            raise RuntimeError('Installation changed during download; update cancelled')
        print('Updating Vantaglass '+current+' → '+latest,flush=True)
        if apply is None:
            subprocess.run([sys.executable,str(candidate/'tools/manage.py'),'upgrade'],check=True,timeout=240)
        else:apply(candidate)
        print('Vantaglass updated to '+latest+'.')
        return True
