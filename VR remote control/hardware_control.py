"""Quest-to-S1 adapter owned by RS. No CAN transport outside shared HardwareMotion."""
import json
import math
import threading
import time
from urllib.request import urlopen

import numpy as np

from bridge.mapping import Mapping
from bridge.pose_controls import PoseControls, angle


class VRHardwareControl:
    INPUT_MAX_MS=250
    VIEW_LEASE=1.5

    def __init__(self,motion,telemetry=None,start_worker=True,clock=None):
        self.motion=motion;self.telemetry=telemetry or self.http_telemetry
        self.clock=clock or time.monotonic;self.autoworker=start_worker
        self.lock=threading.RLock();self.selected=False;self.active=False
        self.enabled=False;self.preparing=False;self.phase='off';self.message='真机 VR 未开启'
        self.viewer_token=None;self.generation=0;self.sequence=0;self.sent=0
        self.mapping=Mapping();self.pose_controls=PoseControls();self.last_packet=None
        self.next_poll=threading.Event();self.thread=None;self.control_key=None
        self.ui_paused=False;self.preparation_interrupted=False

    @staticmethod
    def http_telemetry():
        with urlopen('http://127.0.0.1:8767/api/telemetry',timeout=.3) as response:return json.load(response)

    def _live(self,allow_ui=False):
        s=self.telemetry();p=s.get('packet');age=s.get('ageMs')
        if s.get('status')!='live' or s.get('error') or type(age) not in (int,float) or not 0<=age<=self.INPUT_MAX_MS:
            raise ValueError('VR 数据过期或断流，请检查 RD 连接后重新开启真机 VR')
        if not p or p.get('source')!='quest' or p.get('focused') is not True:
            raise ValueError('需要 Quest 真机在前台的有效数据')
        hand=p.get('right',{})
        if hand.get('connected') is not True or hand.get('tracked') is not True:
            raise ValueError('右手柄未连接或追踪无效')
        if p.get('uiInteracting') and not allow_ui:
            raise ValueError('手柄射线正在 RD 界面上；请移开射线、松开右握键后重试')
        if s.get('network',{}).get('extraDelayMs',0)>150:
            raise ValueError('无线数据积压超过 150 ms，已停止跟随，避免执行旧动作')
        # Use the bridge protocol validator too, rather than trusting arbitrary JSON.
        from bridge.protocol import validate
        validate(p)
        return s,p

    def state(self):
        with self.lock:
            return dict(selected=self.selected,active=self.active,enabled=self.enabled,preparing=self.preparing,
                uiPaused=self.ui_paused,
                phase=self.phase,message=self.message,sent=self.sent,execution='hardware' if self.selected else 'simulation',
                orientationEnabled=getattr(self,'orientation',True),positionOnly=getattr(self,'position_only',False),gripperEnabled=getattr(self,'gripper_enabled',False),
                positionGain=getattr(self,'gain',1),armId=getattr(self,'arm_id',None),
                tracking=getattr(self,'tracking',None),
                hardware=self.motion.state() if self.selected else None,
                offsetMeters=self.mapping.snapshot()['offsetMeters'])

    def _send(self,command=None):
        self.sequence+=1
        return self.motion.input(dict(token=self.control_key,sequence=self.sequence,command=command))

    def _hold(self):
        self.returning_zero=False
        result=self._send(dict(type='hold'));sim=result['simulation']
        self.base=sim['tcp'];self.last_target=list(self.base['position'])
        self.rotation=list(self.base['quaternion']);self.opening=sim['gripper']
        self.mapping=Mapping(self.gain);self.pose_controls=PoseControls();self.clutched=False
        self.tracking=None

    def _prepare(self):
        self.ui_paused=False;self.preparation_interrupted=False
        self.enabled=False;self.preparing=True;self.phase='preparing';self.settled=0
        self.returning_zero=False
        grip=40. if self.motion.gripper else self.motion.target_grip
        self._send(dict(type='joints',joints=list(self.motion.simulation.spec['vrGrabRadians']),gripper=grip))
        self.message='真机正按限速移动到 VR 抓取位姿；到位后松开握键，再按 A 启用跟随'

    def _return_zero(self):
        # An explicit zero/exit request uses the same feedback, path and servo
        # limits as every real target. Stop is a separate immediate hold.
        self._hold()
        self.enabled=False;self.preparing=True;self.phase='returning-zero';self.settled=0
        self.returning_zero=True;self.ui_paused=False;self.preparation_interrupted=False
        try:
            self._send(dict(type='joints',joints=[0.]*6))
        except Exception:
            self.stop('回零路径未通过检查，真机已停止，未绕过保护')
            raise
        self.message='已停止跟随 · 真机正在限速回零，到位后退出 VR；停止按钮可取消回零'

    def _pause_for_ui(self):
        if self.ui_paused:return
        interrupted=self.preparing
        self._hold() # Cancel the old destination before preserving the session.
        self.preparation_interrupted=interrupted
        self.ui_paused=True;self.enabled=False;self.preparing=False;self.phase='ui-paused'
        self.message='手柄射线指向 RD 界面，已暂停运动，VR 会话保留；移开射线并松开右握键后，'+(
            '按 B 重新移至抓取位姿' if interrupted else '按 A 重新启用跟随')

    def start(self,value):
        with self.lock:
            if self.active:raise ValueError('真机 VR 已开启')
            if not isinstance(value,dict):raise ValueError('需要控制参数')
            if any(type(value.get(k,default)) is not bool for k,default in (('orientation',True),('gripperEnabled',False),('positionOnly',False))):
                raise ValueError('姿态和夹爪开关无效')
            gain=value.get('positionGain',1);Mapping(gain)
            _,p=self._live()
            if p['right']['grip']>=.3:raise ValueError('请先松开右握键，再进入真机 VR 模式')
            if value.get('gripperEnabled') and value.get('gripper') is None:raise ValueError('扳机控制夹爪前必须配置实际闭合／张开电机角度')
            result=self.motion.start(value,owner='vr')
            try:
                self.control_key=result['token'];self.viewer_token=__import__('secrets').token_urlsafe(24)
                self.sequence=0;self.gain=float(gain);self.position_only=value.get('positionOnly',False)
                self.orientation=value.get('orientation',True) and not self.position_only
                self.gripper_enabled=value.get('gripperEnabled',False);self.arm_id=value['armId']
                self.selected=True;self.active=True;self.viewer_seen=self.clock();self.last_packet=None;self.sent=0
                self.mapping=Mapping(gain);self.clutched=False;self.last_target_time=self.clock();self._prepare()
                self.generation+=1;generation=self.generation
                if self.autoworker:
                    self.thread=threading.Thread(target=self._run,args=(generation,),daemon=True,name='rs-vr-hardware');self.thread.start()
                state=self.state();state['viewerToken']=self.viewer_token
                return state
            except Exception:
                self.stop('进入真机 VR 失败，已撤销控制');raise

    def touch(self,value):
        with self.lock:
            if not self.active or not isinstance(value,dict) or value.get('viewerToken')!=self.viewer_token:
                raise ValueError('真机 VR 页面会话已失效，请重新进入')
            self.viewer_seen=self.clock()
            return self.state()

    def choose_simulation(self):
        with self.lock:
            if self.active:raise ValueError('请先停止真机 VR，再切换到仿真')
            self.selected=False;self.message='真机 VR 已退出，当前为仿真控制';return self.state()

    def command(self,action,options=None):
        with self.lock:
            if action=='stop':
                return self.stop('已停止真机 VR，保持当前位置')
            if action in ('exit','zero') and not self.active:
                return self.stop('真机 VR 未开启，保持当前位置')
            if not self.active or not self.motion.active or self.motion.owner!='vr':raise ValueError('请先在 RS 中确认并进入真机 VR 模式')
            if self.clock()-self.viewer_seen>self.VIEW_LEASE:
                self.stop('RS 真机 VR 页面离线');raise ValueError(self.message)
            _,p=self._live(allow_ui=action in ('pause','exit','zero'))
            if action in ('exit','zero'):
                self._return_zero()
            elif action in ('grasp','reset'):
                self._hold();self._prepare()
            elif action=='follow':
                if self.preparing:raise ValueError('请等待真机到达抓取位姿后再启用跟随')
                if p['right']['grip']>=.3:raise ValueError('请先松开右握键，再按 A 启动／重置跟随')
                self._hold();self.mapping.update(p,True,self.clock());self.enabled=True;self.phase='following'
                self.ui_paused=False;self.preparation_interrupted=False
                self.message='真机 VR 跟随已启用 · 按住右握键运动，松开保持'
            elif action=='pause':
                if p.get('uiInteracting'):
                    self._pause_for_ui();return self.state()
                self._hold();self.enabled=False;self.preparing=False;self.phase='ready';self.message='真机 VR 已保持当前位置；按 A 重新启用'
                self.ui_paused=False
            else:raise ValueError('未知真机 VR 操作')
            return self.state()

    def stop(self,reason='已停止真机 VR，保持当前位置'):
        with self.lock:
            self.enabled=False;self.preparing=False;self.phase='off';self.active=False
            self.ui_paused=False
            self.viewer_token=None;self.message=reason;self.returning_zero=False;self.tracking=None
            if self.motion.active and self.motion.owner=='vr':self.motion.stop(reason)
            return self.state()

    def tick(self):
        with self.lock:
            if not self.active:return
            try:
                if self.clock()-self.viewer_seen>self.VIEW_LEASE:raise ValueError('RS 真机 VR 页面离线，已停止')
                if not self.motion.active or self.motion.owner!='vr':raise ValueError(self.motion.message)
                _,p=self._live(allow_ui=True)
                identity=(p['seq'],p['timeMs'])
                if self.last_packet and (identity[0]<self.last_packet[0] or identity[1]<self.last_packet[1]):
                    raise ValueError('RD 数据源重启或数据顺序异常，请重新进入真机 VR')
                self._send() # renew only while both Quest telemetry and RS page are healthy
                # Explicit zero is a preset, not a hand-driven target. Merely
                # hovering the UI must not cancel the exit just requested there.
                if p.get('uiInteracting') and not getattr(self,'returning_zero',False):
                    self._pause_for_ui();self.last_packet=identity;return
                if self.ui_paused:
                    self.ui_paused=False;self.phase='ready'
                    self.message='RD 界面操作已结束，真机保持当前位置；松开右握键后，'+(
                        '按 B 重新移至抓取位姿（原移动已取消）' if self.preparation_interrupted else '按 A 重新启用跟随')
                    self.last_packet=identity;return
                if self.preparing:
                    with self.motion.lock:
                        error=float(np.max(np.abs(self.motion.target-self.motion.actual)))
                        grip_error=abs(self.motion.target_grip-self.motion._grip(self.motion.samples)) if self.motion.gripper else 0
                    self.settled=self.settled+1 if error<math.radians(.5) and grip_error<1 else 0
                    if self.settled>=3:
                        if getattr(self,'returning_zero',False):
                            self.stop('真机已回到六轴零位 · VR 模式已退出');return
                        self._hold();self.preparing=False;self.phase='ready'
                        self.message='真机已到达抓取位姿 · 松开右握键，按 A 启用跟随'
                    self.last_packet=identity;return
                if not self.enabled:self.last_packet=identity;self.last_target_time=self.clock();return
                if identity==self.last_packet:return
                self.last_packet=identity
                now=self.clock()
                dt=max(0.,min(.05,now-self.last_target_time));self.last_target_time=now
                mapped=self.mapping.update(p,True,now)
                if not mapped['active']:
                    if self.clutched:
                        self._hold()
                        # Release is deliberate; next grasp must establish a fresh relative origin.
                        self.mapping.update(p,True,self.clock())
                    elif mapped['releaseRequired'] and p['right']['grip']>=.7:
                        raise ValueError('追踪位移跳变，请松开握键后按 A 重新启用')
                    return
                self.clutched=True
                actual=self.motion.state()['simulation']
                goal=[a+b for a,b in zip(self.base['position'],mapped['offsetMeters'])]
                # Integrate the requested pose like simulation, independently of noisy
                # encoder feedback. Bound its lead to the existing 20 mm step
                # envelope so a slow/blocked arm cannot queue a distant target.
                delta=np.asarray(goal)-np.asarray(self.last_target);length=float(np.linalg.norm(delta))
                # Match simulation's time-based Cartesian target stepping. Actual
                # joints still pass HardwareMotion speed/acceleration checks.
                ratio=min(1.,min(.02,.4*dt)/length) if length else 1.
                target=np.asarray(self.last_target)+ratio*delta
                lead=target-np.asarray(actual['tcp']['position'])
                lead_length=float(np.linalg.norm(lead))
                if lead_length>.02:target=np.asarray(actual['tcp']['position'])+lead*(.02/lead_length)
                target=target.tolist()
                rotation,opening=self.pose_controls.goals(p['right'],mapped['clutchId'],self.rotation,self.opening,
                    self.clock(),self.orientation,self.gripper_enabled)
                if np.linalg.norm(np.asarray(target)-np.asarray(actual['tcp']['position']))<.0001 and angle(rotation,actual['tcp']['quaternion'])<math.radians(.1) and abs(opening-actual['gripper'])<.1:return
                self._send(dict(type='pose',frame='base',position=target,quaternion=rotation,position_only=self.position_only,gripper=opening))
                self.last_target=target;self.rotation=rotation;self.opening=opening;self.sent+=1
                self.tracking=dict(positionErrorMm=round(float(np.linalg.norm(np.asarray(goal)-np.asarray(actual['tcp']['position'])))*1000,1),
                    targetLeadMm=round(min(lead_length,.02)*1000,1),
                    ikStepFraction=getattr(self.motion,'vr_step_fraction',1.),
                    speedDegS=math.degrees(self.motion.speed))
                self.message='真机 VR 跟随中 · 松开右握键保持'
            except Exception as error:self.stop('真机 VR 已停止：'+str(error))

    def _run(self,generation):
        while not self.next_poll.wait(.05):
            with self.lock:
                if generation!=self.generation or not self.active:return
            self.tick()
