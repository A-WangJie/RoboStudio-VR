"""VR command routing. Physical motion is owned exclusively by the RS service."""
import json
import math
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
try:
    from .pose_controls import PoseControls, angle
    from .mapping import Mapping
except ImportError:
    from pose_controls import PoseControls, angle
    from mapping import Mapping

class SimulationLink:
    def __init__(self, telemetry, request=None):
        self.telemetry = telemetry
        self.lock = threading.RLock()
        self.port = 8765
        self.request = request or self.http
        self.enabled = False
        self.message = '未启用仿真跟随'
        self.base = None
        self.last_target = None
        self.revision = None
        self.sent = 0
        self.viewer_seen = 0
        self.closed = threading.Event()
        self.last_tick = None
        self.orientation_enabled = False
        self.gripper_enabled = False
        self.rotation = None
        self.gripper = None
        self.pose_controls = PoseControls()
        self.mode_state = {}
        self.mode_received_ms = None
        self.next_mode_poll = 0.
        self.hardware_state = {}

    def hardware_status(self):
        try:
            result=self.request('/api/hardware/vr/state')
            if 'selected' in result:self.hardware_state=result
        except Exception:
            if self.hardware_state.get('selected'):
                raise ValueError('RS 真机 VR 服务断开，请在 RS 重新进入；不会自动切回仿真')
        return self.hardware_state

    def hardware_command(self,action):
        result=self.request('/api/hardware/vr/command',dict(action=action))
        self.hardware_state=result
        return self.snapshot()

    def mode_command(self, action):
        with self.lock:
            if self.hardware_status().get('selected'):
                if action=='vr_enter':raise ValueError('请在 RS 真机 VR 页面完成现场确认后进入')
                return self.hardware_command({'reset':'grasp','vr_exit':'exit','pause':'pause'}.get(action,action))
            self.disable()
            result = self.request("/api/sim/command", {"type": action})
            self.mode_state = result
            self.message = {"vr_exit":"已停止跟随 · 正在缓慢回零", "pause":"准备运动已暂停 · VR 模式保留"}.get(action, "正在移动到 VR 抓取位姿，到位后可启用跟随")
            return self.snapshot()

    def bind_port(self, port):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('仿真端口无效')
        with self.lock:
            if port == self.port: return
            if self.enabled or self.mode_state.get('vr_mode') or self.hardware_state.get('active'):
                raise ValueError('请先在原工作台退出 VR 模式，再切换工作台')
            self.port = port
            self.mode_state = {}
            self.hardware_state = {}

    def http(self, path, payload=None):
        req = Request(f'http://127.0.0.1:{self.port}'+path,
                      data=None if payload is None else json.dumps(payload).encode(),
                      headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}'})
        try:
            with urlopen(req, timeout=1) as r: return json.load(r)
        except HTTPError as e:
            try: msg = json.load(e).get('message', str(e))
            except Exception: msg = str(e)
            raise ValueError(msg) from e

    def snapshot(self, touch=False):
        with self.lock:
            if touch: self.viewer_seen = time.monotonic()
            h=self.hardware_state
            if h.get('selected'):
                return dict(online=bool(h.get('hardware')),enabled=h.get('enabled',False),message=h.get('message','真机 VR 已停止'),
                    sent=h.get('sent',0),vrMode=h.get('active',False),preparing=h.get('preparing',False),
                    execution='hardware',modeFault='',target=None,base=None,quaternion=None,
                    gripper=(h.get('hardware') or {}).get('simulation',{}).get('gripper'),
                    orientationEnabled=h.get('orientationEnabled',False),gripperEnabled=h.get('gripperEnabled',False))
            return dict(online=bool(self.mode_state), enabled=self.enabled, message=self.message, sent=self.sent,
                        vrMode=self.mode_state.get('vr_mode', False), preparing=self.mode_state.get('vr_preparing', False),
                        modeFault=self.mode_state.get('fault', ''), target=self.last_target, base=self.base, quaternion=self.rotation, gripper=self.gripper,
                        orientationEnabled=self.orientation_enabled, gripperEnabled=self.gripper_enabled)

    def disable(self, message='已停止仿真跟随 · 保持最后接受的姿态'):
        with self.lock:
            self.enabled = False
            self.message = message
            if self.hardware_state.get('selected') and self.hardware_state.get('active'):
                try:self.hardware_command('stop')
                except Exception:self.hardware_state.update(active=False,enabled=False,preparing=False,message='RS 真机 VR 状态待确认，请检查真机')

    def enable(self, orientation=False, gripper=False, position_gain=1.):
        mapping = Mapping(position_gain=position_gain)
        if type(orientation) is not bool or type(gripper) is not bool:
            raise ValueError("姿态和夹爪开关必须为布尔值")
        with self.lock:
            if self.hardware_status().get('selected'):
                return self.hardware_command('follow')
            self.enabled = False
            s = self.telemetry.snapshot()
            p = s['packet']
            if s['status'] != 'live' or not p or p['source'] != 'quest' or not p['focused'] or not p['right']['tracked']:
                raise ValueError('需要有效的 Quest 右手追踪数据')
            if p['right']['grip'] >= .3:
                raise ValueError('请先松开右握键，再启用仿真跟随')
            sim = self.request('/api/sim/state')
            if not sim.get('engine', '').startswith('MuJoCo'):
                raise ValueError('仅允许连接 MuJoCo 仿真')
            if sim['mode'] != 'kinematic' or not sim['collision_protection']:
                raise ValueError('请在工作台选择运动学模式，并开启碰撞保护')
            if not sim.get('vr_mode') or sim.get('vr_preparing'):
                raise ValueError('请先进入 VR 模式，等待到达抓取位姿再启用跟随')
            self.base = sim['tcp']
            self.last_target = list(self.base['position'])
            self.revision = sim['revision']
            self.orientation_enabled, self.gripper_enabled = orientation, gripper
            self.rotation = list(self.base['quaternion'])
            self.gripper = sim.get('target_gripper', 40.)
            self.pose_controls = PoseControls()
            with self.telemetry.lock:
                self.telemetry.mapping = mapping
            self.sent = 0
            self.last_tick = None
            self.viewer_seen = time.monotonic()
            self.enabled = True
            self.message = '已启用 · 从当前 TCP 开始，按住右握键移动'

    def tick(self):
        with self.lock:
            if not self.enabled: return
            if time.monotonic() - self.viewer_seen > 2:
                self.disable('监视页面离线 · 已停止，请重新启用')
                return
            now = time.monotonic()
            dt = max(0., min(.05, now-self.last_tick)) if self.last_tick is not None else 0.
            self.last_tick = now
            s = self.telemetry.snapshot()
            p, m = s['packet'], s['mapping']
            if (s['status'] != 'live' or s['error'] or not p or p['source'] != 'quest'
                or not p['focused'] or not p['right']['tracked']):
                self.disable('手柄断流或追踪失效 · 已停止，请松开握键后重新启用')
                return
            if not m['active']:
                with self.telemetry.lock:
                    self.telemetry.mapping.target = [a-b for a,b in zip(self.last_target,self.base['position'])]
                return
            goal = [a+b for a,b in zip(self.base['position'],m['offsetMeters'])]
            # Coalesce input: at most one request in flight, no queued poses.
            delta = [a-b for a,b in zip(goal,self.last_target)]
            length = math.sqrt(sum(x*x for x in delta))
            try:
                rotation, opening = self.pose_controls.goals(p['right'],m['clutchId'],self.rotation,self.gripper,
                    time.monotonic(),self.orientation_enabled,self.gripper_enabled)
            except ValueError as e:
                self.disable(str(e))
                return
            if length < .0002 and angle(rotation,self.rotation) < math.radians(.1) and abs(opening-self.gripper) < .1: return
            # Time-based speed cap and bounded step; slow IK must not accumulate a burst.
            ratio = min(1., min(.02, .4*dt)/length) if length else 1.
            target = [a+ratio*d for a,d in zip(self.last_target,delta)]
            try:
                result = self.request('/api/sim/command',dict(type='pose',frame='base',position=target,
                    quaternion=rotation,gripper=opening,position_only=False,expected_revision=self.revision))
                self.revision = result['revision']
                self.last_target = target
                self.rotation, self.gripper = rotation, opening
                self.sent += 1
                self.message = '仿真跟随中 · XYZ' + (' + 姿态' if self.orientation_enabled else ' · 姿态保持') + (' + 夹爪' if self.gripper_enabled else '')
            except Exception as e:
                self.disable('目标未接受，已停止：'+str(e))

    def run(self):
        while not self.closed.wait(.02):
            if time.monotonic() >= self.next_mode_poll:
                self.next_mode_poll = time.monotonic()+.25
                try:
                    hardware=self.hardware_status()
                    if hardware.get('selected'):
                        self.enabled=False
                        actual=(hardware.get('hardware') or {}).get('simulation',{})
                        with self.lock:
                            self.mode_state=dict(actual,execution='hardware',hardwareActive=hardware.get('active',False))
                            self.mode_received_ms=int(time.time()*1000)
                        continue
                    result = self.request('/api/sim/state')
                    with self.lock:
                        self.mode_state = result
                        self.mode_received_ms = int(time.time()*1000)
                        if self.enabled and (not result.get('vr_mode') or result.get('vr_preparing')):
                            self.disable('模式变更或复位中 · 到位后请重新启用跟随')
                except Exception:
                    with self.lock:
                        self.mode_state = {}
                        if self.enabled: self.disable('仿真服务断开')
            self.tick()
