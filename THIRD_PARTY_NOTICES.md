# 第三方来源与许可

DK / RD 自有代码采用根目录 MIT 许可证。本清单记录第三方来源；各组件仍遵循原许可，不因根目录 MIT 而改变。

| 内容 | 来源 | 处理方式 |
| --- | --- | --- |
| Three.js 0.170.0 | https://github.com/mrdoob/three.js | `app/vendor/THREE-LICENSE.txt` 随前端源码保留，MIT |
| Electron 45.3.1 | `desktop/runtime-lock.json` 的官方地址及 SHA-256 | 本机运行时保留，不纳入源码导出；恢复脚本校验官方归档，运行时内含上游条款 |
| MuJoCo / NumPy / SciPy | `requirements-simulation.txt` | 由使用者安装，分别遵循上游许可；不捆绑 Python 环境 |
| S1 V1 模型和 STL | S1_SDK_V2 随附 `resource/gripper.xml` 与 meshes | 源文件和导入哈希保留；当前目录未附可确认的模型再分发许可证，公开这些资源前需由所有者核实授权，不能用 DK 许可证替代 |
| 碰撞分解数据 | 由配套 STL 使用 coacd / trimesh 生成 | `app/assets/s1_v1/collision/` 保留来源哈希和算法参数；模型来源条件同上 |
| RoboData / RD 依赖 | Unity、OpenXR、Noto CJK 字体、websockets | 见 [RD 第三方清单](VR%20remote%20control/THIRD_PARTY_NOTICES.md)，字体原许可证随源码保留 |

DummyStudio 仅作为早期界面参考，发布文件和 Wine 环境已经移除，不是 DK 的运行依赖。第三方数采 APK 研究副本仅保留于 `.local/research/`，不纳入源码导出。

## S1 底层 SDK

上游：[YHRG-Robotics/S1_SDK_V2](https://github.com/YHRG-Robotics/S1_SDK_V2)。本项目调用 SDK 接口及本地兼容扩展，SDK 本体不随源码副本分发。上游 SDK 和随附模型的授权范围尚需核实；仅添加来源链接不等于获得再分发授权。现有本地扩展的职责和兼容范围见 [共用旧 SDK 说明](docs/shared-old-sdk.md)。

上游核实记录与获取方式见 [SDK 安装说明](docs/sdk-installation.md)。公开副本默认排除 `app/assets/s1_v1/`。`integrations/s1_sdk_extensions/` 是本项目自有适配代码，采用 MIT，并非上游发行 SDK。
