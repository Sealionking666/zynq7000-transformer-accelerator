"""Durable task process; never retries or replaces release artifacts."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import traceback
import zipfile
from parser import review, load_verify
from util import BASE, Lease, lock_home, now, read, save, sha


def execute(job):
    request = read(job / 'request.json')
    package = Path(request['package'])
    state = read(job / 'state.json')

    def update(**values):
        state.update(values, updated=now())
        save(job / 'state.json', state)

    def command(argv, name, timeout):
        begin = time.time()
        meta = dict(argv=list(map(str, argv)), cwd=str(BASE), started=now(), exit_code=None)
        save(job / (name + '.command.json'), meta)
        env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
        with (job / (name + '.log')).open('xb') as output:
            process = subprocess.Popen(meta['argv'], cwd=BASE, env=env, stdout=output, stderr=subprocess.STDOUT,
                                       creationflags=0x08000000 if os.name == 'nt' else 0)
            meta['pid'] = process.pid
            save(job / (name + '.command.json'), meta)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Request cooperative shutdown so the original run_board finally cleans its locks/XSCT.
                (job / 'stop.request').touch(exist_ok=True)
                try:
                    code = process.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    update(status='needs_inspection', phase='采集进程未能按期退出', error='保留PID和锁；请人工检查。未自动重试或删除故障锁。')
                    raise RuntimeError('Cooperative shutdown timed out; inspect owned process ' + str(process.pid))
            meta.update(exit_code=code, finished=now(), wall_seconds=time.time() - begin)
            save(job / (name + '.command.json'), meta)
            return code

    update(status='running', phase='校验代码包与冻结工件', worker_pid=os.getpid())
    try:
        with Lease(lock_home() / 'fusion150-demo-task.lock'):
            code = command([sys.executable, '-X', 'utf8', '-B', package / 'tools/verify.py', '--package', package,
                            '--out', job / 'preflight'], 'preflight', 120)
            if code:
                raise RuntimeError('原verify.py校验失败，请查看preflight.log；未下载')
            if (job / 'stop.request').exists():
                update(status='stopped', phase='下载前已取消', capture_exit_code=None)
                return
            if request['mode'] == 'replay':
                update(phase='读取真实历史日志')
                source = request['source']
                origin = package / source['path']
                if sha(origin) != source['sha256']:
                    raise RuntimeError('历史来源hash不符；拒绝回放')
                (job / 'uart.bin').write_bytes(origin.read_bytes())
                save(job / 'source.json', {**source, 'copied_sha256': sha(job / 'uart.bin'), 'replayed_at': now(),
                                          'warning': '历史日志回放，不是本次实体板运行'})
                uart = job / 'uart.bin'
                update(phase='历史日志独立复核', capture_exit_code=None, capture_status='无采集进程（历史回放）')
            else:
                update(phase='原工具下载与UART采集', capture_status='运行中')
                capture = job / 'capture'
                args = ['--package', str(package), '--purpose', request['purpose'], '--port', request['port'],
                        '--out', str(capture), '--xilinx', request['xilinx'], '--powered', '--jtag', '--exclusive', '--authorize-volatile-download']
                code = command([sys.executable, '-X', 'utf8', '-B', BASE / 'bridge.py', job / 'stop.request',
                                package / 'tools/run_board.py', *args], 'collector', 350 if request['purpose'] == 'official' else 230)
                update(capture_exit_code=code, capture_status='采集进程已退出', phase='复核采集结果')
                if (job / 'stop.request').exists():
                    update(status='stopped', phase='已停止日志采集', error='仅停止采集，不代表停止FPGA计算或复位；保留原工具故障记录，人工检查后再运行')
                    return
                if code:
                    raise RuntimeError('采集工具退出码非零；检查collector.log、capture/download.log及故障记录')
                capture_result = read(capture / 'result.json')
                if capture_result.get('status') != 'captured_unvalidated':
                    raise RuntimeError('原采集工具没有确认完整采集')
                uart = capture / 'uart.bin'
            checked = review(uart, request['purpose'], package)
            save(job / 'review.json', checked)
            update(review_status=checked['status'], phase='历史回放复核完成' if request['mode'] == 'replay' else '采集及独立复核完成',
                   status='completed' if checked['status'] == 'passed' else 'failed',
                   error=None if checked['status'] == 'passed' else checked['reason'])
    except Exception as exc:
        traceback.print_exc()
        if state.get('status') != 'needs_inspection':
            update(status='failed', phase='失败，已保留记录', error=str(exc))
    finally:
        update(finished=now())
        files = []
        for p in sorted(job.rglob('*')):
            if p.is_file() and p.name not in {'export.zip', 'files.json'}:
                files.append(dict(path=p.relative_to(job).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
        save(job / 'files.json', dict(recorded=now(), files=files))
        # Export logs/results only. Large unchanged bit/ELF copies remain on disk in capture/.
        with zipfile.ZipFile(job / 'export.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(job.rglob('*')):
                if p.is_file() and p.name != 'export.zip' and p.suffix not in {'.bit', '.elf'}:
                    archive.write(p, p.relative_to(job))


if __name__ == '__main__':
    execute(Path(sys.argv[1]).resolve())
