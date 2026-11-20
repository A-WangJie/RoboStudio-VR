# RS 与终端的本地旧 SDK 适配（2026-11-19）

> 本文记录开发机已有的终端改动，不表示官方 SDK 已包含这些改动。公开发布只提供三个自有扩展；上游终端脚本不会自动接入共享锁。新用户请以 [SDK 安装说明](sdk-installation.md) 为准。

运行环境固定为 lerobot，S1_SDK 以 editable 方式关联本地 S1_SDK_V2；未使用 11 月 18 日从 GitHub 安装的新版。

## 实际接口与范围

- 旧 SDK 原生 C++ motor_interface 及静态库保留，示教、重力补偿、MIT 控制仍使用原有算法。
- 旧 SDK 新增本地扩展 safe_can.py：从此前已核对旧原生 SDK 帧格式的 RS 适配实现迁入。它不是官方原生库新增能力，不声称 RS 已改为调用封闭的 S1ARM 构造器。
- RS backend/s1_can.py 只做 SDK 模块别名；不再保存另一份协议实现。RS 检测也导入 SDK 的 probe_can。
- 终端 check_arm.py、V1 的 read_pos.py（only_real）、enable.py 和 disable.py 共用 safe_can。mix 与 V2 保留旧原生路径。
- 终端运动 S1_arm → OwnedNativeArm → 原生 S1ARM；RS 鼠标／VR → safe_can。共用同一 SDK 包与占用机制，但原生高层运动和安全低层接口是两个入口。

## 初始化和关闭

safe_can 连接、读状态、搜索及关闭仅管理通信与占用锁；不自动使能、失能、切换模式、回零或初始化板载透传。状态页不会创建原生机械臂对象。使能前检查完整反馈，发现故障／缺失拒绝使能，指令后读取确认。

RS 显式接管后的首个有效运动目标才按原有逻辑切换位置速度模式；保留限速、夹爪标定、失联停止和页面租约。停止 RS 跟随不自动改变电机使能状态。

旧 SDK 原生构造器内部的初始化无法从公开接口中拆除；只有用户显式运行终端运动脚本时才构造它。终端控制 close 保留失能语义，先关闭原生对象再释放占用；退出终端脚本的正常进程清理也释放。SIGKILL、掉电等强制退出不能保证电机失能，必须重新核对状态。

## RS 与终端的切换

每个 can 接口共享 /tmp/s1-sdk-UID/ 下的独占锁。同一接口同一时间只有一个控制者；不同接口可分别使用。终端控制期间 RS 检测提示占用，不切模式、不抢控制。RS 控制期间终端同样拒绝连接。先退出当前控制，再在另一方显式连接／读取，不自动接管或恢复运动。

该锁仅约束使用本次 SDK 适配后的 Python 入口，不能限制旧进程、其他 SDK、candump／自写程序或直接 C++ 示例。修改后必须重新启动已有终端脚本和 RS 后端。

主从示教在两臂都初始化成功后才使能，任一初始化或循环失败会关闭已建立的对象；不会把初始化失败当作跟随成功。

## 检查与使用

```bash
conda activate lerobot
python -c "import S1_SDK; print(S1_SDK.__file__)"
cd "/你的路径/S1_SDK_V2/examples/python"
python check_arm.py --dev can0 --end gripper
python read_pos.py --dev can0 --end gripper
```

先确认实际主从臂和接口对应，再执行 enable.py、teaching.py 或 teleop_demo.py；只读检查通过不代表实体运动已验证。接口 DOWN 时仍需显式执行 startcan，不由 SDK 偷偷修改速率或启动接口。

源码关联安装：`python -m pip install --no-deps -e /本机路径/S1_SDK_V2`。新机器需安装旧 SDK 的构建和运行依赖；不再默认从 GitHub main 安装同名 0.1.0。
