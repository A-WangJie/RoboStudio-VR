"""S1 V1 / DM CAN status, explicit motor enable/disable, and bounded targets.

Frames and ranges verified against the installed motor_core damiao functions.
See docs/s1-can-protocol.md. No S1ARM constructor or native worker is used.
"""
import math
import select
import socket
import struct
import time
from .device_session import DeviceSession

FAULTS = {8:'过压',9:'欠压',10:'过流',11:'MOS 过温',12:'线圈过温',13:'通信丢失',14:'过载'}


def frame(can_id, data):
    return struct.pack('=IB3x8s', can_id, 8, data)


def state_query(node):
    return frame(0x7ff, struct.pack('<H',node)+b'\xcc\x00\x00\x00\x00\x00')


def motor_command(node, action):
    if action not in ('enable','disable'):
        raise ValueError('仅支持使能或失能')
    if type(node) is not int or not 1 <= node <= 8:
        raise ValueError('节点无效')
    return frame(node, b'\xff'*7+bytes([0xfc if action=='enable' else 0xfd]))


def position_velocity(node, position, velocity):
    """SDK damiao::control_pos_vel; SDK gripper position uses the opposite sign."""
    if type(node) is not int or not 1 <= node <= 7:
        raise ValueError('节点无效')
    if not all(type(v) in (int,float) and math.isfinite(v) for v in (position,velocity)):
        raise ValueError('位置与速度必须为有限数值')
    if abs(position)>math.pi or not 0 < velocity <= math.radians(10):
        raise ValueError('位置或速度超出真机鼠标控制范围')
    return frame(0x100+node, struct.pack('<ff', -position if node==7 else position, velocity))


def position_mode(node):
    if type(node) is not int or not 1 <= node <= 7:raise ValueError('节点无效')
    return frame(0x7ff, struct.pack('<H',node)+b'\x55\x0a\x02\x00\x00\x00')


def parse_state(raw, flags=0):
    if flags & socket.MSG_DONTROUTE or len(raw)!=16:
        return None
    can_id, length, data=struct.unpack('=IB3x8s',raw)
    if not 0x11 <= can_id <= 0x18 or length!=8:
        return None
    node=can_id-0x10
    if data[0]&15 != node:
        return None
    # A ping/register reply contains the full node ID followed by its register.
    if data[:4]==struct.pack('<H',node)+b'\x33\x0a':
        return None
    code=data[0]>>4
    if code not in (0,1,*FAULTS):
        return None
    p=(data[1]<<8)|data[2]
    v=(data[3]<<4)|(data[4]>>4)
    t=((data[4]&15)<<8)|data[5]
    position=p*25/65535-12.5
    # SDK gripper position sign is inverted; velocity/torque remain native.
    if node==7:position=-position
    vmax,tmax=(8.,28.) if node<=3 else (30.,10.)
    velocity=v*(2*vmax)/4095-vmax
    torque=t*(2*tmax)/4095-tmax
    return dict(node=node,positionRad=position,positionDeg=math.degrees(position),
        positionValid=abs(position)<=math.pi+.001,
        velocityRadS=velocity,torqueNm=torque,mosTemperatureC=data[6],coilTemperatureC=data[7],
        stateCode=code,enabled=code==1,state='已使能' if code==1 else '已失能' if code==0 else FAULTS[code],
        fault=code>=8,receivedAtMs=int(time.time()*1000))


