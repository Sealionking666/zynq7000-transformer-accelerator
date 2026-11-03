"""Receive-only UART capture and one explicit volatile download of original final artifacts."""
from pathlib import Path
import argparse
import json
import shutil
import socket
import subprocess
import sys
import time
from verify import verify, sha, read, output_outside_package

sys.path.insert(0, str(Path(__file__).resolve().parent / 'pinned'))
from common import lock, lock_root, host_state_root, save

PURPOSES = {
    'validation': ('HAR_VALIDATION_PASS', 180),
    'benchmark': ('HAR_BOARD_PASS', 180),
    'lifecycle': ('HAR_LIFECYCLE_PASS', 180),
    'stress': ('HAR_STRESS_SUMMARY', 2400),
    'official': ('HAR_OFFICIAL_PASS', 300),
}


def run(args):
    if not all([args.powered, args.jtag, args.exclusive, args.authorize_volatile_download]):
        raise RuntimeError('Current operator must explicitly confirm power, JTAG, exclusive access and volatile download')
    package = args.package.resolve()
    verify(package)
    xsct = args.xilinx.resolve() / 'Vitis/2022.2/bin/xsct.bat'
    if not xsct.is_file():
        raise RuntimeError('XSCT 2022.2 not found')
    output = output_outside_package(package, args.out)
    if not output.is_absolute() or not str(output).isascii():
        raise RuntimeError('Use an absolute ASCII output path')
    fault = host_state_root() / 'final-code-board-fault.json'
    if fault.exists():
        raise RuntimeError('Prior board failure requires operator inspection; preserve latch: ' + str(fault))
    # Do not start, terminate or take ownership of another operator's hw_server.
    with socket.create_connection(('127.0.0.1', 3121), timeout=3):
        pass
    output.mkdir(parents=True, exist_ok=False)
    authorization = {'schema': 'final-code-current-operator-confirmation/1', 'recorded': time.time(),
                     'board': 'AX7Z020B', 'powered': True, 'boot_mode': 'JTAG', 'port': args.port,
                     'exclusive': True, 'volatile_PL_DDR_only': True,
                     'purpose': args.purpose, 'bit_sha256': sha(package / 'release/hardware.bit'),
                     'elf_sha256': sha(package / 'release' / (args.purpose + '.elf'))}
    save(output / 'authorization.json', authorization)
    for source, target in [('hardware.bit', 'hardware.bit'), ('ps7_init.tcl', 'ps7_init.tcl'),
                           (args.purpose + '.elf', 'application.elf')]:
        shutil.copyfile(package / 'release' / source, output / target)
    shutil.copyfile(package / 'tools/download.tcl', output / 'download.tcl')
    import serial
    marker, timeout = PURPOSES[args.purpose]
    proc = None
    started = False
    status = {'status': 'prepared', 'purpose': args.purpose, 'scope': 'raw capture; requires independent review'}
    try:
        with lock(lock_root() / 'board.lock', {'final_board_capture': str(output)}):
            with lock(lock_root() / 'eda.lock', {'final_board_capture': str(output)}):
                with serial.Serial(args.port, 115200, timeout=0.1) as uart:
                    uart.reset_input_buffer()
                    with (output / 'download.log').open('xb') as log, (output / 'uart.bin').open('xb') as capture:
                        proc = subprocess.Popen([str(xsct), 'download.tcl'], cwd=output,
                                                stdout=log, stderr=subprocess.STDOUT,
                                                creationflags=0x08000000 if sys.platform == 'win32' else 0)
                        started = True
                        begin = time.monotonic()
                        collected = bytearray()
                        while time.monotonic() - begin < timeout:
                            chunk = uart.read(uart.in_waiting or 1)
                            if chunk:
                                capture.write(chunk)
                                capture.flush()
                                collected.extend(chunk)
                            if proc.poll() not in (None, 0):
                                raise RuntimeError('XSCT download failed; inspect download.log')
                            lines = [line for line in collected.splitlines() if line]
                            if any(b'_FAIL' in line or b'HAR_DOWNLOAD_FAILED' in line for line in lines):
                                raise RuntimeError('Firmware failure marker; inspect raw UART')
                            if collected.endswith(b'\n') and proc.poll() == 0 and any(line.startswith(marker.encode('ascii') + b' ') for line in lines):
                                break
                        else:
                            raise RuntimeError('Capture timed out; no automatic retry')
                    downloaded = (output / 'download.log').read_text(encoding='utf-8', errors='replace')
                    markers = ['HAR_FPGA_PROGRAMMED', 'HAR_PS_INIT_DONE', 'HAR_ELF_DOWNLOADED', 'HAR_APPLICATION_STARTED']
                    if 'HAR_DOWNLOAD_FAILED' in downloaded or not all(downloaded.count(m) == 1 for m in markers):
                        raise RuntimeError('Download identity/order evidence incomplete')
                    if [downloaded.index(m) for m in markers] != sorted(downloaded.index(m) for m in markers):
                        raise RuntimeError('Download markers out of order')
        status.update(status='captured_unvalidated', raw_uart_sha256=sha(output / 'uart.bin'),
                      download_log_sha256=sha(output / 'download.log'), exit_code=proc.returncode)
    except BaseException as exc:
        status.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        if started:
            fault.parent.mkdir(parents=True, exist_ok=True)
            if not fault.exists():
                with fault.open('x', encoding='utf-8') as stream:
                    json.dump({'attempt': str(output), 'error': str(exc),
                               'next': 'Inspect board and logs with the operator; no automatic retry or latch deletion'}, stream, indent=2)
        raise
    finally:
        if proc is not None and proc.poll() is None:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
            proc.wait(timeout=30)
        save(output / 'result.json', status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--purpose', choices=PURPOSES, required=True)
    ap.add_argument('--port', required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--xilinx', type=Path, required=True)
    for flag in ['powered', 'jtag', 'exclusive', 'authorize-volatile-download']:
        ap.add_argument('--' + flag, action='store_true')
    run(ap.parse_args())
