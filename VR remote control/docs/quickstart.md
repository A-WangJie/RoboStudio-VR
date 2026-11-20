# 快速开始

## 环境

- Ubuntu 22.04 是当前验证平台；Python 3.10+。
- Meta Quest 3、Touch 控制器、开发者模式及已授权 USB 调试。
- `adb` 可通过 Android Platform-Tools 或发行版软件包安装。
- Unity 源码开发：Unity Hub、Unity 6000.3.28f1、Android Build Support（SDK / NDK / OpenJDK）。

## 使用现有 DK

从 DK 根目录运行 `bash start-desktop.sh`，在“机械臂控制 → AR / VR → 设备与采集”点击“RD数据桥配置”。保持 Quest USB 连接，选择 USB 或同一局域网的 Wi-Fi，通过“一键同步”配置已安装的 RoboData。数据页显示实际手柄追踪有效后，再进入仿真遥控。

不需要修改 Unity 工程或重装应用来适配本次目录整理。头显启动、系统权限和手柄追踪状态需要设备上确认。

## 从源码单独启动

在本模块目录运行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash start-bridge.sh
```

没有 USB 时仍可启动桥并使用 Wi-Fi。多个 USB 设备时，先 `export QUEST_SERIAL=你的设备序列号`。监视页 `http://127.0.0.1:8767` 可检查状态；独立 RD 没有 DK 后端时不支持仿真或实体执行。

## 构建 Quest 应用

Unity Hub 打开 `QuestControllerClient`，使用 Android / ARM64 / IL2CPP 和 `Assets/Scenes/ControllerDiagnostics.unity`。现有场景与资源 GUID 必须保留。

命令行也可使用：

```bash
export UNITY_EDITOR=/你的Unity编辑器路径/Editor/Unity
bash scripts/build-quest.sh
```

脚本只构建，不自动安装或启动头显应用。APK 进入 `artifacts/apk/`，日志进入 `artifacts/logs/`；已有安装包已迁到该目录。部署使用明确指定设备的 `adb install -r`，确认包名与原应用一致后更新。

## 检查

```bash
bash scripts/test.sh
ROBODATA_CHROME_TESTS=1 bash scripts/test.sh
```

浏览器检查使用 Google Chrome 和 Node.js 22+；默认测试使用模拟输入及模拟电机，不进行真机运动。Unity 原生编译和设备实操是另行验证项。
