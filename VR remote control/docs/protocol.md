# 输入与采集协议

头显向 WebSocket 8766 `/input` 发送 JSON。Wi-Fi 模式需携带本机生成的 `?token=配对码`；USB 通过 adb reverse 访问回环地址。HTTP 状态与操作 API 仅绑定电脑本机 8767。

核心字段：`version=1`、`source=quest`、递增 `seq`、Unix 毫秒 `timeMs`、`focused`、`uiInteracting`、`left`、`right`。每只手包含 `connected`、`tracked`、位置三元组（米）、旋转四元数 XYZW、摇杆、0–1 扳机及握键、主／次按钮。

旋转和位置使用 Unity 本地追踪空间，不是世界绝对机械臂坐标。追踪无效、失焦、重启、乱序或数据过期不能继续作为目标。协议校验实现为 `bridge/protocol.py`，真机还有 DK 独立反馈和会话检查。

命令与遥测共用连接。命令消息含 `type=command`、`id`、`action`；接收端回应 `commandResult` 并携带 `ok` 和 `message`。延迟探测用 `latencyProbe / latencyResult`，往返时间与桥的额外排队延迟是不同指标。

录制为 JSONL：首行为 `header`，采样行为 `frame`，结束行为 `footer`。结束原因、帧数和采集任务一同记录；任务文件名以 RS 提交的任务名优先。格式详见 `bridge/recording.py` 和 `tests/test_robodata.py`。示教 SDK 采集使用独立 `source=teaching-sdk`，不冒充 Quest 数据。
