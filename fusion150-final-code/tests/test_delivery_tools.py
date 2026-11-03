"""Offline regression checks; modified logs are isolated rejection fixtures only."""
from pathlib import Path
from types import SimpleNamespace
import json, sys, tempfile, unittest
P=Path(__file__).resolve().parents[1]
N=P.parent
sys.path.insert(0,str(P/'tools'))
from verify import output_outside_package, official_replay, sha
from build import Build

class DeliveryTools(unittest.TestCase):
    def test_package_outputs_rejected_without_writes(self):
        for out in (P,P/'output',P/'tools/review'):
            with self.subTest(out=out),self.assertRaisesRegex(RuntimeError,'outside'):
                output_outside_package(P,out)

    def test_external_output_accepted(self):
        self.assertEqual(output_outside_package(P,N/'test-output'),(N/'test-output').resolve())

    def test_record_binds_actual_manifest_and_candidate_separately(self):
        with tempfile.TemporaryDirectory(prefix='fpga-delivery-metadata-') as tmp:
            b=Build(SimpleNamespace(package=P,out=Path(tmp),xilinx=Path('E:/vivado')))
            b.stage('metadata',lambda out,record:None)
            m=json.loads((Path(tmp)/'metadata/manifest.json').read_text())
            self.assertEqual(m['package_manifest_sha256'],sha(P/'MANIFEST.json'))
            self.assertEqual(m['candidate_sha256'],sha(P/'candidate.json'))
            self.assertNotEqual(m['candidate_sha256'],m['package_manifest_sha256'])

    def test_original_official_log(self):
        r=official_replay(P)
        self.assertEqual((r['samples'],r['logits'],r['correct']),(2947,17682,2472))
        self.assertAlmostEqual(r['accuracy'],2472/2947)
        self.assertGreater(r['device_elapsed_seconds_including_uart'],38)

    def reject_fixture(self,old,new,message):
        raw=(P/'evidence/official-uart.bin').read_bytes()
        self.assertIn(old,raw)
        with tempfile.TemporaryDirectory(prefix='fpga-isolated-log-fixture-') as tmp:
            fixture=Path(tmp)/'intentionally-invalid-uart.bin'
            fixture.write_bytes(raw.replace(old,new,1))
            with self.assertRaisesRegex(RuntimeError,message):official_replay(P,fixture)

    def test_wrong_firmware_token_rejected(self):
        self.reject_fixture(b'token=1d32',b'token=ffff','token')

    def test_inconsistent_timing_rejected(self):
        self.reject_fixture(b'timer_hz=333333343',b'timer_hz=333333344','timing')

    def test_truncated_capture_rejected(self):
        with tempfile.TemporaryDirectory(prefix='fpga-isolated-log-fixture-') as tmp:
            p=Path(tmp)/'intentionally-truncated-uart.bin'
            p.write_bytes((P/'evidence/official-uart.bin').read_bytes()[:-1])
            with self.assertRaisesRegex(RuntimeError,'Truncated'):official_replay(P,p)

if __name__=='__main__':unittest.main(verbosity=2)
