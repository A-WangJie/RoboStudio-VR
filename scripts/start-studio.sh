#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/python-env.sh"
exec "$studio_python" "$studio_root/server.py" --open-browser "$@"
