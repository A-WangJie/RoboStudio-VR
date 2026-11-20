# DK 主项目工程整理 · 2026-11-17

本轮以 DK 为仓库根项目，保留 app、backend、desktop 和 VR remote control 的源码位置。未初始化 Git、创建分支或连接远程仓库，未重新编译／安装 RD，也未操作真实机械臂。

## 目录迁移

| 原位置 | 当前位置 |
| --- | --- |
| config 中五份用户 JSON | .local/config/，原内容与权限保留 |
| var/electron/ | .local/electron/，保留原 Chromium 用户状态 |
| var/backups/ | .local/backups/development/ |
| 本轮整理前源码 | .local/backups/engineering-core-20261117/ |
| var/logs/ | artifacts/logs/ |
| var 下状态与核验 JSON | artifacts/reports/ |
| var/hardware-detect.lock | .local/locks/hardware-detect.lock |
| var/hardware-operations.jsonl | .local/audit/hardware-operations.jsonl |
| workspaces/ | .local/workspaces/ |
| tmp_numcai/ | .local/research/numcai/ |
| docs 下生成截图与报告 | artifacts/screenshots/、artifacts/reports/ |
| 根目录完整阶段总结 | docs/history/，本机保留；公开概览为 project-overview.md |

Gallery/ 和 recordings/ 保留用户约定的原位置。Electron 官方运行时继续在 desktop/runtime/，Unity 工程继续在 VR remote control/QuestControllerClient/；两类缓存／运行时都不进入源码导出。

根 S1Studio、start-desktop.sh、start-studio.sh、install-desktop.sh 和 server.py 保持可用；启动实现归入 scripts。桌面配置／IPC、网页后端、真机参数、夹爪标定、日志菜单和检查脚本同步使用新目录。环境变量见 [configuration.md](configuration.md)。

## 发布与依赖

新增根 README、快速开始、配置说明、贡献说明、第三方清单、依赖入口、直接依赖验证版本、Git 忽略／文本规则和基础 CI。config 仅保存格式示例；个人解释器与 Node 选择保存在不提交的 .local/config/runtime.json。

scripts/export-source.py 生成包含 DK 与 RD 的源码副本，保留源文件权限和 Unity GUID，清除导出副本中的 Unity Cloud 绑定，排除本机数据、缓存、APK 与 Electron 运行时。SOURCE_MANIFEST.json 记录逐文件 SHA-256。许可证尚未选择，模型再分发条件待核实；此次没有进行发布。

## 验证记录

完整迁移与原配置校验值：artifacts/reports/core-reorganization-manifest.json。

最终检查和启动结果：artifacts/reports/core-engineering-verification.json；完整检查日志：artifacts/logs/core-engineering-full-tests.log。生成文件属于本机核验材料，不提交到源码仓库。

本轮核对模型、仿真、CAN 编码、鼠标及 RD 映射未变；真机适配只改变默认配置、锁和审计路径。Chrome 检查使用隔离配置；Electron 检查使用临时 profile、真实 MuJoCo 和模拟电机。真实头显输入、Android 重编译和实体机械臂运动不在本轮验证范围。

## 本轮最终结果

本地检查共 160 项通过：Python 143 项（包含 12 个 Chrome 检查方法和 3 个真实 Electron 检查方法），Node.js 17 项。Chrome 启动故障检查另覆盖正常及九类故障场景；其方法数不重复计入总数。

项目外的源码副本通过 125 项 Python 与 17 项 Node 检查，另外 3 项依赖本机 SDK 的离线原生对照检查明确跳过。独立启动也已验证 MuJoCo、RD 数据桥／面板与代理、原设置和夹爪标定读取。独立检查复用已有依赖，没有联网下载安装。

原根入口从项目外目录启动成功；菜单安装入口在临时目录生成正确路径，现有系统应用菜单无需改动。全部临时服务均已关闭，原配置内容和权限保持一致。

统一回归时修复了三处旧检查假设：浏览器模拟缺少基础对象、启动故障服务缺少 RD 模块路由、遥操作检查仍把全零姿态当作碰撞并等待旧展示姿态。这些只改测试环境与样例，没有改动控制算法。
