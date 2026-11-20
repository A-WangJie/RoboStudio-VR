# RoboStudio-VR

面向 S1 V1 机械臂的自研图形化工作台：共享 Three.js 前端、Python / MuJoCo 仿真、Electron 桌面外壳，以及通过 Unity 和 OpenXR 自主搭建的 Quest 3 RoboData（RD）采集与 VR 遥操作端。

RD 是本项目的输入与采集模块：读取手柄位姿、按键和追踪状态，经 USB / Wi-Fi 传到电脑；RS 将这些数据接入相对位姿跟随、仿真和受限真机执行通道。桌面版与网页调试复用同一套功能代码。

当前版本：RS 0.3.0 / RD 0.3.9。当前验证环境为 Ubuntu 22.04 / Linux x86_64；本次工程整理不代表已完成跨平台安装包发行。

## 启动

现有电脑继续使用应用菜单中的 S1 Studio，或在根目录运行：

```bash
bash start-desktop.sh
# Google Chrome 网页调试：
bash start-studio.sh
```

新电脑首次运行前，先按 [SDK 与模型准备](docs/sdk-installation.md) 安装 SDK 扩展并导入模型。公开源码副本默认不含第三方 S1 模型，未导入时不能运行 S1 仿真。

准备完成后：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
python3 tools/install_desktop_runtime.py
bash start-desktop.sh
```

已有 Electron 运行时无需重复安装。现有本机解释器保存在 `.local/config/runtime.json`；可用 `S1_STUDIO_PYTHON` 显式指定。网页调试默认打开 Google Chrome，关闭网页不结束本地服务；桌面版退出会回收专属后端。详见 [快速开始](docs/quickstart.md)。

## 功能与边界

- S1 V1 模型、六轴关节和夹爪控制、视角、项目树与多级功能菜单。
- 末端位姿、逆解、三维拖拽／鼠标长跟随、速度比例与滚轮夹爪。
- MuJoCo FK / IK、限位、路径碰撞、运动学与可暂停的动力学仿真。
- Unity 自制 RD：左右手柄数据、USB / 局域网 Wi-Fi、配对同步、自由摘戴采集和任务录制。
- VR 相对位姿映射、抓取位姿、A／B 快捷键，以及鼠标／VR 共享的受限真机控制通道。
- 单／双臂参数和主从示教配置、SDK 只读主臂采集；配置页面不等于已实现所有实体主从执行模式。

物理运动仍需现场核对标定、设备与权限；已有自动检查主要使用模拟输入和模拟电机。TCP 未实物标定，碰撞采用网格和离散采样，软件停止不能代替硬件急停。本次整理未调整 VR 操控手感，也未执行真机运动。

## 目录

```text
app/                    共享前端、S1 模型、固定版本 Three.js
backend/                仿真、CAN、真机适配和运行路径
desktop/                Electron 主进程、IPC、图标及运行时清单
VR remote control/      RD 模块与 QuestControllerClient Unity 工程
scripts/                启动、检查、发布源码导出
tools/                  模型导入、碰撞网格、图标及运行时恢复工具
config/                 可公开的配置格式示例
tests/                  模型、协议、仿真、界面和桌面检查
docs/                   架构、操作、配置与整理说明
.github/workflows/      基础源码检查
.local/                 用户配置、缓存、工作区及备份，不提交
artifacts/              日志、截图和检查报告，不提交
recordings/、Gallery/    既有采集和图片位置，不提交
```

保留 `S1Studio`、`start-desktop.sh`、`start-studio.sh`、`install-desktop.sh` 和 `server.py` 入口，以及模型和 Unity 工程位置。现有配置、标定与 Electron 用户状态迁移后继续使用，见 [配置说明](docs/configuration.md) 和 [整理记录](docs/reorganization.md)。

## 检查与源码发布

```bash
bash scripts/test.sh
S1_STUDIO_CHROME_TESTS=1 bash scripts/test.sh
S1_STUDIO_DESKTOP_TESTS=1 bash scripts/test.sh
python3 scripts/export-source.py --output /tmp/dk-source
```

导出副本包含 RoboStudio-VR 的 RS 主体和筛选后的 RD 源码，保留 Unity GUID，去除副本中的 Unity Cloud 账号绑定。设备连接、配对码、标定、采集、运行时、APK、日志和缓存不会导出。发布副本使用 Git 管理；本机工作工程与公开源码副本分开维护。

本仓库自有 RS / RD 代码采用 [MIT 许可证](LICENSE)，版权归 A-WangJie。第三方代码、字体、模型和 SDK 遵循各自许可；MIT 不授予第三方模型的再分发权。见 [第三方清单](THIRD_PARTY_NOTICES.md) 和 [开源发布说明](docs/open-source.md)。APK 和桌面安装包可在后续版本以 Releases 附件发布，不应混入源码。

- [项目概览](docs/project-overview.md) · [架构](docs/architecture.md) · [桌面操作](docs/desktop.md) · [配置](docs/configuration.md)
- [鼠标真机控制](docs/mouse-hardware-control.md) · [机械臂配置](docs/arm-configuration.md)
- [RD / Unity 说明](VR%20remote%20control/README.md) · [贡献说明](CONTRIBUTING.md)

真机 SDK 的本地关联、RS／终端占用与初始化规则见 [共用旧 SDK 说明](docs/shared-old-sdk.md)。

## S1 真机 SDK

机械臂底层依赖 [YHRG-Robotics / S1_SDK_V2](https://github.com/YHRG-Robotics/S1_SDK_V2)，感谢上游项目。SDK 独立安装，不捆绑进本仓库。当前 RS 使用本机旧 SDK 及自有 `safe_can`、`device_session` 等扩展；直接安装上游当前版本不保证兼容，本仓库 `integrations/s1_sdk_extensions/` 提供这些自有扩展及显式安装器，安装流程见 [SDK 与模型准备](docs/sdk-installation.md)；上游原生库在新环境的全新编译仍待复验。详见 [SDK 适配说明](docs/shared-old-sdk.md)。
