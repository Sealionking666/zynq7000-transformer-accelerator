"""Invoke the unmodified board entrypoint, with a cooperative capture-stop request."""
from pathlib import Path
import _thread
import runpy
import signal
import sys
import threading
import time

stop_file, entrypoint, *argv = sys.argv[1:]
finished = threading.Event()


def watch():
    while not finished.wait(0.15):
        if Path(stop_file).is_file():
            _thread.interrupt_main()
            return


def interrupt(*args):
    raise KeyboardInterrupt('停止日志采集请求；不表示FPGA计算已停止')


if hasattr(signal, 'SIGBREAK'):
    signal.signal(signal.SIGBREAK, interrupt)
signal.signal(signal.SIGTERM, interrupt)
threading.Thread(target=watch, daemon=True).start()
sys.path.insert(0, str(Path(entrypoint).resolve().parent))
sys.argv = [entrypoint, *argv]
try:
    if Path(stop_file).exists():
        raise KeyboardInterrupt('下载前已取消')
    runpy.run_path(entrypoint, run_name='__main__')
except KeyboardInterrupt:
    print('DEMO_CAPTURE_STOPPED: 仅停止采集；不保证硬件停止或复位', flush=True)
    sys.exit(130)
finally:
    finished.set()
