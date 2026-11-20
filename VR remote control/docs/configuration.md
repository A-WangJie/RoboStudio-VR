# 配置与本机数据

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| ROBODATA_PYTHON | RD `.venv/bin/python`，其次 python3；RS 启动时继承其解释器 | 启动脚本使用的 Python |
| QUEST_SERIAL | 自动选择唯一已授权 USB 设备 | 多设备时手动指定，避免写死个人序列号 |
| ROBODATA_DATA_DIR | RD `.local/` | 本地数据根目录 |
| ROBODATA_CONFIG_DIR | `.local/config/` | connection.json、wireless-adb.json 和桥启动锁 |
| ROBODATA_LOG_DIR | `artifacts/logs/` | 数据桥进程日志 |
| ROBODATA_RECORDINGS | DK 集成：DK 根 `recordings/`；独立 RD：`.local/recordings/` | 采集数据，不提交 |
| ROBODATA_S1_SDK | DK 同级的 `14-DOF robotic arm/S1_SDK_V2` | 可选实体主臂只读 SDK |
| ROBODATA_SDK_PYTHON | 当前 Python | SDK 原生扩展需匹配解释器版本 |
| ROBODATA_APK | `artifacts/apk/RoboData.apk` | Unity 构建输出路径 |
| UNITY_EDITOR | PATH 中的 Unity | 命令行 Android 构建所用编辑器 |
| NODE_BINARY | PATH 中的 node | Chrome 测试使用 Node.js 22+ |
| ROBODATA_CHROME_TESTS | 0 | 测试入口是否运行 Chrome 集成检查 |
| ROBODATA_SKIP_ADB | 0 | 无设备验证时跳过启动／退出的 ADB 操作，不用于替代手柄追踪 |

脚本不自动执行 `.env`，避免来源不明文件变成启动指令。需要的环境变量由终端或进程管理器显式设置。

首次运行自动生成连接策略和随机配对码；示例只说明格式。不要将示例配对码用于真实连接。Wi-Fi 模式使用局域网明文 WebSocket，当前不提供公网部署方案。USB 一键同步会更新头显连接配置，并可更新独立的无线 ADB 地址。

此次整理将旧 `config/connection.json`、`config/wireless-adb.json` 和启动锁迁入 `.local/config/`，内容和权限保留，没有重置本机配对。历史采集迁到 `.local/recordings/`；DK 当前的共享 `recordings/` 路径不变。
