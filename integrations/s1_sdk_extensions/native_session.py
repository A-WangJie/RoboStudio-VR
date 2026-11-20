"""Ownership wrapper for the unchanged old compiled S1ARM implementation.

Creating this object is an explicit terminal control operation. RS uses safe_can
for connections/reads, never this native constructor.
"""
import atexit
from .device_session import DeviceSession

class OwnedNativeArm:
    def __init__(self, factory, device, comm, end):
        self._native = None
        self._session = DeviceSession(device).acquire()
        try:
            self._native = factory(device, comm, end)
        except BaseException:
            self._session.close()
            raise
        atexit.register(self.close)

    def __getattr__(self, name):
        if self._native is None: raise RuntimeError('SDK 机械臂会话已关闭')
        return getattr(self._native, name)

    def close(self):
        native, self._native = self._native, None
        try:
            if native is not None:
                try: native.disable()
                finally: del native  # Stop native workers before releasing CAN ownership.
        finally:
            self._session.close()
            atexit.unregister(self.close)
