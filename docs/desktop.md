# S1 Studio 桌面版 · 0.3.0

## 启动与退出

Ubuntu 应用程序菜单搜索 **S1 Studio 机器人工作台**，点击启动。也可以在本项目运行 `./S1Studio` 或 `bash start-desktop.sh`。软件使用自己的 Electron 窗口，不显示浏览器地址栏，不需要手动启动终端服务。原生菜单包括文件、编辑、视图、仿真、工具和帮助。

窗口启动时自动创建专属 MuJoCo 进程，使用本机随机空闲端口，避免与网页调试版的 8765 冲突。关闭窗口或选择“文件 → 退出”时会先暂停仿真，再结束该专属后端、释放端口。仅会结束本软件创建的后端。重复启动会聚焦已有窗口；窗口尺寸和最大化状态会保留。

当前是可直接使用的 **Ubuntu x86_64 本机桌面开发版**。Electron 运行时随项目保存，MuJoCo 后端使用本机已有的 Python 环境；不是已经包含所有 Python 依赖、可直接分发到任意电脑的安装包。保留源码和外部配置是为了继续方便调试 VR。所有程序资源、配置和日志都在项目内；应用菜单中只注册一个指向本目录的启动项。

## 软件操作

| 入口 | 操作 |
| --- | --- |
| 文件 → 打开 / 保存 / 另存为 | `.s1studio` 工作区文件；Ctrl+O / Ctrl+S / Ctrl+Shift+S |
| 工具栏 → 平移目标 / 旋转目标 | 打开末端控制页，切换三维手柄 |
| 仿真 → 开始 / 暂停 | F5 / F6；开始操作会切换到动力学模式 |
| 视图 → 透视 / 正视 / 侧视 / 俯视 | Alt+1 / Alt+2 / Alt+3 / Alt+4 |
| 视图 → 适应模型 / 全屏 | F8 / F11 |
| 视图 → 场景面板 / 控制面板 / 事件记录 | 显示或隐藏对应区域 |
| 工具 → 设置 | Ctrl+,；调整速度、逆解容差和启动开关 |
| 工具 → 打开日志文件夹 | 查看后端及启动错误 |
| 工具 → 开发者工具 | F12，用于继续开发调试 |
| 帮助 → 使用说明 / 关于 | 操作说明、软件和运行时版本 |

编辑菜单中的撤销 / 重做针对文本输入，不是机械臂运动轨迹撤销。

## 项目树与图标工具栏

项目树保留原有对象：`RoboDK → S1 Base → S1 V1 → 关节 / 平行夹爪 / TCP`，并在 S1 Base 下增加当前项目文件及功能目录；文件名、路径和当前页面会随工作区与页面切换同步。当前末端目标位于基座坐标系下，工作平面位于工作区下。多级菜单与项目树说明见 [project-navigation.md](project-navigation.md)。三角箭头展开或折叠子项；单击节点选择并打开对应现有控制。关节组默认折叠，展开后可选择 J1～J6，右侧高亮对应角度项。树支持方向键导航、左右键展开 / 收起、Enter 激活。选择和展开不会主动发送运动命令。

桌面窗口自上而下为工作区信息栏、文字菜单栏、图标工具栏。文字菜单调用原有原生子菜单，保留已有菜单动作与快捷键。

顶部使用白底工具栏和彩色立体矢量图标，以分隔线组织文件、视图、机械臂控制、仿真、工具五组图标。悬停显示名称和已有快捷键；视角、网格、坐标轴及拖拽模式有选中状态。再次点击已启用的平移 / 旋转图标关闭手柄。原生菜单和右侧控制继续可用。运行图标启动现有 MuJoCo 动力学仿真，重置图标调用现有仿真重置。

当前末端目标是本次位姿输入 / 手柄的入口，不是多目标点管理；没有新增程序、MoveJ、轨迹、运动撤销或测量功能。工作区文件格式不变，根节点名称随保存 / 打开同步。

界面模块：`app/js/project-tree.js`（对象导航），`app/js/icons.js`（树节点图标），`app/js/toolbar-icons.js`（工具栏彩色工程图标），`app/project-navigation.css`（树及紧凑工具栏）。深色属性面板保持现有配置。三维场景使用浅蓝灰背景、灰色反射地面及深灰 / 银灰机械臂材质，夹爪保持金属色；网格默认关闭，可由工具栏开启。倒影使用 Three.js r170 Reflector（同 MIT 许可），1024×1024 离屏渲染；Canvas 降级模式不提供倒影。显示底板仅为视觉对象，不改变碰撞模型。

## 工作区文件

保存工作区时先暂停仿真，记录实际的六关节、夹爪、相机位置 / 观察点和障碍物开关。默认保存位置是 `workspaces/`，也可在系统文件对话框中选择其他位置。

打开时校验格式和机器人型号，暂停仿真、切换到运动学模式，再通过现有碰撞检查应用姿态。文件本身不会绕过碰撞保护；若当前到保存姿态的关节插值路径被拦截，打开会报告失败。保存的是位姿快照，不包含速度、接触约束状态、物理时间或完整 MuJoCo 动力学快照。它也不是运动程序或轨迹文件。

## 后续修改参数

设置位于 `.local/config/settings.json`。设置窗口中的“保存并应用”会先暂停，验证参数，再更新后端并原子保存配置，下一次启动继续使用，无需重新封装桌面应用。

| 参数 | 默认值 | 可调范围 |
| --- | --- | --- |
| `simulation.speed_rad_s` | 0.6 rad/s | 0.01～2，动力学参考目标斜坡 |
| `simulation.ik_position_tolerance_mm` | 0.5 mm | 0.01～5 |
| `simulation.ik_orientation_tolerance_deg` | 1° | 0.01～10 |
| `simulation.collision_protection` | true | 碰撞拦截及启动默认值 |
| `simulation.obstacle` | false | 测试障碍物及启动默认值 |
| `pythonPath` | 空字符串 | 空值自动寻找已安装的 Python；更改后重启 |

