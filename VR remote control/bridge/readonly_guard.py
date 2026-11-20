"""Linux x86-64 worker syscall guard: receive-only CAN, stdout/stderr logging."""
import ctypes
import errno
import platform


def install():
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise RuntimeError('只读 SDK 隔离目前仅支持 Linux x86_64')
    class Filter(ctypes.Structure):
        _fields_ = [('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_ = [('len',ctypes.c_ushort),('filter',ctypes.POINTER(Filter))]
    # seccomp_data.arch, then syscall number. Reject a changed ABI.
    rows = [(0x20,0,0,4),(0x15,1,0,0xc000003e),(0x06,0,0,0x80000000),
            (0x20,0,0,0)]
    # sendto/sendmsg/sendmmsg and pwrite64 cannot be used for telemetry reads.
    for syscall in (44,46,307,18):
        rows += [(0x15,0,1,syscall),(0x06,0,0,0x50000|errno.EPERM)]
    # write/writev allowed only to stdout/stderr; the native SocketCAN transport
    # uses write(). Filter inherited by every SDK thread (installed beforehand).
    rows += [(0x15,2,0,1),(0x15,1,0,20),(0x06,0,0,0x7fff0000),
             (0x20,0,0,16),(0x15,2,0,1),(0x15,1,0,2),
             (0x06,0,0,0x50000|errno.EPERM),(0x06,0,0,0x7fff0000)]
    filters = (Filter*len(rows))(*(Filter(*row) for row in rows))
    program = Program(len(rows),filters)
    libc = ctypes.CDLL(None,use_errno=True)
    if libc.prctl(38,1,0,0,0) or libc.prctl(22,2,ctypes.byref(program),0,0):
        raise OSError(ctypes.get_errno(),'无法启用 SDK 只读隔离')
