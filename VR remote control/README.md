# RoboData / RD

基于 Unity、OpenXR 和 Meta Quest 3 的手柄数据采集端，以及 DK / RoboStudio 的 VR 遥操作模块。RD 负责位姿、按键、连接和采集；DK 提供三维机械臂、仿真及真机执行通道。

支持 USB 转发和局域网 Wi-Fi、左右手柄实时状态、相对位姿跟随、任务数据记录，以及通过 RS 页面配置数据桥。右手 **A** 启动／重新建立跟随，**B** 返回抓取位姿；按住右握键运动，松开保持。

当前版本：RoboData 0.3.9；Unity **6000.3.28f1**；Python **3.10+**；WebSocket 依赖固定为 **15.0.1**。真机运动依赖 DK 的 S1 适配层，不能把独立 RD 桥当作通用机械臂驱动。

## 目录

```text
QuestControllerClient/  Unity 工程：Assets、Packages、ProjectSettings
bridge/                数据协议、连接、映射、录制和 DK 路由
ui/                    嵌入 RS 的控制、连接及采集面板
hardware_control.py    DK 真机遥操作适配；复用 DK 的执行权限
bridge_service.py      RS 页面的一键启动／复用数据桥服务
scripts/               启动、检查、源码导出和构建辅助脚本
config/                可公开的设备规则与配置示例
tests/                 协议、桥接、录制、配置及界面测试
tests_hardware/        DK 集成测试，电机及输入均为模拟对象
docs/                  使用、架构、协议和开发文档
artifacts/             APK、符号、日志和测试输出；不提交
.local/                本机连接配置、历史备份和安装包；不提交
```

保留 `QuestControllerClient` 名称和根目录的两个启动脚本，避免破坏本地 Unity Hub 项目登记及 RS 调用。Python 代码按现有模块划分，没有在本次整理中改变跟随算法、限速、A／B 按键或抓取位姿。

## 本地运行

在 DK 工程根目录可直接运行桌面入口 `bash start-desktop.sh`，在“机械臂控制 → AR / VR → 设备与采集”点击“RD数据桥配置”。已有本地 Python 依赖和连接配置会继续使用。

单独启动 RD 桥：

```bash
cd "VR remote control"  # 已在本目录时无需再次 cd
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash start-bridge.sh
```

可通过 `ROBODATA_PYTHON` 指定已有解释器；现有机器的 `tools/python` 保留为离线依赖，仅本机使用，不进入源码发布。HTTP 监视页为 `http://127.0.0.1:8767`；输入端口为 8766。Wi-Fi 连接由配对码限制，控制 HTTP 仅绑定本机。

首次连接使用 RS 的 USB 一键配置，或依照 [快速开始](docs/quickstart.md) 手动配置。连接配置和配对码运行时生成，**不要把本机配置复制成公共示例**。

## 开发与验证

```bash
bash scripts/test.sh
# 安装 Google Chrome 与 Node.js 22+ 后，运行浏览器检查：
ROBODATA_CHROME_TESTS=1 bash scripts/test.sh
# 使用 Unity Hub 打开 QuestControllerClient；构建方法：
bash scripts/build-quest.sh
```

测试使用临时配置目录；CAN 和 Quest 操作以模拟对象验证，不自动驱动真实机械臂。独立 RD 源码的测试跳过依赖 DK 的工作台集成检查。真机实操与 Unity Android 构建需要对应设备及工具链，不能用 Python 测试结果替代。

## 源码发布

该目录是 DK 仓库中的 RD 模块。Git 分支属于整个仓库；若后续建立 `rd` 分支，它仍包含 DK 工程，不等于把一个目录变成分支。RS 与 RD 在 [RoboStudio-VR](https://github.com/A-WangJie/RoboStudio-VR) 同一仓库维护。

生成可审核的 RD 源码副本：

```bash
python3 scripts/export-source.py --output /tmp/robodata-source
```

导出只包含明确列出的源码、Unity 资源、配置示例及文档；排除设备地址、配对码、采集数据、缓存、APK、安装包和本地备份，并移除导出副本中的 Unity Cloud 账号绑定。本地工程和本地 Cloud 设置保持原样。APK 建议作为 GitHub Releases 附件发布。

RD 自有代码采用仓库根目录 [MIT 许可证](../LICENSE)；第三方条款见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

- [架构与模块边界](docs/architecture.md)
- [连接及环境变量](docs/configuration.md)
- [数据协议](docs/protocol.md)
- [RoboData 操作说明](docs/RoboData.md)
- [S1 真机控制](docs/hardware-control.md)
- [整理记录及本地验证](docs/reorganization.md)
- [贡献说明](CONTRIBUTING.md)
