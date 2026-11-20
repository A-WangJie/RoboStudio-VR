#!/usr/bin/env bash
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
studio_applications="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$studio_applications"
cat > "$studio_applications/s1-studio.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=S1 Studio
Name[zh_CN]=S1 Studio 机器人工作台
Comment=S1 V1 末端控制、碰撞检测与 MuJoCo 仿真
Exec="$studio_root/S1Studio"
Icon=$studio_root/desktop/robostudio-rs.png
Path=$studio_root
Terminal=false
StartupNotify=true
StartupWMClass=S1Studio
Categories=Development;
EOF
chmod +x "$studio_applications/s1-studio.desktop"
if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$studio_applications"
fi
printf 'S1 Studio 已加入应用程序菜单。程序目录：%s\n' "$studio_root"
