"""Per-interface ownership shared by RS and SDK terminal controllers (Linux)."""
import errno
import fcntl
import os
from pathlib import Path
import re
import stat

class DeviceSession:
    def __init__(self, device, directory=None):
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,14}', device):
            raise ValueError('无效设备名称')
        self.device = device
        self.directory = Path(directory or f'/tmp/s1-sdk-{os.getuid()}')
        self.fd = None

    def acquire(self):
        if self.fd is not None: return self
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise RuntimeError('SDK 设备锁目录权限异常')
        fd = os.open(self.directory / (self.device + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(fd)
            raise RuntimeError(f'{self.device} 已被终端或 RS 占用；请先退出另一方的真机控制，再重新连接') from error
        except BaseException:
            os.close(fd); raise
        self.fd = fd
        return self

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)

    def __enter__(self): return self.acquire()
    def __exit__(self, *args): self.close()
    def __del__(self): self.close()
