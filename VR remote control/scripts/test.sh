#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/python-env.sh"
cd -- "$rd_root"
rd_test_state="$(mktemp -d -t robodata-tests-XXXXXXXX)"
trap 'rm -rf -- "$rd_test_state"' EXIT
export ROBODATA_CONFIG_DIR="$rd_test_state/config"
export ROBODATA_RECORDINGS="$rd_test_state/recordings"
export PYTHONPATH="$rd_root/tools/python:$rd_root/..${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
for rd_test_file in tests/test_*.py; do
  if [[ "$rd_test_file" == *chrome.py && "${ROBODATA_CHROME_TESTS:-0}" != 1 ]]; then continue; fi
  if [[ "$rd_test_file" == tests/test_bridge_service.py && ! -f ../server.py ]]; then continue; fi
  "$rd_python" -m unittest discover -s tests -p "$(basename -- "$rd_test_file")" -v
done
if [[ -f ../server.py ]]; then
  "$rd_python" -m unittest discover -s tests_hardware -p test_vr_hardware.py -v
  if [[ "${ROBODATA_CHROME_TESTS:-0}" == 1 ]]; then
    "$rd_python" -m unittest discover -s tests_hardware -p test_vr_hardware_chrome.py -v
  fi
fi
