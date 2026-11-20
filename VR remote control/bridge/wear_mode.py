"""Session-only Quest wear sensing override, controlled by the local monitor."""
import ipaddress
import json
from pathlib import Path
import os
import subprocess
import threading
import time
try:
    from .adb_device import usb_serial
except ImportError:
    from adb_device import usb_serial

class WearMode:
    def __init__(self, stop, runner=None, mode=lambda: "usb", config=None):
        self.stop = stop
        self.runner = runner or subprocess.run
        self.serial = os.environ.get('QUEST_SERIAL', '')
        self.mode = mode
        self.config = Path(config) if config else None
        self.wireless = ''
        self.wireless_ready = False
        if self.config and self.config.exists():
            try:
                saved = json.loads(self.config.read_text())
                self.wireless = self.endpoint(saved['host'], saved['port'])
            except (ValueError, KeyError, OSError): pass
        self.operation = threading.Lock()
        self.lock = threading.Lock()
        self.enabled = None
        self.busy = False
        self.message = '正在恢复正常佩戴感应…'

    @staticmethod
    def endpoint(host, port):
        ip = ipaddress.IPv4Address(host)
        if ip.is_loopback or ip.is_unspecified or ip.is_multicast:
            raise ValueError('请输入头显的局域网 IPv4 地址')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('无线调试端口无效')
        return f'{ip}:{port}'

    def run_adb(self, *args):
        try:
            r = self.runner(['adb', *args], capture_output=True, text=True, timeout=5)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError('调试连接超时，请确认头显和电脑在同一网络，且无线调试已启用') from e
        output = (r.stdout + r.stderr).strip()
        if r.returncode or any(x in output for x in ('SecurityException', 'Permission Denial', 'Error:', 'Exception occurred', 'cannot connect', 'failed to connect', 'unable to connect')):
            raise RuntimeError(output[-500:] or 'ADB 操作失败')
        return output

    def adb(self, *args):
        return self.run_adb('-s', self.serial or usb_serial(self.runner), *args)

    def configure_wireless(self, options):
        endpoint = self.endpoint(options.get('host', ''), options.get('port', 5555))
        if not self.operation.acquire(blocking=False): raise ValueError('正在切换，请稍候')
        with self.lock:
            self.busy = True
        try:
            self.wireless_ready = False
            if endpoint != self.wireless: self.enabled = None
            if options.get('bootstrap') is True:
                self.adb('tcpip', '5555')
                endpoint = self.endpoint(options['host'], 5555)
            # tcpip restarts adbd; allow its network listener time to appear.
            attempts = 3 if options.get('bootstrap') is True else 1
            for attempt in range(attempts):
                try:
                    self.run_adb('connect', endpoint)
                    if self.run_adb('-s', endpoint, 'get-state') != 'device':
                        raise ValueError('无线调试未授权，请在头显确认')
                    self.run_adb('-s', endpoint, 'shell', 'getprop', 'ro.product.model')
                    break
                except Exception:
                    if attempt == attempts - 1: raise
                    time.sleep(.4)
            self.wireless = endpoint
            if self.config:
                self.config.parent.mkdir(parents=True, exist_ok=True)
                host, port = endpoint.split(':')
                self.config.write_text(json.dumps(dict(host=host, port=int(port))))
            self.wireless_ready = True
            self.message = '无线调试已连接 · 可以不插 USB 切换自由摘戴'
        except Exception as e:
            self.message = '无线调试连接失败：'+str(e)
            raise
        finally:
            with self.lock: self.busy = False
            self.operation.release()
        return self.snapshot()

    def snapshot(self):
        with self.lock:
            return dict(enabled=self.enabled, busy=self.busy, message=self.message, wirelessEndpoint=self.wireless, wirelessReady=self.wireless_ready)

    def set(self, enabled):
        if type(enabled) is not bool: raise ValueError('开关必须为布尔值')
        if not self.operation.acquire(blocking=False): raise ValueError('正在切换，请稍候')
        with self.lock:
            self.busy = True
            self.message = '正在开启自由摘戴采集…' if enabled else '正在恢复正常佩戴感应…'
        try:
            self.stop('佩戴模式切换 · 仿真跟随已停止，请按需重新启用')
            wireless = self.mode() == 'wifi'
            target = self.wireless if wireless else (self.serial or usb_serial(self.runner))
            if not target: raise ValueError('请先连接下方的无线调试，地址填写头显 IP')
            if wireless: self.run_adb('connect', target)
            command = lambda *args: self.run_adb('-s', target, *args)
            if command('get-state') != 'device': raise RuntimeError('调试设备未连接或未授权')
            if wireless: self.wireless_ready = True
            if enabled:
                if not wireless: command('reverse', 'tcp:8766', 'tcp:8766')
                command('shell', 'am', 'broadcast', '-a', 'com.oculus.vrpowermanager.prox_close')
                command('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
                command('shell', 'am', 'start', '-n', 'com.UnityTechnologies.com.unity.template.urpblank/com.unity3d.player.UnityPlayerGameActivity')
            else:
                command('shell', 'am', 'broadcast', '-a', 'com.oculus.vrpowermanager.automation_disable')
            with self.lock:
                self.enabled = enabled
                self.message = '自由摘戴采集已开启 · 请确认手柄追踪有效' if enabled else '正常佩戴感应 · 已发送恢复指令'
        except Exception as e:
            with self.lock:
                self.enabled = None
                if self.mode() == 'wifi': self.wireless_ready = False
                detail = str(e)
                if self.mode() != 'wifi' and isinstance(e, RuntimeError) and '调试连接超时' in detail:
                    detail = 'USB 调试响应超时，请检查数据线、头显授权及是否已唤醒'
                self.message = '切换未完成，设备状态待确认：'+detail
            raise
        finally:
            with self.lock: self.busy = False
            self.operation.release()
        return self.snapshot()

    def restore(self):
        try: self.set(False)
        except Exception: pass  # The page shows the failure; never claim off on an ADB failure.
