"""S1 V1 connection diagnostics. Only verified SDK-equivalent ping frames.

No motor SDK object is constructed; no enable/disable, motion or zero commands.
"""
import fcntl
from contextlib import contextmanager
import json
from pathlib import Path
import re
import select
import socket
import struct
import subprocess
import threading
import time
from backend.paths import data_dir

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r'[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,14}')


def validate_detection(value):
    if not isinstance(value, dict):
        raise ValueError('检测参数必须为对象')
    layout = value.get('layout')
    timeout = value.get('timeoutMs')
    arms = value.get('arms')
    if layout not in ('auto', 'single', 'dual'):
        raise ValueError('设备数量模式无效')
    if type(timeout) is not int or not 100 <= timeout <= 30000:
        raise ValueError('检测超时必须为 100–30000 ms 的整数')
    if not isinstance(arms, list) or len(arms) != 2:
        raise ValueError('检测需要 A、B 两个设备槽位')
    clean = []
    for index, arm in enumerate(arms):
        if not isinstance(arm, dict) or arm.get('id') != ('A', 'B')[index]:
            raise ValueError('设备槽位标识无效')
        device, bitrate, end = arm.get('device'), arm.get('bitrate'), arm.get('endEffector')
        if not isinstance(device, str) or not NAME.fullmatch(device):
            raise ValueError('CAN 接口名称无效')
        if bitrate is not None and (type(bitrate) is not int or not 10000 <= bitrate <= 1000000):
            raise ValueError('CAN 速率必须为 10000–1000000 或留空')
        if end not in ('None', 'gripper'):
            raise ValueError('末端类型无效')
        clean.append(dict(id=arm['id'], device=device, bitrate=bitrate, endEffector=end))
    if layout != 'single' and clean[0]['device'] == clean[1]['device']:
        raise ValueError('A、B 不能使用相同 CAN 接口')
    return dict(layout=layout, timeoutMs=timeout, arms=clean)


def list_interfaces():
    process = subprocess.run(['ip', '-j', '-details', '-statistics', 'link', 'show'],
                             capture_output=True, text=True, timeout=3, check=True)
    interfaces = []
    for item in json.loads(process.stdout):
        if item.get('link_type') != 'can':
            continue
        info = item.get('linkinfo', {}).get('info_data', {})
        counters = item.get('stats64', item.get('stats', {}))
        interfaces.append(dict(device=item['ifname'], up='UP' in item.get('flags', []),
            busState=info.get('state', 'UNKNOWN'), bitrate=info.get('bittiming', {}).get('bitrate'),
            rxPackets=counters.get('rx', {}).get('packets', 0), txPackets=counters.get('tx', {}).get('packets', 0),
            rxErrors=counters.get('rx', {}).get('errors', 0), txErrors=counters.get('tx', {}).get('errors', 0)))
    return interfaces


from S1_SDK.safe_can import parse_ping_reply, probe_can


class HardwareDiagnostics:
    def __init__(self, interface_reader=None, probe=None, lock_path=None):
        self.interface_reader = interface_reader or list_interfaces
        self.probe = probe or probe_can
        self.lock_path = Path(lock_path or data_dir()/'locks/hardware-detect.lock')
        self.lock = threading.Lock()

    def interfaces(self):
        return dict(interfaces=self.interface_reader(), sampledAtMs=int(time.time()*1000),
                    executionAvailable=False, stateReadingAvailable=True, motorModeAvailable=True)

    @contextmanager
    def exclusive(self):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('真机操作正在进行，请等待当前操作结束')
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open('a') as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise RuntimeError('另一工作台正在操作 CAN，请稍后重试') from error
                yield
        finally:
            self.lock.release()

    def detect(self, value):
        config = validate_detection(value)
        with self.exclusive():
            return self._detect(config)

    def _detect(self, config):
        interfaces = self.interface_reader()
        by_name = {row['device']:row for row in interfaces}
        arms = []
        for arm in config['arms']:
            row = dict(**arm, status='not_checked', message='', interface=by_name.get(arm['device']))
            info = row['interface']
            if config['layout'] == 'single' and arm['id'] == 'B':
                row.update(status='unused', message='单臂模式，B 不参与检测')
            elif info is None:
                row.update(status='missing_interface', message='未找到接口 '+arm['device'])
            elif not info['up']:
                row.update(status='interface_down', message='CAN 接口未启动；重新插拔后需重新配置并启动接口')
            elif info['busState'] in ('BUS-OFF', 'STOPPED', 'SLEEPING'):
                row.update(status='bus_fault', message='CAN 总线状态：'+info['busState'])
            elif arm['bitrate'] is not None and info['bitrate'] != arm['bitrate']:
                row.update(status='bitrate_mismatch', message=f"配置速率 {arm['bitrate']} 与接口实际 {info['bitrate']} 不一致，未发送探测")
            else:
                try:
                    result = self.probe(arm['device'], arm['endEffector'], config['timeoutMs'])
                    row.update(result)
                    online = not result['missingNodes']
                    row.update(status='online' if online else 'partial' if result['respondingNodes'] else 'no_response',
                        message='所需节点全部响应' if online else '缺少响应节点：'+', '.join(map(str, result['missingNodes'])))
                except (OSError, RuntimeError) as error:
                    row.update(status='probe_error', message='CAN 探测失败：'+str(error))
            row['checkedAtMs'] = int(time.time()*1000)
            arms.append(row)
        return dict(config=config, arms=arms, interfaces=self.interface_reader(), checkedAtMs=int(time.time()*1000),
                    detectedCount=sum(row['status']=='online' for row in arms), executionAvailable=False,
                    stateReadingAvailable=True, motorModeAvailable=True, message='检测完成；结果仅代表本次节点响应，未使能电机或读取关节角')
