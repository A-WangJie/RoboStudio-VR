# 快速开始

当前验证平台为 Ubuntu 22.04 / Linux x86_64。Python 3.10+ 用于仿真，Node.js 22+ 用于 JavaScript 与 Chrome 检查；桌面模式使用清单固定的 Electron 45.3.1。

## 从源码启动

在 DK 根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# 先按 sdk-installation.md 获取和安装 SDK，再添加本项目扩展并导入模型
.venv/bin/python -m pip install -e /路径/S1_SDK_V2
.venv/bin/python tools/install_s1_extensions.py --sdk-root /路径/S1_SDK_V2 --apply
# 按 sdk-installation.md 导入模型并生成碰撞数据后，再继续
python3 tools/install_desktop_runtime.py
bash start-desktop.sh
```

桌面运行时已经存在时不必重复安装。只调试网页版可运行 `bash start-studio.sh`，它打开 Google Chrome；完全退出需在终端按 Ctrl+C。桌面版关闭窗口会暂停并结束自己的仿真后端。不要直接双击 `app/index.html`。

现有电脑仍可使用原桌面菜单、`S1Studio` 和两个根启动脚本。此次整理保留本机 Python 选择和 Electron 用户数据，没有恢复默认机械臂标定。换目录后执行 `bash install-desktop.sh` 重新登记应用菜单。

## 参数与数据

本机参数为 `.local/config/settings.json`、`arms.json`、`gripper-calibration.json`。公开格式示例位于 `config/`；示例不包含个人设备地址和真机标定行程。`S1_STUDIO_PYTHON` 可指定已有解释器；其他位置覆盖见 [配置说明](configuration.md)。

日志在 `artifacts/logs/`，工作区默认保存到 `.local/workspaces/`。已有 RD 采集仍保存到根目录 `recordings/`，Quest 图片仍可保存到 `Gallery/`。两者不进入源码发布。

## VR / RD

RD 位于 `VR remote control/`，其 Unity 工程路径不变。RS 中进入“机械臂控制 → AR / VR → 设备与采集”，使用“RD数据桥配置”。USB / Wi-Fi 的配对步骤及构建说明见 [RD README](../VR%20remote%20control/README.md)。不需要为本次目录整理重新安装头显应用。

## 检查

```bash
bash scripts/test.sh
S1_STUDIO_CHROME_TESTS=1 bash scripts/test.sh
S1_STUDIO_DESKTOP_TESTS=1 bash scripts/test.sh
```

Chrome / Electron 检查需要对应运行环境；后者还需要图形桌面。检查默认使用隔离配置与模拟设备，不以自动测试替代现场真机验证。

2026-11-19 适配更新：RS 真机检测、状态与运动通信已归入本地旧 SDK 的 `safe_can` 扩展；原生高层控制仍保留。初始化行为、占用和终端切换规则见 [共用旧 SDK](shared-old-sdk.md)。
