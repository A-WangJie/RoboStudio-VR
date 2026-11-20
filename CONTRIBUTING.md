# 开发与贡献

按 [快速开始](docs/quickstart.md) 安装 Python 仿真依赖。桌面运行时用固定清单恢复，前端 Three.js 已随源码保存，普通启动不需要重新导入模型或安装 S1 SDK。

默认检查入口为 `bash scripts/test.sh`，包括核心 Python、可用的 Node.js 检查和 RD Python 检查。界面改动追加 `S1_STUDIO_CHROME_TESTS=1`；桌面路径或 IPC 改动追加 `S1_STUDIO_DESKTOP_TESTS=1`。图形检查使用临时配置、模拟输入和模拟电机，不自动探测、使能或移动真实机械臂。没有安装原生 SDK 时，离线 SDK 对照检查会明确跳过。

发布前执行 `python3 scripts/export-source.py --output /tmp/dk-source`，审核生成的文件清单。不要提交 `.local/`、`artifacts/`、用户采集、个人配置、Electron 运行时或 Unity 缓存。Unity `.meta` 文件与资源必须成对保留。

配置路径整理应与操控行为变更分开。修改位姿映射、逆解、限速、输入权限或电机协议时，附复现输入、前后状态和对应检查结果。提交描述明确哪些验证使用模拟对象，哪些已经由现场操作确认。

自有代码采用根目录 [MIT 许可证](LICENSE)，覆盖 RS 与 RD；贡献自有代码时请确认有权按该许可提供。模型及第三方来源见 [第三方清单](THIRD_PARTY_NOTICES.md)。
