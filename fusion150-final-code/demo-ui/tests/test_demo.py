"""Offline reliability tests. Altered logs are isolated test fixtures, never board results."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import zipfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parser import observe, review
from util import BASE, package_default, read, save

PACKAGE = Path(os.environ.get('FUSION_TEST_PACKAGE', package_default()))


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fusion150-isolated-fixtures-')
        self.path = Path(self.temp.name) / 'TEST_FIXTURE_ONLY.bin'

    def tearDown(self):
        self.temp.cleanup()

    def check_mutation(self, raw, purpose):
        self.path.write_bytes(raw)
        self.assertEqual(review(self.path, purpose, PACKAGE)['status'], 'failed')

    def test_actual_three_sources(self):
        for row in read(BASE/'history.json'):
            self.assertEqual(hashlib.sha256((PACKAGE/row['path']).read_bytes()).hexdigest(), row['sha256'])
            self.assertEqual(review(PACKAGE/row['path'], row['purpose'], PACKAGE)['status'], 'passed')

    def test_validation_scope_and_missing_classification(self):
        value = review(PACKAGE/'evidence/report/E05-raw-04-uart.txt', 'validation', PACKAGE)
        self.assertIn('非逐logit', value['scope'])
        self.assertEqual(value['observation']['samples'], 1796)
        self.assertIsNone(value['observation']['timing'])
        self.assertEqual(value['observation']['classification'], [])

    def test_benchmark_timer_warmup(self):
        value = review(PACKAGE/'evidence/report/E05-raw-06-uart.txt', 'benchmark', PACKAGE)
        self.assertEqual(value['observation']['timing']['measured'], 60)
        self.assertAlmostEqual(value['observation']['timing']['pspl_median_us'], 40.67099882054104)
        self.assertIsNone(value['observation']['accuracy'])

    def test_official_independent_raw_logits(self):
        value = review(PACKAGE/'evidence/official-uart.bin', 'official', PACKAGE)
        self.assertEqual(value['facts']['logits'], 17682)
        self.assertEqual(value['facts']['correct'], 2472)
        self.assertNotIn('timing', value['facts'])
        self.assertIsNone(value['observation']['timing'])

    def test_truncation_all_three(self):
        for r in read(BASE/'history.json'):
            raw = (PACKAGE/r['path']).read_bytes()
            self.check_mutation(raw[:-1], r['purpose'])
            self.check_mutation(raw[:len(raw)//2], r['purpose'])

    def test_end_marker_alone_not_pass(self):
        raw = (PACKAGE/'evidence/report/E05-raw-04-uart.txt').read_bytes()
        self.check_mutation(raw.splitlines()[-1]+b'\n','validation')

    def test_fail_wrong_checksum_duplicate_and_profile(self):
        raw = (PACKAGE/'evidence/report/E05-raw-04-uart.txt').read_bytes()
        for new in [raw.replace(b'BD0B22AD',b'00000000'), raw+b'HAR_VALIDATION_FAIL sample=0 status=1\n', raw+raw,
                    raw.replace(b'6822676ce8ba453d8819544787327cb5',b'00000000000000000000000000000000'),
                    raw.replace(b'samples=512',b'samples=513')]:
            self.check_mutation(new, 'validation')

    def test_benchmark_coverage_and_bad_timer(self):
        raw = (PACKAGE/'evidence/report/E05-raw-06-uart.txt').read_bytes()
        for new in [raw.replace(b'timer_hz=0x0000000013DE435F',b'timer_hz=0x0000000000000001'),
                    raw.replace(b'repeat=1 sample=0', b'repeat=1 sample=1'), raw+raw]:
            self.check_mutation(new,'benchmark')

    def test_official_corrupt_actual_logit(self):
        raw = (PACKAGE/'evidence/official-uart.bin').read_bytes()
        # Change one hex digit in an actual row; preserve source bytes elsewhere.
        start = raw.index(b'logits=') + len(b'logits=')
        new = raw[:start] + (b'0' if raw[start:start+1] != b'0' else b'1') + raw[start+1:]
        self.check_mutation(new,'official')

    def test_partial_progress_is_observed_only(self):
        raw = (PACKAGE/'evidence/report/E05-raw-04-uart.txt').read_bytes()
        part = raw[:raw.index(b'HAR_VALIDATION_PROGRESS samples=512')]
        value = observe(part,'validation')
        self.assertEqual(value['samples'],256)
        self.assertFalse(value['end_line'])

    def test_bridge_stop_runs_original_finally(self):
        root = Path(self.temp.name)
        entry = root/'ISOLATED_NO_HARDWARE_ENTRY.py'
        entry.write_text("import time\nfrom pathlib import Path\ntry:\n while True: time.sleep(.05)\nfinally:\n Path(__file__).with_suffix('.cleanup').write_text('finally executed')\n", encoding='utf-8')
        stop = root/'stop.request'
        p = subprocess.Popen([sys.executable,'-X','utf8','-B',str(BASE/'bridge.py'),str(stop),str(entry)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        time.sleep(.5)
        stop.touch()
        output = p.communicate(timeout=10)[0]
        self.assertEqual(p.returncode,130,output)
        self.assertTrue(entry.with_suffix('.cleanup').exists())

    def test_metadata_sharing_violation_is_bounded_retry(self):
        real_replace = os.replace
        count = []
        def replace(a,b):
            count.append(1)
            if len(count) < 3:
                raise PermissionError('isolated simulated sharing violation')
            return real_replace(a,b)
        with patch('util.os.replace', side_effect=replace):
            save(self.path,dict(test_fixture_only=True))
        self.assertEqual(read(self.path),dict(test_fixture_only=True))
        self.assertEqual(len(count),3)

    def test_interrupted_worker_cannot_become_passed(self):
        from server import Manager
        root = Path(self.temp.name)/'manager-data'
        job = root/('a'*32)
        save(job/'state.json',dict(id='a'*32,status='running',mode='replay',purpose='validation',created='2020-01-01T00:00:00+08:00',worker_pid=0))
        manager = Manager(PACKAGE,root,sys.executable)
        self.assertEqual(manager.jobs()[0]['status'],'needs_inspection')
        self.assertEqual(manager.detail('a'*32)['selected']['review'],None)
        with self.assertRaises(RuntimeError):
            manager.start(dict(mode='replay',history='validation'))

    def test_official_live_routing_requires_fresh_authorization(self):
        from server import Manager
        root = Path(self.temp.name) / 'ISOLATED_NO_HARDWARE_ROUTING'
        xilinx = root / 'fixture-xilinx'
        xsct = xilinx / 'Vitis/2022.2/bin/xsct.bat'
        xsct.parent.mkdir(parents=True)
        xsct.write_text('TEST FIXTURE ONLY; DO NOT EXECUTE', encoding='utf-8')
        manager = Manager(PACKAGE, root / 'runs', sys.executable)
        body = dict(mode='live', purpose='official', port='COM5', xilinx=str(xilinx), confirmations={})
        with self.assertRaisesRegex(ValueError, '逐项确认'):
            manager.start(body)
        self.assertEqual(list((root / 'runs').glob('*/request.json')), [])
        body['confirmations'] = {k: True for k in ['powered', 'jtag', 'exclusive', 'volatile']}
        with patch('server.subprocess.Popen') as spawn, patch('server.worker_busy', return_value=False):
            spawn.return_value.pid = 0
            started = manager.start(body)
        self.assertEqual(started['purpose'], 'official')
        self.assertEqual(started['dataset'], 'official_test')
        request = read(root / 'runs' / started['id'] / 'request.json')
        self.assertEqual(request['purpose'], 'official')
        self.assertEqual(request['dataset'], 'official_test')
        self.assertEqual(request['confirmations'], body['confirmations'])
        self.assertIn(str(BASE / 'worker.py'), spawn.call_args.args[0])

    def test_official_worker_adapter_timeout_and_exact_review(self):
        import worker
        actual = (PACKAGE / 'evidence/official-uart.bin').read_bytes()
        start = actual.index(b'logits=') + len(b'logits=')
        corrupt = actual[:start] + (b'0' if actual[start:start+1] != b'0' else b'1') + actual[start+1:]
        cases = [('retained-official-log', actual, 'completed'),
                 ('isolated-corrupt-logit', corrupt, 'failed'),
                 ('wrong-dataset-log', (PACKAGE / 'evidence/report/E05-raw-04-uart.txt').read_bytes(), 'failed')]
        for label, raw, expected in cases:
            with self.subTest(label=label):
                job = Path(self.temp.name) / 'ISOLATED_NO_HARDWARE_WORKER' / label
                save(job / 'request.json', dict(test_fixture_only=True, mode='live', purpose='official',
                     dataset='official_test', package=str(PACKAGE), port='COM5', xilinx='ISOLATED_STUB'))
                save(job / 'state.json', dict(test_fixture_only=True, id=label, mode='live', purpose='official',
                     dataset='official_test', status='queued', phase='Isolated fixture; no physical board',
                     review_status='pending', capture_exit_code=None))
                calls, wait_timeouts = [], []
                def isolated_process(argv, **kwargs):
                    argv = list(map(str, argv))
                    calls.append(argv)
                    if str(BASE / 'bridge.py') in argv:
                        self.assertEqual(argv[6], str(PACKAGE / 'tools/run_board.py'))
                        self.assertEqual(argv[argv.index('--purpose') + 1], 'official')
                        capture = Path(argv[argv.index('--out') + 1])
                        save(capture / 'result.json', dict(test_fixture_only=True, status='captured_unvalidated'))
                        (capture / 'uart.bin').write_bytes(raw)
                    process = MagicMock(pid=0)
                    def wait(timeout):
                        wait_timeouts.append(timeout)
                        return 0
                    process.wait.side_effect = wait
                    return process
                with patch('worker.subprocess.Popen', side_effect=isolated_process) as spawn:
                    worker.execute(job)
                result = read(job / 'state.json')
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['capture_exit_code'], 0)
                checked = read(job / 'review.json')
                if expected == 'completed':
                    self.assertEqual(checked['facts']['samples'], 2947)
                    self.assertEqual(checked['facts']['logits'], 17682)
                    self.assertEqual(checked['facts']['correct'], 2472)
                    self.assertEqual(checked['scope'], '独立逐logit核验')
                else:
                    self.assertEqual(checked['status'], 'failed')
                self.assertEqual(spawn.call_count, 2)
                # The wrapper must allow the original official collector's 300s plus cleanup.
                self.assertEqual(read(job / 'collector.command.json')['exit_code'], 0)
                self.assertEqual(len(calls), 2)
                self.assertEqual(wait_timeouts, [120, 350])


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='fusion150-http-test-')
        cls.data = Path(cls.temp.name)/'runs'
        cls.port = 18766
        cls.base = f'http://127.0.0.1:{cls.port}'
        cls.log = open(Path(cls.temp.name)/'server.log','wb')
        cls.proc = subprocess.Popen([sys.executable,'-X','utf8','-B',str(BASE/'server.py'),'--package',str(PACKAGE),'--data',str(cls.data),'--port',str(cls.port)],stdout=cls.log,stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                cls.config=cls.call('/api/config')[1]
                break
            except (OSError, ValueError):
                time.sleep(.1)
        else:
            raise RuntimeError('test server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)
        cls.log.close()
        cls.temp.cleanup()

    @classmethod
    def call(cls,path,body=None):
        headers={'Origin':cls.base}
        if body is not None:
            headers.update({'Content-Type':'application/json','X-Demo-Token':cls.config['token']})
        req=urllib.request.Request(cls.base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:
            r=urllib.request.urlopen(req,timeout=15)
        except urllib.error.HTTPError as exc:
            r=exc
        with r:
            return r.status,json.loads(r.read())

    def test_no_autorun_gets_concurrency_export_and_persistence(self):
        for path in ['/api/state','/api/ports','/api/config']:
            self.assertEqual(self.call(path)[0],200)
        self.assertEqual(list(self.data.glob('*/request.json')),[])
        barrier=threading.Barrier(12)
        def start(_):
            barrier.wait()
            return self.call('/api/start',dict(mode='replay',history='official'))
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(start,range(12)))
        self.assertEqual(sum(s==202 for s,v in results),1,results)
        self.assertEqual(sum(s==409 for s,v in results),11,results)
        job_id=next(v['id'] for s,v in results if s==202)
        for _ in range(200):
            state=self.call('/api/state?job='+job_id)[1]['selected']
            if state['status'] not in {'queued','running'} and 'export.zip' in state['files']:
                break
            time.sleep(.1)
        self.assertEqual(state['status'],'completed',state)
        self.assertEqual(state['review']['facts']['logits'],17682)
        self.assertIsNone(state['capture_exit_code'])
        # A new manager represents server restart and reads the same durable task.
        from server import Manager
        restored=Manager(PACKAGE,self.data,sys.executable).detail(job_id)['selected']
        self.assertEqual(restored['status'],'completed')
        self.assertEqual(len(list(self.data.glob('*/request.json'))),1)
        with zipfile.ZipFile(self.data/job_id/'export.zip') as z:
            self.assertIn('uart.bin',z.namelist())
            self.assertIn('review.json',z.namelist())
            self.assertEqual(z.read('uart.bin'),(PACKAGE/'evidence/official-uart.bin').read_bytes())
        status,chunk=self.call('/api/log?job='+job_id+'&stream=uart&offset=0')
        self.assertEqual(status,200)
        self.assertEqual(chunk['offset'],32768)
        self.assertEqual(chunk['total'],440343)
        self.assertEqual(self.call('/api/stop',dict(id=job_id))[0],400)
        self.assertEqual(self.call('/api/start',dict(mode='live',purpose='validation',port='COM5',xilinx='E:/vivado',confirmations={}))[0],400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
