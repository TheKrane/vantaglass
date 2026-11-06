#!/usr/bin/env bash
set -euo pipefail
if (( $# )); then
  printf '%s\n' 'Vantaglass is dark-only. Run ./install.sh without appearance options.' >&2
  exit 2
fi
if (( EUID == 0 )); then
  echo 'Run as your desktop user, without sudo.' >&2
  exit 1
fi
for dependency in curl python omarchy omarchy-shell hyprctl; do
  command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency" >&2; exit 1; }
done
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python "$project_dir/tools/manage.py" install
python "$project_dir/tools/manage.py" switch
