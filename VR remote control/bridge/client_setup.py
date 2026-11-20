"""USB-assisted setup of RoboData and the independent wireless ADB link."""
import ipaddress
import json
from pathlib import Path
import re
import tempfile
import threading


class ClientSetup:
    def __init__(self, connection, wear_mode, simulation, recorder, disconnect):
        self.connection = connection
        self.wear = wear_mode
        self.simulation = simulation
        self.recorder = recorder
        self.disconnect = disconnect
        self.lock = threading.Lock()

    def configure(self, options):
        if not self.lock.acquire(blocking=False):
            raise ValueError('正在配置头显，请稍候')
        try:
            return self._configure(options)
        finally:
            self.lock.release()

    def _configure(self, options):
        mode = options.get('mode', self.connection.mode)
        if mode not in ('usb', 'wifi'):
            raise ValueError('连接方式无效')
        host = str(ipaddress.IPv4Address(options.get('host', '127.0.0.1')))
        if mode == 'wifi' and host not in self.connection.snapshot()['addresses']:
            raise ValueError('请选择本机局域网 IP')
        # Fail before changing the active connection when USB is missing.
        try:
            if self.wear.adb('get-state') != 'device':
                raise RuntimeError('USB 未授权')
        except Exception as error:
            raise ValueError('请插入 Quest USB 并允许调试，然后重试：' + str(error)) from error

        quest_host = None
        if mode == 'wifi':
            addresses = self.wear.adb('shell', 'ip', '-o', '-4', 'addr', 'show', 'wlan0')
            interfaces = [ipaddress.IPv4Interface(value) for value in
                          re.findall(r'\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)', addresses)]
            matching = [interface for interface in interfaces
                        if ipaddress.IPv4Address(host) in interface.network]
            if not matching:
                raise ValueError('头显未连接 Wi-Fi，或所选电脑 IP 与头显不在同一网段。请连接同一 Wi-Fi 并选择正确的同步主机 IP。')
            quest_host = str(matching[0].ip)

        self.simulation.disable('正在通过 USB 一键配置 RoboData · 跟随已停止')
        self.recorder.stop('client_reconfigured')
        package = 'com.UnityTechnologies.com.unity.template.urpblank'
        folder = '/sdcard/Android/data/' + package + '/files'
        payload = dict(mode=mode, host=host, port='8766', code=self.connection.token)
        if mode == 'usb':
            self.wear.adb('reverse', 'tcp:8766', 'tcp:8766')
        with tempfile.TemporaryDirectory(prefix='robodata-setup-') as directory:
            setup = Path(directory) / 'connection-setup.json'
            setup.write_text(json.dumps(payload))
            setup.chmod(0o600)
            self.wear.adb('shell', 'mkdir', '-p', folder)
            self.wear.adb('push', str(setup), folder + '/connection-setup.tmp')
            self.wear.adb('shell', 'mv', folder + '/connection-setup.tmp', folder + '/connection-setup.json')
        if self.connection.mode != mode:
            self.connection.set(mode)
            self.disconnect()
        self.wear.adb('shell', 'am', 'start', '-n', package + '/com.unity3d.player.UnityPlayerGameActivity')

        result = dict(synced=True, mode=mode, host=host, questHost=quest_host)
        if mode == 'usb':
            return dict(result, message='USB 数据连接已配置并请求启动 RoboData；请在头显内完成启动确认。')
        try:
            self.wear.configure_wireless(dict(host=quest_host, port=5555, bootstrap=True))
        except Exception as error:
            return dict(result, wirelessReady=False, warning=str(error),
                        message='RD 连接参数已同步，但自由摘戴无线调试未配置成功：' + str(error)
                        + '。请保持 USB 连接后重试，或展开无线调试设置排查。')
        return dict(result, wirelessReady=True,
                    message='RD Wi-Fi 连接参数已同步，头显 IP ' + quest_host
                    + ' 的无线调试已配置并验证。自由摘戴开关可直接使用；显示实时接收后可拔线。')
