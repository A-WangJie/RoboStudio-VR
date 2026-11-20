#!/usr/bin/env bash
# Quest developer-mode session control. Does not disable tracking validity checks.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/python-env.sh"
quest_serial="$("$rd_python" "$rd_root/bridge/adb_device.py")"
quest_adb=(adb -s "$quest_serial")
case "${1:-status}" in
  on)
    "${quest_adb[@]}" get-state >/dev/null
    # Do not resume any previous simulation session as part of waking the headset.
    if curl -fsS --max-time 3 -H 'Origin: http://127.0.0.1:8767' -X POST \
      http://127.0.0.1:8767/api/simulation/disable >/dev/null; then
      printf '已停止旧仿真跟随，需在电脑页面重新启用。\n'
    else
      printf '桥接服务未响应；如需仿真，请检查服务后重新启用。\n'
    fi
    "${quest_adb[@]}" reverse tcp:8766 tcp:8766
    "${quest_adb[@]}" shell am broadcast -a com.oculus.vrpowermanager.prox_close
    "${quest_adb[@]}" shell input keyevent KEYCODE_WAKEUP
    "${quest_adb[@]}" shell am start -n com.UnityTechnologies.com.unity.template.urpblank/com.unity3d.player.UnityPlayerGameActivity
    printf '已请求摘戴采集模式。请在监视页确认实时接收且手柄追踪有效。\n'
    ;;
  off)
    curl -fsS --max-time 3 -H 'Origin: http://127.0.0.1:8767' -X POST \
      http://127.0.0.1:8767/api/simulation/disable >/dev/null || true
    "${quest_adb[@]}" shell am broadcast -a com.oculus.vrpowermanager.automation_disable
    printf '已请求恢复自动佩戴感应。摘下后观察休眠是否恢复；若无效，重启头显恢复本次临时设置。\n'
    ;;
  status)
    "${quest_adb[@]}" shell dumpsys power | rg 'mWakefulness=|mProximityPositive='
    ;;
  *) printf '用法：%s on|off|status\n' "$0" >&2; exit 2 ;;
esac
