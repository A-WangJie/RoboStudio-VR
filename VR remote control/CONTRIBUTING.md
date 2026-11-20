# 开发与贡献

从 README 的快速开始创建 Python 环境，使用 Unity 6000.3.28f1 打开 `QuestControllerClient`。Unity 的 `.meta` 文件是资源 GUID 的组成部分，必须和资源一起提交；不要重新生成现有场景、OpenXR 配置或更改 GUID 来整理目录。

桥接依赖见 `requirements.txt`，Unity 依赖由 `Packages/manifest.json` 和 `packages-lock.json` 固定。运行 `bash scripts/test.sh`；改动 RS 面板时再运行 Chrome 检查。`NODE_BINARY` 可指定 Node.js 22+，`ROBODATA_PYTHON` 可指定 Python。

位置映射、姿态变换、离合、A／B 按键和真机安全条件属于行为改动，应与目录整理分开，附复现输入、前后目标和测试。真机测试须显式操作，不允许测试脚本自动使能或恢复上次跟随。

`artifacts/`、`.local/`、Unity `Library`、个人 `UserSettings`、采集数据及密钥不进入提交。先执行源码导出脚本检查发布副本；不要把机器上的整个目录拖进 GitHub。

提交说明写清问题、行为变化、验证结果和仍需设备确认的部分。许可证由 DK 项目所有者统一确定。
