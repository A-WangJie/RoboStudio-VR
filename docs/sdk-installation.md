# S1 SDK 与 DK 本地扩展

上游：https://github.com/YHRG-Robotics/S1_SDK_V2

## 授权和验证范围

2026-11-20 检查：上游 pyproject.toml 声明 MIT，仓库根目录未提供独立 LICENSE；未找到模型专门的再分发说明。因此公开源码默认不附上游模型、STL 或衍生碰撞数据。该处理不代表认定上游禁止再分发，待明确后可调整。

公开上游参考提交：`1c7b26f37288d37853eac2ece78ae69db4a7d701`。
这个提交仅用于固定获取来源，尚未验证其在新机器上的原生编译与真机兼容性；本机已验证的是既有旧 SDK 加本地扩展。不要将参考提交标为已验证安装版本。

## 新机器安装流程

下面是待完整复验的安装流程，不要在已有可用环境上重新安装：

```bash
git clone https://github.com/YHRG-Robotics/S1_SDK_V2.git /你的路径/S1_SDK_V2
git -C /你的路径/S1_SDK_V2 checkout 1c7b26f37288d37853eac2ece78ae69db4a7d701
# 先按上游说明准备编译工具和依赖，然后在 DK 使用的 Python 环境安装：
python -m pip install -e /你的路径/S1_SDK_V2
python tools/install_s1_extensions.py --sdk-root /你的路径/S1_SDK_V2
python tools/install_s1_extensions.py --sdk-root /你的路径/S1_SDK_V2 --apply
```

扩展安装器先预览，必须显式 --apply 才写入。只添加 safe_can.py、device_session.py、native_session.py；校验源码哈希，遇到不同版本的已有文件直接拒绝，不导入原生 SDK、不打开 CAN、不操作电机。

这三个文件是本项目自己的适配扩展，不是上游官方 API。RS 的 safe_can 调用依赖前两个；native_session 仅提供原生对象占用包装。安装它不会自动修改上游终端脚本：未显式使用 DeviceSession / OwnedNativeArm 的上游脚本不受共享锁约束。请勿同时运行这些原始终端脚本与 RS 真机控制。

## 模型恢复

确认有权使用你取得的模型资源后，在 DK 根目录运行：

```bash
python tools/import_s1_model.py --resource /你的路径/S1_SDK_V2/src/S1_SDK/resource
# 重新生成衍生碰撞数据，需额外安装离线生成依赖：
python -m pip install trimesh coacd==1.0.14
mkdir -p app/assets/s1_v1/collision
python tools/build_collision_meshes.py
```

未导入模型前，S1 仿真和模型相关测试不能正常工作。碰撞分解可能耗时。不要把生成后的第三方模型直接提交到 GitHub，直到其再分发授权得到确认。

## 测试范围

发布准备阶段会使用临时 SDK 包验证本地扩展导入、锁与模拟通信测试；不代表上游原生库全新安装成功，不代表真机运动经过验证。本机原 SDK、环境、标定和模型均保留。
