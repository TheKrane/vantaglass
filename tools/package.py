#!/usr/bin/env python3
"""Create a reproducible source release without private desktop state."""
import gzip
import hashlib
import io
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]

def entries():
    files=[]
    for name in ['README.md','CONTRIBUTING.md','RELEASE_NOTES.md','ATTRIBUTION.md','LICENSE','VERSION','compatibility.json','install.sh','bootstrap.sh']:
        files.append(ROOT/name)
    for folder in ['themes','plugins','assets','licenses','tools','tests','hooks']:
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts and path.suffix!='.pyc':files.append(path)
    return {str(path.relative_to(ROOT)):path.read_bytes() for path in sorted(files)}

def package(destination=None):
    version=(ROOT/'VERSION').read_text().strip()
    destination=destination or ROOT/'dist'/('vantaglass-'+version+'.tar.gz')
    destination.parent.mkdir(parents=True,exist_ok=True)
    files=entries()
    files['SHA256SUMS']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(files.items())).encode()
    with destination.open('wb') as raw, gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as compressed, tarfile.open(fileobj=compressed,mode='w') as archive:
        for name,data in sorted(files.items()):
            item=tarfile.TarInfo('vantaglass/'+name)
            item.size=len(data)
            item.mode=0o755 if name in ('install.sh','bootstrap.sh') else 0o644
            item.mtime=0
            archive.addfile(item,io.BytesIO(data))
    # Verify exact bytes and inventory by reopening the completed archive.
    with tarfile.open(destination,'r:gz') as archive:
        found={item.name.removeprefix('vantaglass/'):archive.extractfile(item).read() for item in archive}
        if found!=files:raise RuntimeError('Archive verification failed')
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix+'.sha256').write_text(digest+'  '+destination.name+'\n')
    print(str(destination)+'\n'+digest+'\n'+str(len(files))+' verified entries')
    return destination

if __name__=='__main__':package()
