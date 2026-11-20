"""Choose one authorized USB device; never silently choose a wireless peer."""
import os
import subprocess


def usb_serial(runner=None):
    configured = os.environ.get('QUEST_SERIAL', '').strip()
    if configured:
        return configured
    result = (runner or subprocess.run)(['adb', 'devices'], capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError('无法读取 USB 设备：' + (result.stderr or '').strip())
    devices = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == 'device' and ':' not in fields[0]:
            devices.append(fields[0])
    if not devices:
        raise RuntimeError('未发现已授权的 USB 设备；请连接 Quest 并允许 USB 调试')
    if len(devices) != 1:
        raise RuntimeError('存在多个 USB 设备，请通过 QUEST_SERIAL 指定 Quest 序列号')
    return devices[0]


if __name__ == '__main__':
    try:
        print(usb_serial())
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error))
