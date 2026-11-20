# 配置与目录覆盖

| 变量 | 默认位置 / 行为 |
| --- | --- |
| S1_STUDIO_DATA_DIR | DK `.local/`，缓存、锁、审计和用户数据 |
| S1_STUDIO_CONFIG_DIR | 数据目录下 `config/`，桌面与后端共享 |
| S1_STUDIO_LOG_DIR | DK `artifacts/logs/` |
| S1_STUDIO_WORKSPACES_DIR | 数据目录下 `workspaces/` |
| S1_STUDIO_ARTIFACTS_DIR | DK `artifacts/`，生成的检查报告与截图 |
| S1_STUDIO_PYTHON | 显式解释器；优先于所有保存设置 |
| NODE_BINARY | JavaScript / Chrome 检查使用的 Node.js 22+ |
| S1_STUDIO_CHROME_TESTS | 设为 1 运行 Chrome 检查，同时检查 RD 浏览器面板 |
| S1_STUDIO_DESKTOP_TESTS | 设为 1 运行 Electron 窗口与 IPC 检查 |
| S1_STUDIO_RD_TESTS | 默认 1；设为 0 只检查 DK 核心 |
| ROBODATA_S1_SDK | 旧版 SDK 源码根目录，供遗留 RD 只读采集／原生离线对照；RS 当前通过 Python 安装的 SDK 关联加载，不由此变量切换 |

解释器依次使用 `S1_STUDIO_PYTHON`、本机 `settings.json` 的 `pythonPath`、本机 `runtime.json` 的 `pythonPath`、DK `.venv/bin/python`、PATH 中的 python3。现有电脑的解释器路径仅写入不提交的 `runtime.json`，源码中不包含个人 home 路径。

`server.py --config /路径/settings.json` 仍优先使用指定文件；机械臂配置与夹爪标定从该文件的同目录读取。未指定时使用 `.local/config/`；网页版没有设置文件时沿用后端默认仿真参数。桌面首次启动会生成默认 settings，已有配置损坏时直接报错，不静默覆盖。

原 `config/` 中的五份用户配置已完整迁入 `.local/config/`；桌面 IPC、后端、真机适配和日志菜单使用新位置。窗口状态、快捷目标栏及真机夹爪标定均保留。`config/` 只保留经过清理的示例，不应直接用示例覆盖真实标定。

浏览器 localStorage 和桌面 Electron profile 保持原有存储机制；Electron profile 从 `var/electron/` 搬到 `.local/electron/`，文件内容不变。网页来源端口变化仍会影响浏览器 localStorage，属于原有浏览器行为。

RD 的设备配置继续独立存于 `VR remote control/.local/config/`，使用它自己的 `ROBODATA_*` 环境变量，详见 [RD 配置](../VR%20remote%20control/docs/configuration.md)。脚本不自动执行 `.env` 文件。

2026-11-19 适配更新：RS 真机检测、状态与运动通信已归入本地旧 SDK 的 `safe_can` 扩展；原生高层控制仍保留。初始化行为、占用和终端切换规则见 [共用旧 SDK](shared-old-sdk.md)。
