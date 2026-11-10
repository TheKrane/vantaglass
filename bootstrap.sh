#!/usr/bin/env bash
# Download a fixed release, verify its checksum, and run its user-local installer.
set -euo pipefail
main() {
  if (( EUID == 0 )); then echo 'Run as your normal desktop user, without sudo.' >&2; return 1; fi
  local dependency release='0.1.2' repo='TheKrane/vantaglass'
  for dependency in curl python; do
    command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency" >&2; return 1; }
  done
  work=$(mktemp -d)
  trap 'rm -rf -- "$work"' EXIT
  local asset="vantaglass-${release}.tar.gz"
  local base="https://github.com/${repo}/releases/download/v${release}"
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 3 --max-time 120 "$base/$asset" -o "$work/$asset"
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 3 --max-time 30 "$base/$asset.sha256" -o "$work/$asset.sha256"
  python - "$work" "$asset" <<'PY'
import hashlib,pathlib,sys,tarfile
folder=pathlib.Path(sys.argv[1]);name=sys.argv[2];archive=folder/name
parts=(folder/(name+'.sha256')).read_text().split()
if len(parts)!=2 or parts[1]!=name or hashlib.sha256(archive.read_bytes()).hexdigest()!=parts[0]:
    raise SystemExit('Release checksum mismatch. Nothing installed.')
with tarfile.open(archive,'r:gz') as tf:
    members=tf.getmembers()
    if len(members)>1000 or sum(m.size for m in members)>50_000_000:raise SystemExit('Unexpected archive size')
    seen=set()
    for member in members:
        path=pathlib.PurePosixPath(member.name)
        if not member.isfile() or path.is_absolute() or '..' in path.parts or path.parts[0]!='vantaglass' or member.name in seen:
            raise SystemExit('Unsafe archive member. Nothing installed.')
        seen.add(member.name)
    tf.extractall(folder,filter='data')
PY
  bash "$work/vantaglass/install.sh"
  rm -rf -- "$work"
  trap - EXIT
}
main "$@"
