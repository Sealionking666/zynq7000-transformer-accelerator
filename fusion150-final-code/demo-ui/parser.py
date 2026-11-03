"""Read UART without inference or downloads. Acceptance is deliberately separate."""
from pathlib import Path
import importlib.util
import re
import statistics


def load_verify(package):
    spec = importlib.util.spec_from_file_location('final_delivery_verify', Path(package) / 'tools/verify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def token(package, purpose):
    text = (Path(package) / f'software/ps/{purpose}/build_identity.h').read_text(encoding='utf-8')
    return re.search(r'HAR_BUILD_TOKEN\s+"([0-9a-f]+)"', text)[1]


def lines_of(raw, complete=False):
    text = raw.decode('ascii', errors='replace')
    # The deployed xil_printf produces CRCRLF. Accept that notation, never fabricate rows.
    lines = [s for s in text.splitlines() if s]
    if not complete and raw and not raw.endswith(b'\n') and lines:
        lines.pop()
    return lines


def observe(raw, purpose):
    lines = lines_of(raw)
    result = dict(purpose=purpose, bytes=len(raw), end_line=False, samples=None,
                  total={'validation': 1796, 'benchmark': 66, 'official': 2947}[purpose],
                  measured=None, correct=None, accuracy=None, logits=None,
                  classification=[], timing=None, failure=None)
    fail = next((s for s in lines if '_FAIL' in s), None)
    result['failure'] = fail
    if purpose == 'validation':
        for s in lines:
            m = re.fullmatch(r'HAR_VALIDATION_PROGRESS samples=(\d+) checksum=([0-9a-fA-F]{8})', s)
            if m:
                result['samples'] = int(m[1])
            m = re.fullmatch(r'HAR_VALIDATION_PASS samples=(\d+) logits=(\d+) raw32_calls=(\d+) correct=(\d+) checksum=([0-9a-fA-F]{8})', s)
            if m:
                result.update(end_line=True, samples=int(m[1]), logits=int(m[2]), correct=int(m[4]))
    elif purpose == 'official':
        for s in lines:
            m = re.fullmatch(r'HAR_OFFICIAL_SAMPLE sample=(\d+) label=(\d+) prediction=(\d+) calls=(\d+) input_checksum=([0-9a-fA-F]{8}) logits=(.*)', s)
            if m:
                result['classification'].append(dict(sample=int(m[1]), label=int(m[2]), prediction=int(m[3]), logits_hex=m[6]))
        result['samples'] = len(result['classification']) or None
        result['classification'] = result['classification'][-12:]
        for s in lines:
            m = re.fullmatch(r'HAR_OFFICIAL_PASS samples=(\d+) logits=(\d+) calls=(\d+) correct=(\d+) input_checksum=([0-9a-fA-F]{8}) checksum=([0-9a-fA-F]{8})', s)
            if m:
                result.update(end_line=True, samples=int(m[1]), logits=int(m[2]), correct=int(m[4]))
    else:
        rows = [re.fullmatch(r'HAR_SAMPLE_PASS repeat=(\d+) sample=(\d+) warmup=(\d+) cpu_ticks=0x([0-9a-fA-F]{16}) pspl_ticks=0x([0-9a-fA-F]{16}) ', s) for s in lines]
        rows = [m for m in rows if m]
        result['samples'] = len(rows) or None
        result['measured'] = sum(m[3] == '0' for m in rows)
        hz = next((re.fullmatch(r'timer_hz=0x([0-9a-fA-F]{16}) ', s) for s in lines if s.startswith('timer_hz=')), None)
        if hz and int(hz[1], 16) > 0 and result['measured']:
            frequency = int(hz[1], 16)
            pspl = [int(m[5], 16) / frequency * 1e6 for m in rows if m[3] == '0']
            cpu = [int(m[4], 16) / frequency * 1e6 for m in rows if m[3] == '0']
            result['timing'] = dict(timer_hz=frequency, measured=len(pspl), pspl_median_us=statistics.median(pspl),
                                    cpu_median_us=statistics.median(cpu), pspl_min_us=min(pspl), pspl_max_us=max(pspl),
                                    scope='内存Q16至完整PS/PL logits；含生产复制、guard/poison/cache/control；排除6次预热、下载和UART')
        result['end_line'] = any(re.fullmatch(r'HAR_BOARD_PASS measured_inferences=\d+ logits=\d+ raw32_calls=\d+', s) for s in lines)
    if result['correct'] is not None and result['samples']:
        result['accuracy'] = result['correct'] / result['samples']
    return result


def review(path, purpose, package):
    """Fail closed on incomplete/mixed logs. Do not upgrade firmware reports to raw-logit proof."""
    raw = Path(path).read_bytes()
    observed = observe(raw, purpose)
    answer = dict(status='failed', scope='', reason='', observation=observed, numerical='尚未取得')
    try:
        def need(ok, why):
            if not ok:
                raise ValueError(why)
        need(raw.endswith(b'\n'), '日志被截断，缺少完整换行')
        lines = lines_of(raw, complete=True)
        need(not observed['failure'], observed['failure'] or '固件失败')
        need(lines and lines[0] == 'HAR_PROFILE name=fused-guard4k-v1 token=' + token(package, purpose) + ' guard_bytes=4160', '固件profile/token不符')
        if purpose == 'official':
            facts = load_verify(package).official_replay(Path(package), Path(path))
            answer.update(status='passed', scope='独立逐logit核验', reason='2947条 / 17682 logits与冻结参考精确一致', numerical='独立逐logit验证通过', facts=facts)
        elif purpose == 'validation':
            expected = ['HAR_VALIDATION_BEGIN samples=1796']
            frozen = Path(package) / 'evidence/report/E05-raw-04-uart.txt'
            frozen_lines = lines_of(frozen.read_bytes(), complete=True)
            expected.extend(frozen_lines[2:])
            # Exact progress checksums and terminal bind this aggregate contract.
            need([s.lower() for s in lines[1:]] == [s.lower() for s in expected], '进度覆盖、checksum、样本/调用/正确数或结束汇总不符')
            need(len(lines) == 11 and observed['samples'] == 1796 and observed['correct'] == 1449, '开发集汇总不完整')
            answer.update(status='passed', scope='独立汇总核验（非逐logit）',
                          reason='1796样本、8个进度checksum、10776 logits计数、1796调用及最终bd0b22ad一致；原固件负责逐值比较',
                          numerical='固件报告数值通过；独立核对汇总通过',
                          limitation='UART不输出逐样本logits/分类，不能独立重建逐值比较或分类明细')
        else:
            need(len(lines) == 70, '基准日志须含66条调用、频率及唯一开始/结束行')
            need(lines[1] == 'HAR_BOARD_BEGIN contract=int8-nearest-q16-v1 samples=6 repeats=10 fused=1', '基准开始行不符')
            need(lines[2] == 'timer_hz=0x0000000013DE435F ', '设备计时器频率与原BSP不符')
            for i, s in enumerate(lines[3:-1]):
                m = re.fullmatch(r'HAR_SAMPLE_PASS repeat=(\d+) sample=(\d+) warmup=(\d+) cpu_ticks=0x([0-9a-fA-F]{16}) pspl_ticks=0x([0-9a-fA-F]{16}) ', s)
                need(m is not None, f'基准第{i}行格式不符')
                need(tuple(map(int, m.groups()[:3])) == (i // 6, i % 6, int(i < 6)), f'基准第{i}行顺序/预热标志不符')
                need(int(m[4], 16) > 0 and int(m[5], 16) > 0, '设备ticks须大于零')
            need(lines[-1] == 'HAR_BOARD_PASS measured_inferences=60 logits=360 raw32_calls=66', '基准结束计数不符')
            answer.update(status='passed', scope='独立计时与覆盖核验（非逐logit）', reason='66条顺序正确；排除6预热，60次正式计时；原固件负责PL/ARM/冻结参考逐值比较',
                          numerical='固件报告数值通过；独立计时核验通过', limitation='基准UART不含逐项logits、预测类别或标签')
    except Exception as exc:
        answer.update(status='failed', reason=str(exc), numerical='未通过独立核验')
    return answer
