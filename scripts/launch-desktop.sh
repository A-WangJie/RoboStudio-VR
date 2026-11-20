#!/usr/bin/env bash
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$studio_root/scripts/python-env.sh"
export S1_STUDIO_PYTHON="$studio_python"
studio_runtime="$studio_root/desktop/runtime/electron"
if [[ ! -x "$studio_runtime" ]]; then
  printf 'S1 Studio runtime is missing. See desktop/runtime-lock.json.\n' >&2
  exit 1
fi
# Keep native Chromium / driver diagnostics in a separate file. Application
# errors and backend output are recorded independently in desktop.log.
# S1_STUDIO_DEBUG=1 restores native diagnostics to the launching terminal.
studio_test_run=0
for studio_argument in "$@"; do
  [[ "$studio_argument" != "--s1-smoke-test" ]] || studio_test_run=1
done
if [[ "${S1_STUDIO_DEBUG:-0}" != "1" && "$studio_test_run" == "0" ]]; then
  studio_native_logs="${S1_STUDIO_LOG_DIR:-$studio_root/artifacts/logs}"
  mkdir -p "$studio_native_logs"
  if [[ -f "$studio_native_logs/electron.log" ]] && (( $(stat -c %s "$studio_native_logs/electron.log") > 1048576 )); then
    mv -f "$studio_native_logs/electron.log" "$studio_native_logs/electron.log.previous"
  fi
  printf '\n--- RoboStudio launch %s ---\n' "$(date -Is)" >> "$studio_native_logs/electron.log"
  exec 2>> "$studio_native_logs/electron.log"
fi
unset ELECTRON_RUN_AS_NODE
exec "$studio_runtime" --class=S1Studio "$studio_root/desktop" "$@"
