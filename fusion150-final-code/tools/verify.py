"""Verify the final source delivery using package-relative paths only."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import zipfile


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def resolve(root, name):
    p = (Path(root) / name).resolve()
    p.relative_to(Path(root).resolve())
    return p


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def output_outside_package(root, output):
    """Reject accidental build/review outputs inside the sealed source tree."""
    root, output = Path(root).resolve(), Path(output).resolve()
    need(output != root and root not in output.parents,
         'Output must be outside the package: ' + str(output))
    return output


def fnv(values, state=2166136261):
    for value in values:
        state = ((state ^ (value & 0xffffffff)) * 16777619) & 0xffffffff
    return state


def official_replay(root, uart_path=None):
    vector_root = root / 'tests/official'
    expected = list(struct.unpack('<17682i', (vector_root / 'expected-logits-q16.bin').read_bytes()))
    labels = list(struct.unpack('<2947i', (vector_root / 'labels-i32.bin').read_bytes()))
    raw_inputs = (vector_root / 'input-q16.bin').read_bytes()
    need(len(raw_inputs) == 2947 * 1152 * 4, 'Official input length differs')
    uart_path = Path(uart_path) if uart_path is not None else root / 'evidence/official-uart.bin'
    raw = uart_path.read_bytes()
    need(raw.endswith(b'\n'), 'Truncated official UART')
    lines = [line for line in raw.decode('ascii').splitlines() if line]
    need(len(lines) == 2951, 'Official UART sample coverage differs')
    identity = (root / 'software/ps/official/build_identity.h').read_text(encoding='utf-8')
    token = re.search(r'#define\s+HAR_BUILD_TOKEN\s+"([0-9a-f]+)"', identity)
    need(token is not None, 'Missing official firmware identity')
    need(lines[0] == 'HAR_PROFILE name=fused-guard4k-v1 token=' + token[1] + ' guard_bytes=4160',
         'Wrong UART profile or official firmware token')
    need(lines[1] == 'HAR_OFFICIAL_BEGIN samples=2947 logits=17682 input_sha256=' +
         sha(vector_root / 'input-q16.bin') + ' oracle_sha256=' + sha(vector_root / 'expected-logits-q16.bin'),
         'Official input/oracle identity differs')
    pattern = r'HAR_OFFICIAL_SAMPLE sample=(\d+) label=(\d+) prediction=(\d+) calls=(\d+) input_checksum=([0-9a-fA-F]{8}) logits=' + ','.join([r'([0-9a-fA-F]{8})'] * 6)
    cm = [[0] * 6 for _ in range(6)]
    ih = 2166136261
    actual = []
    for i, line in enumerate(lines[2:2949]):
        m = re.fullmatch(pattern, line)
        need(m is not None, 'Malformed official row ' + str(i))
        index, label, predicted, calls = map(int, m.groups()[:4])
        values = [int(m[j], 16) for j in range(6, 12)]
        values = [v - 2**32 if v >= 2**31 else v for v in values]
        need(index == i and calls == i + 1 and label == labels[i], 'Official order/label differs')
        need(values == expected[i*6:i*6+6], 'Physical-board logit differs at ' + str(i))
        need(predicted == max(range(6), key=lambda j: values[j]), 'Prediction differs')
        sample = struct.unpack_from('<1152i', raw_inputs, i * 1152 * 4)
        ih = fnv(sample, ih)
        need(ih == int(m[5], 16), 'Input checksum differs at ' + str(i))
        actual.extend(values)
        cm[label][predicted] += 1
    checksum = fnv(actual)
    correct = sum(cm[i][i] for i in range(6))
    timing = re.fullmatch(r'HAR_OFFICIAL_TIME begin=([0-9a-fA-F]{16}) end=([0-9a-fA-F]{16}) '
                          r'ticks=([0-9a-fA-F]{16}) timer_hz=(\d+)', lines[-2])
    need(timing is not None, 'Malformed official device timing')
    begin, end, ticks = (int(timing[i], 16) for i in (1, 2, 3))
    timer_hz = int(timing[4])
    need(ticks > 0 and (end - begin) % (1 << 64) == ticks and timer_hz == 333333343,
         'Official device timing differs from the deployed BSP contract')
    terminal = re.sub(r'(input_checksum|checksum)=([0-9a-fA-F]{8})',
                      lambda m: m[1] + '=' + m[2].lower(), lines[-1])
    need(terminal == f'HAR_OFFICIAL_PASS samples=2947 logits=17682 calls=2947 correct={correct} input_checksum={ih:08x} checksum={checksum:08x}',
         'Official terminal differs')
    need(correct == 2472 and checksum == 0xfe0d23fe, 'Frozen official aggregate differs')
    macro = sum(2 * cm[i][i] / (sum(cm[i]) + sum(cm[j][i] for j in range(6))) for i in range(6)) / 6
    return {'samples': 2947, 'logits': len(actual), 'correct': correct,
            'accuracy': correct / 2947, 'macro_f1': macro,
            'checksum': f'{checksum:08x}', 'confusion_matrix': cm,
            'raw_uart_sha256': sha(uart_path), 'device_elapsed_seconds_including_uart': ticks / timer_hz,
            'scope': 'Offline replay of supplied official UART against frozen vectors; no board access; not an inference latency benchmark'}


def verify(root):
    root = Path(root).resolve()
    manifest = read(root / 'MANIFEST.json')
    need(manifest['schema'] == 'fusion150-final-code-manifest/1', 'Unknown manifest schema')
    need((root / 'MANIFEST.sha256').read_text().strip() == sha(root / 'MANIFEST.json') + '  MANIFEST.json',
         'Manifest digest differs')
    rows = manifest['files']
    expected = {v['path'] for v in rows}
    need(len(expected) == len(rows), 'Duplicate manifest member')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()
              and '.git' not in p.relative_to(root).parts and '__pycache__' not in p.parts
              and p.suffix != '.pyc'}
    need(actual == expected | {'MANIFEST.json', 'MANIFEST.sha256'}, 'Missing or unlisted delivery file')
    for row in rows:
        path = resolve(root, row['path'])
        need(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'File differs: ' + row['path'])
    for name, row in read(root / 'model/freeze/model.lock.json')['files'].items():
        path = resolve(root / 'model', name)
        need(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'Final model differs: ' + name)
    staged = 0
    for role, members in read(root / 'source-map.json').items():
        for destination, source in members.items():
            resolve(root / '_hypothetical_staging' / role, destination)
            need(resolve(root, source).is_file(), 'Missing staged input: ' + source)
            staged += 1
    candidate = read(root / 'candidate.json')
    need(sha(root / 'release/hardware.bit') == candidate['deployed_bit_sha256'], 'Wrong deployed bit')
    need(sha(root / 'release/hardware.xsa') == candidate['original_XSA_sha256'], 'Wrong XSA')
    with zipfile.ZipFile(root / 'release/hardware.xsa') as z:
        for suffix, target in [('.bit', 'hardware.bit'), ('ps7_init.tcl', 'ps7_init.tcl')]:
            names = [n for n in z.namelist() if n.endswith(suffix)]
            need(len(names) == 1 and hashlib.sha256(z.read(names[0])).hexdigest() == sha(root / 'release' / target),
                 'XSA embedded artifact differs')
    return {'status': 'final_code_content_verified', 'files': len(rows),
            'bytes': sum(v['bytes'] for v in rows), 'staged_inputs': staged,
            'model_locked_files': 31, 'official_board_log_replay': official_replay(root),
            'historical_absolute_paths_used': False, 'board_actions': False}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--out', type=Path)
    ap.add_argument('--official-uart', type=Path,
                    help='Also replay a new official-purpose uart.bin; no board access')
    args = ap.parse_args()
    if args.out:
        args.out = output_outside_package(args.package, args.out)
    result = verify(args.package)
    if args.official_uart:
        result['supplied_official_capture_replay'] = official_replay(args.package.resolve(), args.official_uart)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
