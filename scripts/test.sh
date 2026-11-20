#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/python-env.sh"
cd -- "$studio_root"
studio_test_state="$(mktemp -d -t dk-tests-XXXXXXXX)"
trap 'rm -rf -- "$studio_test_state"' EXIT
export S1_STUDIO_DATA_DIR="$studio_test_state/local"
export S1_STUDIO_CONFIG_DIR="$studio_test_state/local/config"
export S1_STUDIO_LOG_DIR="$studio_test_state/logs"
export PYTHONPATH="$studio_root${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
export S1_STUDIO_PYTHON="$studio_python"
for studio_test_file in tests/test_*.py; do
  if [[ "$studio_test_file" == *chrome* && "${S1_STUDIO_CHROME_TESTS:-0}" != 1 ]]; then continue; fi
  if [[ "$studio_test_file" == *desktop* && "${S1_STUDIO_DESKTOP_TESTS:-0}" != 1 ]]; then continue; fi
  "$studio_python" -m unittest discover -s tests -p "$(basename -- "$studio_test_file")" -v
done
studio_node="${NODE_BINARY:-}"
if [[ -z "$studio_node" ]] && command -v node >/dev/null; then studio_node=node; fi
if [[ -n "$studio_node" ]]; then
  "$studio_node" --test tests/*.test.cjs tests/*.test.mjs
else
  printf 'Node.js 未配置；跳过 JavaScript 检查。设置 NODE_BINARY 可启用。\n'
fi
if [[ "${S1_STUDIO_RD_TESTS:-1}" == 1 ]]; then
  ROBODATA_PYTHON="$studio_python" ROBODATA_CHROME_TESTS="${S1_STUDIO_CHROME_TESTS:-0}" bash 'VR remote control/scripts/test.sh'
fi
