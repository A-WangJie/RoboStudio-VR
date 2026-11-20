#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/python-env.sh"
cd -- "$rd_root"
if [[ "${ROBODATA_SKIP_ADB:-0}" != 1 ]]; then
  if quest_serial="$("$rd_python" "$rd_root/bridge/adb_device.py")"; then
    adb -s "$quest_serial" reverse tcp:8766 tcp:8766 || printf 'USB 转发未配置；仍可使用 Wi-Fi。\n' >&2
  else
    printf 'USB 未就绪；仍启动服务，可使用 Wi-Fi。\n' >&2
  fi
fi
exec "$rd_python" bridge/server.py "$@"