class S1Can:
    def __init__(self, device, socket_factory=None):
        self._session = DeviceSession(device) if socket_factory is None else None
        self.socket = None
        try:
            if self._session: self._session.acquire()
            self.socket=(socket_factory or socket.socket)(socket.AF_CAN,socket.SOCK_RAW,socket.CAN_RAW)
            self.socket.bind((device,));self.socket.setblocking(False)
            # Only these external response identifiers reach the parser.
            # CAN_ERR_FLAG in a mask selects the error-frame subscription path.
            # Use the documented standard-ID mask, excluding EFF and RTR frames.
            mask=socket.CAN_SFF_MASK | socket.CAN_EFF_FLAG | socket.CAN_RTR_FLAG
            filters=b''.join(struct.pack('=II',0x10+n,mask) for n in range(1,9))
            self.socket.setsockopt(socket.SOL_CAN_RAW,socket.CAN_RAW_FILTER,filters)
        except Exception:
            if self.socket: self.socket.close()
            if self._session: self._session.close()
            raise

    def close(self):
        try:
            if self.socket: self.socket.close()
        finally:
            if self._session: self._session.close()

    def read(self, nodes, timeout_ms, interval=.02):
        # Discard replies already queued before this read, including command ACKs.
        for _ in range(4096):
            try:self.socket.recvmsg(72)
            except BlockingIOError:break
        started=time.monotonic();deadline=started+timeout_ms/1000
        sent=set();samples={};next_index=0
        attempts={};sent_at={};next_send=started
        while time.monotonic()<deadline:
            now=time.monotonic();node=None
            if now>=next_send:
                if next_index<len(nodes):
                    node=nodes[next_index];next_index+=1
                else:
                    # Re-query only missing nodes, within the original deadline.
                    # A dropped status/query must not require a new session;
                    # sustained loss still returns an incomplete snapshot.
                    node=next((n for n in nodes if n not in samples and attempts[n]<3
                        and now-sent_at[n]>=max(.02,interval)),None)
            if node is not None:
                self.socket.send(state_query(node));sent.add(node)
                attempts[node]=attempts.get(node,0)+1;sent_at[node]=now
                # Pace by the actual send time, even after a scheduling delay.
                next_send=now+interval
            for _ in range(256):
                try:raw,_,flags,_=self.socket.recvmsg(72)
                except BlockingIOError:break
                sample=parse_state(raw,flags)
                if sample and sample['node'] in sent:
                    samples[sample['node']]=sample
            if len(samples)==len(nodes):break
            select.select([self.socket],[],[],min(.01,interval,max(0,deadline-time.monotonic())))
        return [samples[n] for n in nodes if n in samples]

    def move(self, positions, velocity, initialize=False):
        # Validate the complete batch before the first write. Never enable here.
        frames=[(position_mode(n),position_velocity(n,p,velocity)) for n,p in positions.items()]
        for mode,target in frames:
            if initialize:self.socket.send(mode)
            self.socket.send(target)

    def command(self, nodes, action):
        sent=[];errors=[]
        for node in nodes:
            try:self.socket.send(motor_command(node,action))
            except OSError as error:
                errors.append(f'节点 {node}：{error}')
                if action=='enable':break
                continue
            sent.append(node)
            time.sleep(.01)
        return sent,'；'.join(errors) if errors else None


def parse_ping_reply(raw, flags=0):
    if flags & socket.MSG_DONTROUTE or len(raw) != 16: return None
    can_id, length, data = struct.unpack('=IB3x8s', raw)
    if not 0x11 <= can_id <= 0x18 or length != 8: return None
    node = can_id - 0x10
    if data[:4] != struct.pack('<H', node) + b'\x33\x0a': return None
    return node if int.from_bytes(data[4:], 'little') in (1, 2) else None


def probe_can(device, end_effector, timeout_ms):
    nodes = list(range(1, 7))
    if end_effector in ('gripper', 'teach'): nodes.append(7 if end_effector == 'gripper' else 8)
    seen, sent = set(), []
    started = time.monotonic()
    transport = S1Can(device)
    try:
        while time.monotonic() - started < timeout_ms / 1000:
            if len(sent) < len(nodes) and time.monotonic() - started >= .1 * len(sent):
                node = nodes[len(sent)]
                transport.socket.send(frame(0x7ff, struct.pack('<H', node) + b'\x33\x0a\0\0\0\0'))
                sent.append(node)
            for _ in range(256):
                try: raw, _, flags, _ = transport.socket.recvmsg(72)
                except BlockingIOError: break
                node = parse_ping_reply(raw, flags)
                if node in sent: seen.add(node)
            if set(nodes) <= seen: break
            select.select([transport.socket], [], [], min(.02, max(0, started + timeout_ms / 1000 - time.monotonic())))
    finally: transport.close()
    return dict(requiredNodes=nodes, respondingNodes=sorted(seen), sentNodes=sent,
                missingNodes=sorted(set(nodes)-seen), elapsedMs=round((time.monotonic()-started)*1000))


def required_nodes(end_effector):
    if end_effector not in ('None', 'gripper', 'teach'):
        raise ValueError('安全 CAN 接口支持 None / gripper / teach；mix 请使用原生控制接口')
    return list(range(1, 7)) + ([7] if end_effector == 'gripper' else [8] if end_effector == 'teach' else [])


def set_motor_state(device, end_effector, action, timeout_ms=2000):
    if action not in ('enable', 'disable'): raise ValueError('无效电机操作')
    nodes = required_nodes(end_effector)
    transport = S1Can(device)
    try:
        if action == 'enable':
            samples = transport.read(nodes, timeout_ms)
            if len(samples) != len(nodes) or any(s['fault'] or not s['positionValid'] for s in samples):
                raise RuntimeError('使能前检查未通过：节点缺失、故障或角度异常；未发送使能')
            targets = [s['node'] for s in samples if not s['enabled']]
        else: targets = nodes
        sent, error = transport.command(targets, action)
        samples = transport.read(nodes, timeout_ms)
        verified = len(samples) == len(nodes) and not error and all(not s['fault'] and s['enabled'] == (action == 'enable') for s in samples)
        return dict(verified=verified, sentNodes=sent, sendError=error, samples=samples,
                    missingNodes=sorted(set(nodes)-{s['node'] for s in samples}))
    finally: transport.close()
