"""Small standard-library helpers. Runtime data must stay outside source packages."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import time
import uuid

BASE = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Windows readers/antivirus may briefly hold a non-delete-sharing handle.
    # Retry only this metadata rename, never a board command or a download.
    for attempt in range(10):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.02 * (attempt + 1))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def package_default():
    for path in [BASE.parent / 'fusion150-final-code', BASE.parent]:
        if (path / 'candidate.json').is_file():
            return path.resolve()
    raise RuntimeError('找不到代码包；请传入 --package')


def outside(path, package):
    path = Path(path).resolve()
    for root in [BASE.resolve(), Path(package).resolve()]:
        if path == root or root in path.parents:
            raise ValueError('运行输出必须位于展示软件及代码包之外')
    if not str(path).isascii():
        raise ValueError('原板卡入口要求绝对ASCII输出路径；请用 --data 指定')
    return path


class Lease:
    """OS-owned byte lock; a crashed process cannot leave a permanently held lock."""
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise RuntimeError('已有软件实例或任务占用：' + str(self.path))
        return self

    def close(self):
        if self.stream:
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_UN)
            self.stream.close()
            self.stream = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        self.close()


def lock_home():
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x001C, None, 0, buffer) != 0:
            raise RuntimeError('无法定位Windows共享任务锁')
        return Path(buffer.value) / 'fpga-perf-tune' / 'locks'
    return Path.home() / '.local/state/fpga-perf-tune/locks'


def worker_busy():
    lease = Lease(lock_home() / 'fusion150-demo-task.lock')
    try:
        lease.acquire()
    except RuntimeError:
        return True
    finally:
        lease.close()
    return False


def alive(pid):
    if not pid:
        return False
    if os.name == 'nt':
        import ctypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.restype = ctypes.c_void_p
        handle = api.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        code = ctypes.c_ulong()
        try:
            api.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
            return code.value == 259
        finally:
            api.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False
