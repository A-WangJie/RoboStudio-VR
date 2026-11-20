# 2026-11-17 工程整理

本次以 RD 为 DK 中独立模块整理源码与本机数据，没有创建 Git 仓库、分支、远程连接或发布操作。

| 原位置 | 新位置 |
| --- | --- |
| 根 RoboData.apk、builds/*.apk | artifacts/apk/ |
| 根和 builds 的 symbols.zip | artifacts/symbols/ |
| 构建日志、数据桥日志 | artifacts/logs/ |
| 检查 JSON、截图 | artifacts/reports/、artifacts/screenshots/ |
| IL2CPP / Burst 调试目录 | artifacts/debug/ |
| backups/ | .local/backups/development/ |
| 本轮调整前源码 | .local/backups/engineering-20261117/ |
| Unity Hub 安装包 | .local/installers/ |
| config 的连接、无线 ADB 和启动锁 | .local/config/ |
| 早期 RD 采集 | .local/recordings/ |
| 调试过程笔记 | docs/history/（本机保留，不提交） |

Unity 工程和源代码文件未整体改名；Library 缓存保留，避免本地重新导入。根 start-bridge.sh 与 quest-unmounted.sh 是兼容入口，scripts 下是真正实现。现有 APK 均保留；Unity 新构建统一输出 artifacts/apk/RoboData.apk，不自动安装。

公开配置为格式示例；现有令牌和设备地址按原内容迁移，没有重配或同步到头显。新增 .gitignore/.gitattributes、Python 依赖、配置示例、开发说明、第三方清单、测试入口和源码导出脚本。ci/rd-tests.yml 是独立 RD 的 CI 模板，未替 DK 根仓库启用工作流。

当前没有自行选择自有代码许可证，正式公开前由所有者在 DK 根目录确定。已有字体许可保持不变；Unity 编辑器、安装包和缓存不进入源码导出。Unity Cloud 标识仅在导出的副本中清除，本地设置不变。

## 验证记录

迁移逐项清单：artifacts/reports/reorganization-manifest.json。

自动检查日志：artifacts/logs/engineering-tests.log；浏览器检查日志：artifacts/logs/engineering-chrome-tests.log。最终核验结果：artifacts/reports/engineering-verification.json。

验证覆盖原启动入口、临时隔离配置、协议与录制、设备选择、Unity GUID 完整性、源代码导出排除规则、RS 集成面板及模拟电机适配。测试不调用真实 CAN，不安装或启动头显应用；未把 Python 测试等同于 Unity Android 原生重新编译或实际手柄体验确认。

## 本轮核验结果

- 本地完整检查 67 项通过：Python 64 项，Google Chrome 集成 3 项。
- 独立源码副本 45 项通过；不依赖 DK 的测试可以在模块外运行。
- 原 `start-bridge.sh` 经一键服务启动成功，并可复用已有进程；隔离接收 3 帧模拟 WebSocket 输入。
- 实际启动 DK 的 MuJoCo 后端，验证 `/vr-ui/` 三个资源和 `/api/vr-bridge/state`，全部通过；随后关闭本轮启动的进程。
- 现有连接配置内容与权限保留；导出副本不包含本机配对码。Unity 资源 `.meta` 原样保留，导出副本的 Cloud 账号绑定已清除。
- 位置映射、姿态计算和真机 VR 控制文件与整理前一致；未调整操作手感。

现有 APK 保留，未重新编译、安装或启动头显程序，也未使能或驱动真实机械臂。独立源码需要按 README 安装依赖；本轮独立验证复用了本机已安装的同版本 WebSocket 依赖，没有访问网络安装包。
