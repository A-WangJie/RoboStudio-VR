"""Start the local RoboData bridge from either the desktop or web workbench."""
import fcntl
import json
import os
import sys
from pathlib import Path
import subprocess
import threading
import time
from urllib.request import urlopen


class BridgeService:
    def __init__(self, root=None, state_url='http://127.0.0.1:8767/api/state', timeout=20):
        self.root = Path(root or Path(__file__).resolve().parent)
        self.state_url = state_url
        self.timeout = timeout
        self.lock = threading.Lock()
        self.process = None

    def running(self):
        try:
            with urlopen(self.state_url, timeout=.7) as response:
                state = json.load(response)
            return (state.get('status') in {'live', 'waiting', 'stale', 'disconnected'}
                    and isinstance(state.get('connection'), dict)
                    and isinstance(state.get('simulation'), dict))
        except (OSError, ValueError, AttributeError):
            return False

    def setup(self):
        if not self.lock.acquire(timeout=24):
            raise RuntimeError('数据桥正在配置，请稍后重试')
        try:
            local = Path(os.environ.get('ROBODATA_DATA_DIR', str(self.root / '.local'))).expanduser()
            config = Path(os.environ.get('ROBODATA_CONFIG_DIR', str(local / 'config'))).expanduser()
            config.mkdir(parents=True, exist_ok=True)
            # Separate RS instances must also share a single bridge.
            with (config / 'bridge-start.lock').open('a') as lock_file:
                deadline = time.monotonic() + self.timeout
                while True:
                    try:
                        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('其他工作台正在配置数据桥，请稍后重试')
                        time.sleep(.1)
                if self.running():
                    return {'running': True, 'message': 'RD 数据桥已在运行，可直接连接 RoboData。'}
                script = self.root / 'start-bridge.sh'
                if not script.is_file():
                    raise RuntimeError('找不到数据桥启动文件：' + str(script))
                log_path = Path(os.environ.get('ROBODATA_LOG_DIR', str(self.root / 'artifacts/logs'))) / 'bridge-runtime.log'
                log_path.parent.mkdir(parents=True, exist_ok=True)
                if self.process is None or self.process.poll() is not None:
                    with log_path.open('ab') as log:
                        self.process = subprocess.Popen(
                            ['bash', str(script)], cwd=self.root,
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True, env=dict(os.environ, ROBODATA_PYTHON=os.environ.get('ROBODATA_PYTHON', sys.executable)))
                while time.monotonic() < deadline:
                    if self.process.poll() is not None:
                        raise RuntimeError('数据桥启动失败，请查看日志：' + str(log_path))
                    if self.running():
                        return {'running': True, 'message': 'RD 数据桥已启动，可连接 RoboData；USB 已连接时会自动配置转发。'}
                    time.sleep(.15)
                raise RuntimeError('数据桥尚未就绪，请稍后重试。日志：' + str(log_path))
        finally:
            self.lock.release()
