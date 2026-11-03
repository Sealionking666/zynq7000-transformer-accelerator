"""Deterministic records, integrity checks and owned subprocesses. No model calls."""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

BASELINE = '4869aaa2496f3e3318ae9ebfb4eb200d065f5a09'
KERNEL = 'FPGA/accelerator/hls_engine/variants/matmul_int8_burst.cpp'
RUNTIME_FILES = ('har_fixed.c', 'har_pl.c', 'har_zynq.c')
MUTABLE = {KERNEL, *('tuning/runtime/' + n for n in RUNTIME_FILES)}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def identifier(value):
    require(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value)), 'Unsafe identifier')
    return value


def inside(root, relative):
    root = Path(root).resolve()
    p = (root / relative).resolve()
    require(p.is_relative_to(root), 'Path leaves owned root: ' + str(relative))
    return p


def git(root, *args):
    p = subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=False)
    require(p.returncode == 0, p.stderr.decode('utf-8', errors='replace'))
    return p.stdout.decode('utf-8', errors='replace').strip()


def git_blob(root,ref,path):
    return subprocess.check_output(['git','-C',str(root),'show',ref+':'+path])


def tracked(root):
    names = git(root, 'ls-files', '-z').split('\0')
    return {n: sha(Path(root) / n) for n in names if n}


def verify_map(root, manifest):
    for n, digest in manifest.items():
        p = inside(root, n)
        require(p.is_file() and sha(p) == digest, 'Integrity mismatch: ' + n)


def freeze(root, locked=None):
    lock = locked or read(Path(root) / 'freeze/model.lock.json')
    verify_map(root, {n: v['sha256'] for n, v in lock['files'].items()})


def files_under(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(Path(root).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc' and p.name != 'INSTALLATION.json'}


def alive(pid):
    if os.name == 'nt':
        import ctypes
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.restype = ctypes.c_void_p
        h = k.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
        k.CloseHandle(ctypes.c_void_p(h))
        return code.value == 259
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


class LockReleaseError(RuntimeError):
    """Controller cleanup failed; persisted stage outcome must be inspected."""


@contextlib.contextmanager
def lock(path, metadata=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    try:
        with path.open('x', encoding='utf-8') as f:
            json.dump({**(metadata or {}), 'pid': os.getpid(), 'token': token, 'created': time.time()}, f)
    except FileExistsError:
        raise RuntimeError('Resource locked; inspect owner before resume: ' + str(path))
    try:
        yield
    finally:
        if path.exists() and read(path).get('token') == token:
            try:
                path.unlink()
            except OSError as e:
                # Preserve a nonzero controller outcome. Never rerun a tool or
                # board download merely because a terminal stage's cleanup failed.
                raise LockReleaseError('Lock release failed: '+str(path)+
                    '; inspect saved terminal stage and use recovery; do not repeat operation. '+str(e)) from e


def host_state_root():
    # Both hosts must resolve the same user resource locks even when their
    # subprocess environments omit or override LOCALAPPDATA. Never change host
    # permission settings or fall back to a different writable lock directory.
    if os.name == 'nt':
        import ctypes
        buffer=ctypes.create_unicode_buffer(32768)
        result=ctypes.windll.shell32.SHGetFolderPathW(None,0x001C,None,0,buffer)
        require(result==0 and buffer.value,'Cannot resolve Windows Local AppData for shared resource locks')
        base=Path(buffer.value)
    else:
        base=Path.home()/'.local/state'
    return base/'fpga-perf-tune'


def lock_root():
    return host_state_root()/'locks'


def run(command, cwd, output, timeout, markers=()):
    """Capture a single command, terminate only its own process tree on failure."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    record = {'command': list(map(str, command)), 'cwd': str(cwd), 'started': time.time(),
              'timeout_seconds': timeout, 'status': 'running'}
    meta = output.with_suffix(output.suffix + '.process.json')
    p = None
    try:
        with output.open('xb') as log:
            p = subprocess.Popen(list(map(str, command)), cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=0x08000000 if os.name == 'nt' else 0,
                                 start_new_session=os.name != 'nt')
            record['pid'] = p.pid
            save(meta, record)
            code = p.wait(timeout=timeout)
        record['exit_code'] = code
        text = output.read_text(encoding='utf-8', errors='replace')
        require(code == 0, f'Command exit={code}; see {output}')
        for marker in markers:
            require(marker in text, f'Missing marker {marker}; see {output}')
        record['status'] = 'passed'
        return text
    except BaseException as e:
        record.update(status='failed', error=type(e).__name__ + ': ' + str(e))
        if p is not None and p.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'], capture_output=True)
            else:
                import signal
                os.killpg(p.pid, signal.SIGKILL)
            p.wait(timeout=15)
        raise
    finally:
        record['finished'] = time.time()
        if output.exists():
            record['log_sha256'] = sha(output)
        save(meta, record)
