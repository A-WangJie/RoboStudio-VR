#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/python-env.sh"
rd_unity="${UNITY_EDITOR:-Unity}"
if ! command -v "$rd_unity" >/dev/null 2>&1; then
  printf '请设置 UNITY_EDITOR 为 Unity 6000.3.28f1 可执行文件路径。\n' >&2
  exit 1
fi
mkdir -p -- "$rd_root/artifacts/apk" "$rd_root/artifacts/logs"
export ROBODATA_APK="${ROBODATA_APK:-$rd_root/artifacts/apk/RoboData.apk}"
exec "$rd_unity" -batchmode -quit -buildTarget Android \
  -projectPath "$rd_root/QuestControllerClient" \
  -executeMethod RoboStudioVR.Editor.BuildRoboData.Build \
  -logFile "$rd_root/artifacts/logs/unity-build.log"