`S1_STUDIO_PYTHON` 环境变量优先于 `pythonPath`；当前机器默认自动选用 `本机 runtime.json 中保存的 Python`。换电脑时需要安装 `requirements-simulation.txt` 中的依赖，并指定可用 Python。配置错误会明确提示启动失败；详细信息保存在日志中。

TCP、网格、关节定义、动力学增益仍由模型和后端代码管理；当前设置窗口没有提供这些标定选项。VR 功能已接入，当前说明见 RD README。

## 目录与继续开发

```text
S1Studio                      直接启动入口
start-desktop.sh              桌面启动脚本
install-desktop.sh            注册 Ubuntu 应用程序菜单
S1 Studio.desktop             本机生成的启动项（不提交）
desktop/main.cjs              原生菜单、窗口、文件对话框和应用生命周期
desktop/preload.cjs           受限桌面桥接接口
desktop/backend.cjs           专属 Python 后端启动、暂停和退出
desktop/config.cjs            设置 / 工作区校验与原子写入
desktop/runtime/              官方 Electron 45.3.1，包含上游许可证
desktop/runtime-lock.json     固定下载地址与官方 SHA-256
app/js/workbench.js            工具栏、设置、工作区和菜单动作
app/workbench.css              桌面工作台样式
.local/config/settings.json          外部可编辑配置
.local/config/window-state.json      自动保存的窗口状态
.local/electron/                 此软件独立的 Chromium 数据
artifacts/logs/desktop.log           桌面和 MuJoCo 后端日志
```

修改前端代码后，可用“工具 → 重新加载界面”；会先暂停当前仿真。修改 Python 或 Electron 主进程后关闭并重启软件。更新界面 / 算法仍然编辑当前这一套源码，不需要重写桌面版。网页调试继续使用 `bash start-studio.sh` 和 Google Chrome；浏览器版不具备桌面文件对话框及窗口退出时的后端管理。

移动项目目录后运行 `bash install-desktop.sh` 更新菜单启动项。恢复运行时可使用 `python3 tools/install_desktop_runtime.py`，或加 `--archive /路径/官方.zip` 使用本地文件；安装工具会按固定哈希校验，并拒绝覆盖已有运行时。

## 验证与边界

`tests/test_desktop.py` 启动真实 Electron 和 MuJoCo，使用临时配置、临时 Chromium 数据以及测试专用 SwiftShader，不修改日常配置。检查沙箱桥接、原生菜单、末端逆解、平移 / 旋转动作、设置持久化、工作区保存恢复、仿真运行暂停，以及关闭运行中窗口后后端 PID 和端口都消失。文件对话框的文件选择在自动测试中使用固定临时路径。

记录见 `desktop-checks.json`；`desktop-stage3.png` 和 `desktop-settings.png` 为 Electron 内容区域截图，不包含操作系统标题栏和原生菜单区域。默认实际运行不添加 SwiftShader 或禁用沙箱参数。

桌面化保留当前标定边界：TCP 未实物标定，碰撞采用凸包和离散采样。软件关闭管理的是其专属本机仿真，不代表已经具备真机紧急停止功能。

## 分类功能页

顶部“机械臂控制”位于“机械臂配置”右侧；展开后二级分类依次为“从臂示教 → 鼠标控制 → AR / VR”，点击箭头展开第三级原有功能，选择后在右侧显示对应页面。鼠标控制包含关节控制、末端位姿与三维拖拽；夹爪开合合并在关节控制页底部，项目树中的夹爪入口直接定位到该区域。仿真包含运行、暂停、重置、模式与碰撞设置；数据包含事件记录和项目模型信息；设置与帮助包含工作台参数及说明。

切换页面不发送运动命令。仿真运行按钮保留原有切换动力学并运行的语义；暂停及重置仍需主动点击。关节页包含原有恢复初始姿态按钮，末端页包含平移 / 旋转手柄设置。菜单支持上下方向键、Escape 关闭、点击外部关闭。项目树和原生菜单同步打开相应右侧页。参数保存与退出、后端管理逻辑沿用原实现。

共享目录位于 `app/js/navigation.js`，多级菜单位于 `app/js/function-menu.js`；页面组织和样式位于 `app/js/function-pages.js` 和 `app/function-pages.css`；移动已有控件并保留事件及实时数据，不复制机器人状态。


### Linux 图形诊断日志

RoboStudio 在 Linux 下关闭硬件视频编解码探测，避免 Electron 45 与较旧 libva ABI 不兼容。三维场景仍使用 WebGL 硬件加速。

启动器将原生 Electron／图形驱动的标准错误保存到 `artifacts/logs/electron.log`，超过 1 MiB 后在下次启动时保留一份 `.previous`。工作台与后端日志仍在 `artifacts/logs/desktop.log`。可用 `S1_STUDIO_DEBUG=1 bash start-desktop.sh` 将原生诊断直接输出到终端，集成测试也保留终端诊断。

部分 NVIDIA / X11 环境仍会记录 Mesa 备用 GBM 驱动探测失败；日志归档不代表修复了该驱动探测问题。确认 WebGL 的实际渲染器为 NVIDIA 后，无需为此关闭 GPU 沙箱或修改系统驱动目录权限。


工程整理后，本文提到的检查 JSON 统一位于 `artifacts/reports/`，生成截图位于 `artifacts/screenshots/`；这些本机材料不随源码导出。当前路径与配置以 [配置说明](configuration.md) 为准。
