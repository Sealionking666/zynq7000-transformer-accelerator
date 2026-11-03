"""Loopback-only Python service, no framework, no automatic board actions."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
import argparse
import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from parser import observe
from util import BASE, Lease, lock_home, now, outside, package_default, read, save, sha, worker_busy, alive

ACTIVE = {'queued', 'running', 'needs_inspection'}


class Manager:
    def __init__(self, package, data, python):
        self.package = Path(package).resolve()
        self.data = outside(data, package)
        self.data.mkdir(parents=True, exist_ok=True)
        self.python = python
        self.mutex = threading.Lock()
        self.children = {}
        self.catalog = read(BASE / 'history.json')

    def jobs(self):
        rows = []
        for path in self.data.glob('*/state.json'):
            try:
                state = read(path)
                if state['status'] in {'queued', 'running'}:
                    launch = path.parent/'launch.command.json'
                    pid = state.get('worker_pid') or (read(launch).get('pid') if launch.exists() else None)
                    age = (datetime.fromisoformat(now())-datetime.fromisoformat(state['created'])).total_seconds()
                    if age > 30 and not alive(pid):
                        state.update(status='needs_inspection', phase='任务进程已中断，需人工检查',
                                     error='重启后未找到原任务进程；保留全部日志和锁，不自动继续或重复下载')
                        save(path, state)
                rows.append(state)
            except (OSError, ValueError):
                continue
        return sorted(rows, key=lambda s: s['created'], reverse=True)

    def job_path(self, job_id):
        if not re.fullmatch(r'[0-9a-f]{32}', job_id or ''):
            raise ValueError('任务编号不合法')
        path = self.data / job_id
        if not (path / 'state.json').is_file():
            raise ValueError('没有这个任务')
        return path

    def start(self, body):
        with self.mutex:
            if any(s['status'] in ACTIVE for s in self.jobs()) or worker_busy():
                raise RuntimeError('已有任务运行或待人工检查；不能重复启动')
            mode = body.get('mode')
            purpose = body.get('purpose')
            if mode not in {'live', 'replay'}:
                raise ValueError('请选择实体板采集或历史回放')
            request = dict(mode=mode, package=str(self.package))
            if mode == 'replay':
                source = next((s for s in self.catalog if s['id'] == body.get('history')), None)
                if source is None:
                    raise ValueError('历史来源不存在')
                purpose = source['purpose']
                request['source'] = source
            else:
                if purpose not in {'validation', 'official', 'benchmark'}:
                    raise ValueError('只支持开发集validation、官方test及benchmark实体板任务')
                confirmations = body.get('confirmations', {})
                if not all(confirmations.get(s) is True for s in ['powered', 'jtag', 'exclusive', 'volatile']):
                    raise ValueError('必须逐项确认本次供电、JTAG、独占与易失下载授权')
                if not re.fullmatch(r'COM[1-9][0-9]{0,3}', body.get('port', '')):
                    raise ValueError('请指定实际COM口')
                xilinx = Path(body.get('xilinx', '')).resolve()
                if not (xilinx / 'Vitis/2022.2/bin/xsct.bat').is_file():
                    raise ValueError('AMD安装根下找不到Vitis/2022.2/bin/xsct.bat')
                request.update(port=body['port'], xilinx=str(xilinx), confirmations=confirmations,
                               confirmed_at=now(), authorization_scope='本次任务：原release工件易失PL/DDR下载，不写Flash/SD')
            dataset = {'validation': 'development', 'official': 'official_test', 'benchmark': 'benchmark_fixed6'}[purpose]
            request['dataset'] = dataset
            job_id = uuid.uuid4().hex
            job = self.data / job_id
            job.mkdir()
            request.update(id=job_id, purpose=purpose, created=now())
            state = dict(id=job_id, mode=mode, purpose=purpose, dataset=dataset, created=now(), status='queued', phase='准备任务',
                         capture_exit_code=None, review_status='pending', source=request.get('source'),
                         port=request.get('port'), output=str(job))
            save(job / 'request.json', request)
            save(job / 'state.json', state)
            argv = [self.python, '-X', 'utf8', '-B', '-u', str(BASE / 'worker.py'), str(job)]
            try:
                with (job / 'worker.log').open('xb') as output:
                    process = subprocess.Popen(argv, cwd=BASE, stdout=output, stderr=subprocess.STDOUT,
                                               env=dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1'),
                                               creationflags=0x08000000 if os.name == 'nt' else 0)
                self.children[job_id] = process
                save(job / 'launch.command.json', dict(argv=argv, cwd=str(BASE), pid=process.pid, started=now(),
                                                     description='独立任务进程；刷新或关闭网页不会重启或停止'))
            except Exception as exc:
                state.update(status='failed', phase='任务进程启动失败', error=str(exc), finished=now())
                save(job / 'state.json', state)
                raise
            return state

    def detail(self, job_id=None):
        jobs = self.jobs()
        active = next((s for s in jobs if s['status'] in ACTIVE), None)
        selected = job_id or (jobs[0]['id'] if jobs else None)
        result = dict(jobs=jobs[:100], active=active, selected=None, board='未确认当前连接；串口枚举不等于板卡连接成功')
        if not selected:
            return result
        job = self.job_path(selected)
        state = read(job / 'state.json')
        launch = job / 'launch.command.json'
        process = self.children.get(selected)
        if process is not None:
            code = process.poll()
            if code is not None:
                meta = read(launch)
                if not (job / 'worker-exit.json').exists():
                    save(job / 'worker-exit.json', dict(pid=process.pid, exit_code=code, observed_exit_at=now()))
                if state['status'] in {'queued', 'running'}:
                    state.update(status='needs_inspection', phase='任务进程异常退出，需人工检查', error='工作进程已退出但无完整结束记录；未自动重试')
                    save(job / 'state.json', state)
        uart = job / ('capture/uart.bin' if state['mode'] == 'live' else 'uart.bin')
        state['observation'] = observe(uart.read_bytes()[:8*1024*1024], state['purpose']) if uart.is_file() else None
        state['review'] = read(job / 'review.json') if (job / 'review.json').exists() else None
        state['commands'] = [read(p) for p in sorted(job.glob('*.command.json'))]
        exit_path = job/'worker-exit.json'
        state['worker_exit'] = read(exit_path) if exit_path.exists() else None
        state['files'] = [p.relative_to(job).as_posix() for p in sorted(job.rglob('*')) if p.is_file()]
        if state['mode'] == 'live':
            result['board'] = '本次操作者已确认条件；' + ('原工具采集中，连接结果见日志' if state['status'] in {'queued', 'running'} else '记录已结束，不能推定此刻仍连接')
        result['selected'] = state
        return result

    def stop(self, job_id):
        with self.mutex:
            job = self.job_path(job_id)
            state = read(job / 'state.json')
            if state['status'] not in {'queued', 'running'}:
                raise ValueError('所选任务已结束或需要人工检查')
            (job / 'stop.request').touch(exist_ok=True)
            return dict(message='已请求停止日志采集；不表示停止FPGA计算或复位硬件', id=job_id)


class Handler(BaseHTTPRequestHandler):
    server_version = 'Fusion150Local/1.0'

    def log_message(self, fmt, *args):
        print(now(), fmt % args, flush=True)

    def same_host(self):
        port = self.server.server_address[1]
        if self.headers.get('Host') not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
            raise ValueError('只接受本地服务地址')

    def send_data(self, value, status=200):
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_blob(raw, 'application/json; charset=utf-8', status)

    def send_blob(self, raw, mime, status=200):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        try:
            self.same_host()
            url = urlsplit(self.path)
            params = parse_qs(url.query)
            manager = self.server.manager
            if url.path in {'/', '/app.js', '/style.css'}:
                name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[url.path]
                self.send_blob((BASE/'static'/name).read_bytes(), {'index.html':'text/html; charset=utf-8', 'app.js':'text/javascript; charset=utf-8', 'style.css':'text/css; charset=utf-8'}[name])
            elif url.path == '/api/config':
                candidate = read(manager.package / 'candidate.json')
                artifacts = {p.name: sha(p) for p in (manager.package/'release').glob('*') if p.suffix in {'.elf', '.bit', '.xsa'}}
                self.send_data(dict(token=self.server.token, package=str(manager.package), data=str(manager.data), history=manager.catalog,
                                    candidate=candidate, artifacts=artifacts, xilinx_default='E:/vivado',
                                    identity_matches=artifacts.get('hardware.bit') == candidate['deployed_bit_sha256']))
            elif url.path == '/api/ports':
                try:
                    from serial.tools import list_ports
                    ports = [dict(port=p.device, description=p.description, hwid=p.hwid) for p in list_ports.comports()]
                    self.send_data(dict(ports=ports, note='只枚举设备，不打开串口、不下载；不能证明板卡已连接'))
                except ImportError:
                    self.send_data(dict(ports=[], error='当前Python未安装pyserial；回放可用，实板需安装requirements.txt'))
            elif url.path == '/api/state':
                self.send_data(manager.detail(params.get('job', [None])[0]))
            elif url.path == '/api/log':
                job = manager.job_path(params.get('job', [''])[0])
                stream = params.get('stream', ['uart'])[0]
                paths = {'uart': ('capture/uart.bin' if (job/'capture').is_dir() else 'uart.bin'),
                         'tool':'collector.log', 'download':'capture/download.log', 'preflight':'preflight.log', 'worker':'worker.log'}
                if stream not in paths:
                    raise ValueError('日志流不存在')
                path = job / paths[stream]
                offset = max(0, int(params.get('offset', ['0'])[0]))
                total = path.stat().st_size if path.exists() else 0
                offset = min(offset, total)
                chunk = b''
                if path.exists():
                    with path.open('rb') as f:
                        f.seek(offset)
                        chunk = f.read(32768)
                self.send_data(dict(text=chunk.decode('utf-8', errors='replace'), offset=offset+len(chunk), total=total))
            elif url.path == '/download':
                job = manager.job_path(params.get('job', [''])[0])
                name = params.get('file', ['export.zip'])[0]
                path = (job/name).resolve()
                if job not in path.parents or not path.is_file() or path.suffix in {'.bit', '.elf'}:
                    raise ValueError('导出文件不存在或不是日志/结果')
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(path.stat().st_size))
                self.send_header('Content-Disposition', 'attachment; filename="' + path.name.replace('"', '') + '"')
                self.end_headers()
                with path.open('rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            else:
                self.send_data(dict(error='没有这个页面'), 404)
        except (ValueError, OSError, RuntimeError) as exc:
            self.send_data(dict(error=str(exc)), 400)

    def do_POST(self):
        try:
            self.same_host()
            port = self.server.server_address[1]
            if self.headers.get('Origin') not in {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}:
                raise ValueError('请从本地网页操作')
            if not secrets.compare_digest(self.headers.get('X-Demo-Token', ''), self.server.token):
                raise ValueError('页面会话已失效，请刷新')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError('请求长度不合法')
            body = json.loads(self.rfile.read(length))
            if self.path == '/api/start':
                self.send_data(self.server.manager.start(body), 202)
            elif self.path == '/api/stop':
                self.send_data(self.server.manager.stop(body.get('id')))
            else:
                self.send_data(dict(error='操作不存在'), 404)
        except RuntimeError as exc:
            self.send_data(dict(error=str(exc)), 409)
        except (ValueError, OSError) as exc:
            self.send_data(dict(error=str(exc)), 400)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--package', type=Path, default=None)
    ap.add_argument('--data', type=Path, default=Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'fusion150-demo/runs')
    ap.add_argument('--port', type=int, default=8765)
    args = ap.parse_args()
    package = args.package or package_default()
    manager = Manager(package, args.data, sys.executable)
    with Lease(lock_home() / 'fusion150-demo-server.lock'):
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
        server.daemon_threads = True
        server.manager, server.token = manager, secrets.token_hex(32)
        save(manager.data/'service.json', dict(pid=os.getpid(), started=now(), url=f'http://127.0.0.1:{args.port}', package=str(package.resolve()), data=str(manager.data)))
        print(f'展示软件已启动：http://127.0.0.1:{args.port}\n运行记录：{manager.data}\n关闭页面不停止任务；Ctrl+C只关闭网页服务，任务进程继续留存。', flush=True)
        try:
            server.serve_forever(poll_interval=0.3)
        except KeyboardInterrupt:
            print('网页服务已关闭；未对硬件发出停止/复位命令。', flush=True)
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
