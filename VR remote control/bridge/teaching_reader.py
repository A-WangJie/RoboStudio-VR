"""Isolated native SDK reader. Never invokes enable/control/gravity/zero APIs."""
import json
import math
import os
from pathlib import Path
import socket
import sys
import time
from teaching_capture import PREFIX, validate_options


def run(config):
    root = Path(os.environ.get('ROBODATA_S1_SDK', str(Path(__file__).resolve().parents[3]/'14-DOF robotic arm/S1_SDK_V2')))
    hardware = root/'src/S1_SDK/hardware'
    if not hardware.is_dir():
        raise ValueError('找不到 S1 SDK：'+str(hardware))
    monitors = []
    for device in config['devices']:
        interface = Path('/sys/class/net')/device
        if not interface.exists() or (interface/'type').read_text().strip() != '280':
            raise ValueError('未找到 CAN 接口 '+device+'；请连接示教臂并配置接口')
        if not int((interface/'flags').read_text().strip(), 16) & 1:
            raise ValueError('CAN 接口 '+device+' 未启动；请先配置速率并置为 UP')
        monitor = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        monitor.bind((device,)); monitor.setblocking(False)
        monitors.append(monitor)
    sys.path.insert(0, str(hardware))
    try:
        import motor_interface as sdk
    except ImportError as error:
        raise ValueError('无法加载 SDK 原生扩展；需匹配 Python 3.10 与依赖库：'+str(error))
    from readonly_guard import install
    install()  # SDK initialization may construct motor mode/disable frames: block all CAN writes.
    arms = [sdk.S1ARM(device, sdk.CommType.can, sdk.EndType.teach) for device in config['devices']]
    last_bus = [None]*len(arms)
    started = time.monotonic()
    seq = 0
    while True:
        tick = time.monotonic()
        for i, monitor in enumerate(monitors):
            # Only genuine received data frames count; exclude error/RTR frames.
            for _ in range(4096):
                try:
                    frame = monitor.recv(16)
                except BlockingIOError:
                    break
                if len(frame) == 16 and not int.from_bytes(frame[:4],sys.byteorder) & 0x60000000 and frame[4] > 0:
                    last_bus[i] = time.monotonic()
        if any(tick-(last or started) > config['timeoutMs']/1000 for last in last_bus):
            raise ValueError('CAN 总线无新反馈，采集已停止；检查供电、速率和示教臂连接')
        if all(last is not None for last in last_bus):
            samples = []
            for device, arm, last in zip(config['devices'], arms, last_bus):
                values = list(arm.get_position())
                if len(values) < 6 or not all(math.isfinite(v) for v in values):
                    raise ValueError('SDK 返回无效关节读数：'+device)
                samples.append(dict(device=device, jointsRad=values[:6], sdkPosition=values,
                    canAgeMs=round((time.monotonic()-last)*1000), perJointFreshnessVerified=False))
            print(PREFIX+json.dumps(dict(source='teaching-sdk', version=1, seq=seq, timeMs=int(time.time()*1000), arms=samples), allow_nan=False), flush=True)
            seq += 1
        time.sleep(max(0, 1/config['rateHz']-(time.monotonic()-tick)))


if __name__ == '__main__':
    try:
        run(validate_options(json.loads(sys.argv[1])))
    except Exception as error:
        print('ROBODATA_ERROR '+str(error), flush=True)
    finally:
        # The SDK destructor may send motor-close commands. The OS releases
        # sockets on exit; bypass native destructors in this read-only worker.
        os._exit(0)
