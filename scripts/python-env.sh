#!/usr/bin/env bash
# Source this helper. Local JSON is data, never executed as shell commands.
studio_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
studio_python="${S1_STUDIO_PYTHON:-}"
if [[ -z "$studio_python" ]]; then
  studio_python="$(python3 - "$studio_root" <<'PY'
import json, os, sys
from pathlib import Path
root=Path(sys.argv[1])
data=Path(os.environ.get('S1_STUDIO_DATA_DIR',str(root/'.local'))).expanduser()
config=Path(os.environ.get('S1_STUDIO_CONFIG_DIR',str(data/'config'))).expanduser()
for name in ('settings.json','runtime.json'):
    p=config/name
    if p.is_file():
        value=json.loads(p.read_text()).get('pythonPath')
        if value:
            print(value); break
else:
    venv=root/'.venv/bin/python'
    print(str(venv) if venv.is_file() else 'python3')
PY
)"
fi
if [[ -z "${NODE_BINARY:-}" ]]; then
  studio_node_path="$(python3 - "$studio_root" <<'PY'
import json, os, sys
from pathlib import Path
root=Path(sys.argv[1]);data=Path(os.environ.get('S1_STUDIO_DATA_DIR',str(root/'.local'))).expanduser()
p=Path(os.environ.get('S1_STUDIO_CONFIG_DIR',str(data/'config'))).expanduser()/'runtime.json'
print(json.loads(p.read_text()).get('nodeBinary','') if p.is_file() else '')
PY
)"
  if [[ -n "$studio_node_path" ]]; then export NODE_BINARY="$studio_node_path"; fi
fi
