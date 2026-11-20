# 第三方组件

RD 自有代码采用仓库根目录 [MIT 许可证](../LICENSE)。本文件记录第三方来源，各组件仍遵循各自许可证。

| 组件 | 来源和版本 | 处理方式 |
| --- | --- | --- |
| Unity Editor / Android 工具链 | Unity 6000.3.28f1 | 由开发者通过 Unity Hub 安装，按 Unity 条款使用，不分发编辑器及安装包 |
| Unity / OpenXR / Input System / URP 包 | `QuestControllerClient/Packages/manifest.json`、`packages-lock.json` | 通过 Unity Package Manager 获取，各包适用各自许可；不提交 Library/PackageCache |
| websockets | 15.0.1，https://github.com/python-websockets/websockets | BSD-3-Clause；requirements 声明依赖，本机离线副本不进入导出源码 |
| RoboDataFont | Noto CJK，https://github.com/notofonts/noto-cjk | 字体及随附 `Assets/Resources/RoboDataFont-LICENSE.txt` 一起保留；以该文件所载 SIL Open Font License 条款为准 |
| Android Debug Bridge | Android SDK Platform-Tools | 由使用者安装，不在源代码中分发 |
| NumPy / DK 仿真依赖 | DK 根目录 requirements-simulation.txt | 真机适配及 DK 测试需要；按上游许可安装 |

当前 Android applicationId 保留既有 Unity 模板包名，以维持本机已安装应用的配置和更新兼容。对外首次发布时可在独立版本中规划正式包名；更名会被 Android 当作另一应用，不应在文件整理时顺带变更。
