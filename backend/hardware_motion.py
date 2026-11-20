"""Opt-in, single-owner mouse/VR control. No implicit enable, disable or homing.

All hardware writes run under the diagnostic CAN reservation. Browser requests
provide targets, never frames. The controller bounds speed, acceleration and
following error against fresh motor feedback before each batch.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import secrets
import threading
import time

import numpy as np
from scipy.spatial.transform import Rotation

from backend.hardware import ROOT
from backend.paths import config_dir
from backend.simulation import CommandError, vector


def number(value, low, high, name):
    if type(value) not in (float,int) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError(f'{name} 必须在 {low}–{high} 范围内')
    return float(value)


def gripper_range(value, end_effector):
    if value is None:return None
    if end_effector!='gripper' or not isinstance(value,dict):raise ValueError('夹爪配置无效')
    closed=number(value.get('closedDeg'),-170,170,'夹爪闭合角')
    opened=number(value.get('openDeg'),-170,170,'夹爪张开角')
    if abs(opened-closed)<5:raise ValueError('夹爪行程至少为 5°，请使用已核对的实际角度')
    return [math.radians(closed),math.radians(opened)]


class HardwareMotion:
    PERIOD=.05
    LEASE=.7
    FEEDBACK_TIMEOUT=180
    ACCELERATION=math.radians(20)
    FOLLOWING_ERROR=math.radians(5)

    def __init__(self, operations, simulation, config_path=None, start_worker=True, clock=None):
        self.operations=operations
        self.simulation=simulation
        self.config_path=Path(config_path or config_dir()/'arms.json')
        self.autoworker=start_worker
        self.clock=clock or time.monotonic
        self.lock=threading.RLock()
        self.active=False
        self.token=None
        self.message='仅仿真 · 真机鼠标控制未开启'
        self.samples=[]
        self.feedback_status=None
        self.stopped_token=None
        self.transport=None
        self.reservation=None
        self.generation=0
        self.stopped=threading.Event()

    def settings(self):
        config=json.loads(self.config_path.read_text())
        calibrations={}
        path=self.config_path.parent/'gripper-calibration.json'
        if path.exists():
            saved=json.loads(path.read_text())
            for arm in config['arms']:
                item=saved.get('arms',{}).get(arm['id'])
                if item and item.get('device')==arm['device'] and arm['endEffector']=='gripper':
                    gripper_range(item,'gripper')
                    calibrations[arm['id']]=item
        return dict(config=dict(layout=config['connection']['layout'],timeoutMs=config['connection']['timeoutMs'],
            arms=[{k:a[k] for k in ('id','device','bitrate','endEffector')} for a in config['arms']]),
            defaultSpeedDegS=3,maxSpeedDegS=10,gripperCalibrations=calibrations)

    def _grip(self, samples):
        if not self.gripper:return self.simulation.gripper
        angle=next(s['positionRad'] for s in samples if s['node']==7)
        return float(np.clip((angle-self.gripper[0])/(self.gripper[1]-self.gripper[0])*100,0,100))

    def _read(self):
        started=time.monotonic()
        samples=self.transport.read(self.nodes,self.FEEDBACK_TIMEOUT,interval=.002)
        responding={s['node'] for s in samples}
        missing=sorted(set(self.nodes)-responding)
        self.feedback_status=dict(missingNodes=missing,respondingNodes=sorted(responding),
            elapsedMs=round((time.monotonic()-started)*1000,1),sampledAtMs=int(time.time()*1000))
        if missing:
            labels='、'.join('夹爪（节点 7）' if n==7 else f'J{n}（节点 {n}）' for n in missing)
            raise OSError(f'关节反馈不完整，缺少 {labels}；{self.FEEDBACK_TIMEOUT} ms 内未收到完整反馈，已停止下发；检查 CAN 后重新开启')
        if any(s['fault'] or not s['enabled'] or not s['positionValid'] for s in samples):
            raise OSError('节点失能、故障或角度异常，已停止下发；请检查真机状态')
        q=np.array([next(s['positionRad'] for s in samples if s['node']==n) for n in range(1,7)])
        limits=self.simulation.limits
        # Encoder quantization/zero offsets at the model boundary are shown as read.
        if np.any(q<limits[:,0]-math.radians(.5)) or np.any(q>limits[:,1]+math.radians(.5)):
            raise ValueError('实际关节角超出模型限位，请先核对零位和关节映射')
        if self.gripper:
            angle=next(s['positionRad'] for s in samples if s['node']==7)
            if not min(self.gripper)-math.radians(.5)<=angle<=max(self.gripper)+math.radians(.5):
                raise ValueError('实际夹爪角度超出配置行程；请核对闭合和张开角度')
        self.samples=samples
        self.feedback_at=self.clock()
        return q

    def _sync(self,q):
        sim=self.simulation
        with sim.lock:
            sim.mode='kinematic';sim.running=False
            sim.target=q.copy();sim.servo=q.copy()
            sim.gripper=self._grip(self.samples)
            sim._put(sim.data,q,sim.gripper)
            sim.revision+=1;sim.sequence+=1

    def _path(self,start,end,grip_start,grip_end):
        sim=self.simulation
        steps=max(1,int(np.ceil(np.max(np.abs(end-start))/math.radians(1))),int(np.ceil(abs(grip_end-grip_start)/2)))
        with sim.lock:
            for fraction in np.linspace(0,1,steps+1):
                sim._put(sim.scratch,start+(end-start)*fraction,grip_start+(grip_end-grip_start)*fraction)
                for contact in sim._contacts(sim.scratch):
                    # Permit only measured tiny assembly overlap already present at takeover.
                    allowance=self.baseline.get(tuple(contact['pair']),0)
                    if contact['penetration_mm']>allowance:
                        raise CommandError('COLLISION','真机目标路径存在模型碰撞，已拒绝目标',[contact])

    def start(self,value,owner='mouse'):
        with self.lock:
            if owner not in ('mouse','vr'):raise ValueError('控制来源无效')
            if self.active:raise RuntimeError('真机控制通道已被占用，请先停止')
            if not isinstance(value,dict) or value.get('confirmed') is not True:
                raise ValueError('请先确认目标机械臂、关节对应关系和现场状态')
            config,arm=self.operations._validate(value,'read')
            if config!=self.settings()['config']:
                raise ValueError('连接参数与已保存配置不同，请先保存机械臂配置并重新读取')
            speed=number(value.get('speedDegS',3),.5,10,'关节速度上限')
            gripper=gripper_range(value.get('gripper'),arm['endEffector'])
            with self.simulation.lock:
                if self.simulation.vr_mode or self.simulation.running:
                    raise ValueError('请先退出仿真 VR 模式并暂停动力学仿真，再开启真机控制')
            self.operations._check_interface(arm)
            self.reservation=self.operations.diagnostics.exclusive()
            self.reservation.__enter__()
            try:
                self.arm=arm;self.config=config;self.speed=math.radians(speed);self.gripper=gripper
                self.owner=owner
                self.nodes=list(range(1,8 if arm['endEffector']=='gripper' else 7))
                self.transport=self.operations.transport_factory(arm['device'])
                q=self._read()
                self.baseline={}
                with self.simulation.lock:
                    self.simulation._put(self.simulation.scratch,q,self._grip(self.samples))
                    for contact in self.simulation._contacts(self.simulation.scratch):
                        if contact['penetration_mm']>.2:raise ValueError('实际姿态存在明显模型碰撞，请核对安装和关节零位')
                        self.baseline[tuple(contact['pair'])]=contact['penetration_mm']+.02
                self._sync(q)
                self.actual=q.copy();self.target=q.copy();self.commanded=q.copy();self.velocity=np.zeros(6)
                self.target_grip=self._grip(self.samples)
                self.grip_command=next((s['positionRad'] for s in self.samples if s['node']==7),0.)
                self.grip_velocity=0.
                self.last_tick=self.last_client=self.clock();self.last_sequence=0
                self.initialized=False;self.has_target=False
                self.token=secrets.token_urlsafe(24);self.active=True
                self.generation+=1;generation=self.generation
                self.stopped=threading.Event()
                self.message=f'真机 {"VR" if owner=="vr" else "鼠标"} 控制已开启 · 已对齐实际姿态，等待输入'
                self.operations._audit(dict(action=owner+'-start',armId=arm['id'],device=arm['device'],speedDegS=speed,
                    gripper=gripper,sampledAtMs=int(time.time()*1000),message=self.message))
                if self.autoworker:
                    threading.Thread(target=self._run,args=(generation,self.stopped),daemon=True,name='s1-mouse-servo').start()
                result=self.state();result['token']=self.token
                return result
            except Exception:
                self._release()
                raise

    def _release(self):
        try:
            if self.transport:self.transport.close()
        finally:
            self.transport=None
            if self.reservation:
                self.reservation.__exit__(None,None,None);self.reservation=None

    def state(self):
        with self.lock:
            return dict(active=self.active,armId=getattr(self,'arm',{}).get('id'),device=getattr(self,'arm',{}).get('device'),
                owner=getattr(self,'owner',None),
                feedbackStatus=deepcopy(self.feedback_status),
                message=self.message,samples=deepcopy(self.samples),speedDegS=math.degrees(getattr(self,'speed',math.radians(3))),
                gripperAvailable=bool(getattr(self,'gripper',None)),simulation=self.simulation.state())

    def _authorize(self,value):
        if isinstance(value,dict) and not self.active and self.stopped_token and value.get('token')==self.stopped_token:
            # The heartbeat after an automatic stop must preserve its cause.
            raise ValueError(self.message)
        if not isinstance(value,dict) or not self.active or value.get('token')!=self.token:
            raise ValueError('真机控制会话已失效，请重新开启')
        seq=value.get('sequence')
        if type(seq) is not int or seq<=self.last_sequence:raise ValueError('控制请求顺序无效，拒绝旧目标')
        if self.clock()-self.last_client>self.LEASE:
            self._stop('控制页面通信超时，已停止下发',hold=True)
            raise ValueError(self.message)
        self.last_sequence=seq

    def input(self,value):
        with self.lock:
            self._authorize(value)
            try:return self._input(value)
            except Exception as error:
                self._stop('控制目标被拒绝，已停止跟随：'+str(error),hold=True)
                raise

    def _vr_pose(self, payload):
        """Retry a shorter Cartesian step instead of selecting a distant IK branch.

        The measured configuration is the seed on every attempt. Existing joint
        limits, swept collision checks and physical servo limits still apply.
        Caller holds the simulation lock. Never submit an unsafe fallback.
        """
        sim=self.simulation
        position=vector(payload.get('position'),3,'position（米）')
        quaternion=vector(payload.get('quaternion'),4,'quaternion（xyzw）')
        norm=float(np.linalg.norm(quaternion))
        if norm<1e-8:raise CommandError('INVALID_INPUT','目标四元数不能为零')
        if np.linalg.norm(position)>1.2:
            raise CommandError('UNREACHABLE','目标超出模型工作范围，保持上一姿态')
        actual_pose=sim.fk(self.actual,self._grip(self.samples))
        origin=np.asarray(actual_pose['position'])
        start_rotation=Rotation.from_quat(actual_pose['quaternion'])
        end_rotation=Rotation.from_quat(quaternion/norm)
        rotation_delta=(end_rotation*start_rotation.inv()).as_rotvec()
        previous=sim.target.copy()
        failure=None
        try:
            for fraction in (1.,.5,.25,.125,.0625):
                sim.target=self.actual.copy()
                target=origin+(position-origin)*fraction
                orientation=(Rotation.from_rotvec(rotation_delta*fraction)*start_rotation).as_quat()
                try:
                    q,_=sim._ik(target.tolist(),orientation.tolist(),payload.get('position_only',False))
                except CommandError as error:
                    if error.code!='IK_FAILED':raise
                    failure=error
                    continue
                if np.max(np.abs(q-self.actual))<=math.radians(15):
                    self.vr_step_fraction=fraction
                    return q
                failure=ValueError('缩小目标后末端逆解仍跳变过大，已停止；请核对姿态与关节零位')
            raise failure
        finally:
            sim.target=previous

    def _input(self,value):
        payload=value.get('command')
        configuring=False
        if payload is not None:
            if not isinstance(payload,dict) or payload.get('type') not in ('joints','pose','hold','preset','gripper-config'):
                raise ValueError('真机控制仅接受关节、末端或停止目标')
            if self.clock()-self.feedback_at>.25:raise ValueError('电机反馈已过期，请等待最新反馈')
            if payload['type']=='gripper-config':
                if self.owner!='mouse' or payload.get('confirmed') is not True:raise ValueError('请确认实际夹爪行程后再应用')
                limits=gripper_range(payload.get('gripper'),self.arm['endEffector'])
                if limits is None:raise ValueError('请填写实际夹爪闭合和张开角度')
                self._read()
                angle=next(s['positionRad'] for s in self.samples if s['node']==7)
                if not min(limits)-math.radians(.5)<=angle<=max(limits)+math.radians(.5):
                    raise ValueError('当前夹爪反馈不在配置行程内，请核对角度')
                self.gripper=limits
                configuring=True
                # Applying a range must cancel old targets, never move the jaw.
                payload=dict(type='hold')
            if payload['type']=='hold':
                self.actual=self._read()
                # Anchors must use this measurement, not the previous servo frame.
                self._sync(self.actual)
                self.target=self.actual.copy();self.commanded=self.actual.copy();self.velocity[:]=0
                self.target_grip=self._grip(self.samples);self.grip_command=next((s['positionRad'] for s in self.samples if s['node']==7),0.)
                self.grip_velocity=0.
                if configuring:
                    self.has_target=False
                    self.initialized=False # Node 7 needs its mode on the next explicit target too.
            else:
                with self.simulation.lock:
                    if payload['type']=='preset':
                        name=payload.get('name')
                        if name not in ('home','vr-grab'):raise ValueError('未知预设姿态')
                        q=np.array(self.simulation.spec['homeRadians' if name=='home' else 'vrGrabRadians'])
                        payload=dict(payload,gripper=40 if name=='vr-grab' and self.gripper else self.target_grip)
                    elif payload['type']=='joints':
                        raw=payload.get('joints')
                        if not isinstance(raw,list) or any(type(p) not in (int,float) for p in raw):raise ValueError('关节目标必须为有限数值数组')
                        q=vector(raw,6,'joints')
                    else:
                        if payload.get('frame','base')!='base':raise ValueError('只允许基座坐标系')
                        if 'position_only' in payload and type(payload['position_only']) is not bool:raise ValueError('仅位置开关无效')
                        for key in ('position','quaternion'):
                            raw=payload.get(key)
                            if not isinstance(raw,list) or any(type(p) not in (int,float) for p in raw):raise ValueError('末端目标必须为有限数值数组')
                        if self.owner=='vr':
                            q=self._vr_pose(payload)
                        else:
                            q,_=self.simulation._ik(payload.get('position'),payload.get('quaternion'),payload.get('position_only',False))
                        if np.max(np.abs(q-self.actual))>math.radians(15):raise ValueError('末端逆解跳变过大，请小幅拖动')
                    if np.any(q<self.simulation.limits[:,0]-1e-9) or np.any(q>self.simulation.limits[:,1]+1e-9):
                        raise ValueError('关节目标超出模型限位')
                    grip=number(payload.get('gripper',self.target_grip),0,100,'夹爪百分比')
                    if not self.gripper and abs(grip-self.target_grip)>.01:raise ValueError('真机夹爪行程尚未配置；请先填写闭合与张开电机角度')
                    self._path(self.actual,q,self._grip(self.samples),grip)
                self.target=q.copy();self.target_grip=grip
                self.has_target=True
        self.last_client=self.clock()
        return self.state()

    def stop(self,reason='已停止真机鼠标控制',hold=True):
        with self.lock:
            if self.active:self._stop(reason,hold)
            return self.state()

    def _stop(self,reason,hold):
        self.stopped_token=self.token
        self.active=False;self.token=None;self.stopped.set()
        hold_sent=False
        try:
            if hold and self.initialized and self.clock()-self.feedback_at<=.25:
                self._read()
                positions={s['node']:s['positionRad'] for s in self.samples if s['node']<=6 or self.gripper}
                self.transport.move(positions,self.speed)
                hold_sent=True
        except Exception as error:reason+='；保持指令未确认：'+str(error)
        finally:
            self.message=reason+'；电机使能状态不自动改变'
            self.operations._audit(dict(action=self.owner+'-stop',armId=self.arm['id'],device=self.arm['device'],
                message=self.message,holdSent=hold_sent,feedbackStatus=deepcopy(self.feedback_status),sampledAtMs=int(time.time()*1000)))
            self._release()

    @staticmethod
    def ramp(current,velocity,target,speed,dt):
        delta=target-current
        desired=np.sign(delta)*np.minimum(speed,np.sqrt(2*HardwareMotion.ACCELERATION*np.abs(delta)))
        velocity=velocity+np.clip(desired-velocity,-HardwareMotion.ACCELERATION*dt,HardwareMotion.ACCELERATION*dt)
        step=velocity*dt
        # Never accelerate past the latest requested target.
        step=np.where(step*delta<0,0,np.sign(delta)*np.minimum(np.abs(step),np.abs(delta)))
        return current+step,step/dt

    @staticmethod
    def coordinated_ramp(current,velocity,target,speed,dt):
        """Common joint progress keeps a VR Cartesian step from shearing.

        Preserve the same per-joint speed, acceleration and stopping envelope.
        Unlike independent clipping, a small wrist delta does not finish first
        while the shoulder is still catching up. Changing targets still ramp
        from the previous velocity rather than resetting on each packet.
        """
        delta=target-current
        distance=float(np.max(np.abs(delta)))
        if distance<1e-12:return target.copy(),np.zeros_like(velocity)
        rate=min(speed/distance,math.sqrt(2*HardwareMotion.ACCELERATION/distance))
        desired=delta*rate
        change=desired-velocity
        largest=float(np.max(np.abs(change)))
        fraction=min(1.,HardwareMotion.ACCELERATION*dt/largest) if largest else 1.
        velocity=velocity+change*fraction
        step=velocity*dt
        step=np.where(step*delta<0,0,np.sign(delta)*np.minimum(np.abs(step),np.abs(delta)))
        return current+step,step/dt

    def tick(self):
        with self.lock:
            if not self.active:return
            try:
                if self.clock()-self.last_client>self.LEASE:
                    self._stop('控制页面通信超时，已停止下发',True);return
                if self.settings()['config']!=self.config:
                    raise ValueError('已保存的机械臂连接配置已改变，请重新开启控制')
                self.operations._check_interface(self.arm)
                q=self._read();self.actual=q.copy();self._sync(q)
                now=self.clock();dt=min(.075,max(.001,now-self.last_tick));self.last_tick=now
                if not self.has_target:return
                if np.max(np.abs(self.commanded-q))>self.FOLLOWING_ERROR:
                    raise OSError('目标与实际关节偏差超过 5°，已停止下发；请检查受阻或关节映射')
                ramp=self.coordinated_ramp if self.owner=='vr' else self.ramp
                next_q,velocity=ramp(self.commanded,self.velocity,self.target,self.speed,dt)
                grip_start=self._grip(self.samples);grip_next=grip_start
                positions={i+1:float(p) for i,p in enumerate(next_q)}
                if self.gripper:
                    target=self.gripper[0]+self.target_grip/100*(self.gripper[1]-self.gripper[0])
                    actual_grip=next(s['positionRad'] for s in self.samples if s['node']==7)
                    if abs(self.grip_command-actual_grip)>self.FOLLOWING_ERROR:raise OSError('夹爪跟随偏差过大，已停止下发')
                    g,v=self.ramp(np.array([self.grip_command]),np.array([self.grip_velocity]),np.array([target]),self.speed,dt)
                    positions[7]=float(g[0]);grip_next=float(np.clip((g[0]-self.gripper[0])/(self.gripper[1]-self.gripper[0])*100,0,100))
                self._path(q,next_q,grip_start,grip_next)
                # No writes occur until the first explicit valid mouse target.
                self.transport.move(positions,self.speed,initialize=not self.initialized)
                self.initialized=True;self.commanded=next_q;self.velocity=velocity
                if self.gripper:self.grip_command=float(g[0]);self.grip_velocity=float(v[0])
                self.message=f'真机 {"VR" if self.owner=="vr" else "鼠标"} 控制中 · 画面显示实际反馈'
            except Exception as error:
                self._stop('真机跟随停止：'+str(error),False)

    def _run(self,generation,stopped):
        while not stopped.wait(self.PERIOD):
            with self.lock:
                if generation!=self.generation or not self.active:return
                self.tick()
