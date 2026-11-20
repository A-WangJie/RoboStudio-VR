# 架构与边界

```text
Quest 3 / OpenXR
  └─ ControllerInput → QuestTelemetrySender + RoboDataPanel
       └─ WebSocket :8766（USB adb reverse 或局域网 Wi-Fi）
            └─ bridge：校验、相对映射、采集、命令路由
                 ├─ HTTP 127.0.0.1:8767 → RS 的 ui/ 集成面板
                 ├─ simulation_link → DK 仿真 API
                 └─ hardware_control → DK HardwareMotion → CAN
```

Unity `devicePose` 用于机械臂遥操作，`pointer` 用于面板射线，两者不能混用。映射为 Unity 前／左／上对应机器人 +X／+Y／+Z；旋转遵循同一坐标变换。当前 V2 行为见 [USB 与自然跟随](usb-telemetry.md)。

`bridge_service.py` 是 DK 启动适配器，负责启动／复用唯一的数据桥，并继承 DK 正在使用的 Python 解释器。根目录启动脚本保留为兼容入口，真正的启动实现放在 `scripts/`。

`hardware_control.py` 在 DK 进程中运行，只提交受校验的目标；CAN 独占、限速、反馈和停止由 DK 的 `backend/hardware_motion.py` 管理。独立 RD 不包含 DK 模型或 CAN 驱动，也不会因启动数据桥就接管机械臂。

Python 源码、Unity `Assets/Packages/ProjectSettings` 和 RS UI 是提交内容。设备连接状态、令牌、日志、真实采集和构建输出属于本机数据。目录变化详见 [整理记录](reorganization.md)。
