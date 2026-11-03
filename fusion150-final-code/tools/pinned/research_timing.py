"""Read-only AMD 2022.2 research clock/STA replay; never standard acceptance.

No executor imports, monkeypatches, vendor launches or board actions. A contract
declares one operating point per SoC, independently of HLS scheduling and APU
timer units. Original manifests/reports are never rewritten.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import xml.etree.ElementTree as ET
import zipfile
from common import read, require, sha

NUM = r'-?\d+(?:\.\d+)?'
COVERAGE = {'no_clock', 'constant_clock', 'pulse_width_clock',
            'unconstrained_internal_endpoints', 'no_input_delay', 'no_output_delay',
            'multiple_clock', 'generated_clocks', 'loops', 'partial_input_delay',
            'partial_output_delay', 'latch_loops'}


def positive(value):
    require(type(value) in (int, float, str), 'Invalid declared number')
    try:
        n = Decimal(str(value))
    except InvalidOperation as exc:
        raise RuntimeError('Invalid declared number') from exc
    require(n.is_finite() and n > 0, 'Nonpositive/nonfinite declared number')
    return n


def clocks(text, summary=False):
    if summary:
        parts = text.split('| Clock Summary')
        require(len(parts) == 2, 'Missing/duplicate clock summary')
        text = parts[1].split('| Intra Clock Table')[0]
        rows = re.findall(r'^(\S+)\s+\{[^}\n]+\}\s+('+NUM+r')\s+('+NUM+r')\s*$', text, re.M)
    else:
        rows = re.findall(r'^(\S+)\s+('+NUM+r')\s+\{[^}\n]+\}[^\n]*$', text, re.M)
    require(rows and len({r[0] for r in rows}) == len(rows), 'Missing/duplicate routed clocks')
    result = {r[0]: positive(r[1]) for r in rows}
    if summary:
        require(all(abs(Decimal(r[2])-1000/result[r[0]]) <= Decimal('.02') for r in rows),
                'Clock frequency/period disagree')  # summary MHz is rounded
    return result


def timing_summary(text):
    parts = text.split('| Design Timing Summary')
    require(len(parts) == 2, 'Missing/duplicate design timing summary')
    body = parts[1].split('| Clock Summary')[0]
    rows = re.findall(r'^\s*('+NUM+r'(?:\s+'+NUM+r'){11})\s*$', body, re.M)
    require(len(rows) == 1, 'Incomplete setup/hold/pulse summary')
    nums = list(map(Decimal, rows[0].split()))
    result = {}
    for i, name in enumerate(('setup', 'hold', 'pulse_width')):
        slack, total_slack, failing, endpoints = nums[i*4:i*4+4]
        require(slack >= 0 and total_slack == 0 and failing == 0 and endpoints > 0
                and endpoints == int(endpoints), 'Timing failed/missing endpoints: '+name)
        result[name] = dict(worst_slack_ns=float(slack), total_negative_slack_ns=float(total_slack),
                            failing_endpoints=int(failing), total_endpoints=int(endpoints))
    require('All user specified timing constraints are met.' in body, 'Missing STA pass statement')
    require(re.search(r'Enable Multi Corner Analysis\s*:\s*Yes', text) is not None,
            'Missing multi-corner analysis')
    require(re.search(r'Ignore I/O Paths\s*:\s*No', text) is not None, 'I/O analysis disabled/missing')
    for corner in ('Slow', 'Fast'):
        require(len(re.findall(r'^\s*'+corner+r'\s+Yes\s+Yes\s*$', text, re.M)) == 1,
                'Missing max/min corner: '+corner)
    return result


def coverage(text):
    rows = re.findall(r'checking ([a-z_]+) \((\d+)\)', text)
    require(COVERAGE <= {r[0] for r in rows} and all(int(n) == 0 for _, n in rows)
            and all(sum(n == key for n, _ in rows) >= 2 for key in COVERAGE),
            'Timing coverage missing/failed')


def warnings(text, name):
    require('Report' in text and 'REPORT SUMMARY' in text, 'Malformed report: '+name)
    require(not re.search(r'\|\s*(?:Error|Critical Warning)\s*\|', text, re.I),
            'DRC/methodology error or critical warning')
    count = re.search(r'Violations found:\s*(\d+)', text)
    rows = re.findall(r'\|\s*([A-Z][A-Z0-9_-]+)\s*\|\s*(Warning|Advisory)\s*\|[^|]*\|\s*(\d+)\s*\|', text)
    details = re.findall(r'^([A-Z][A-Z0-9_-]+)#\d+\s+(Warning|Advisory)\s*\n(.*?)^Related violations:', text, re.M | re.S)
    require(count is not None and sum(int(n) for _, _, n in rows) == int(count[1]) == len(details)
            and text.count('Related violations:') == int(count[1]), 'Incomplete violation report: '+name)
    for rule, severity, n in rows:
        require(sum(r == rule and s == severity for r, s, _ in details) == int(n), 'Violation count mismatch')
    return [dict(rule=r, severity=s, report=name, detail=' '.join(d.split())) for r, s, d in details]


def reports(soc, expected):
    """Check complete routed reports; usable on a retained failed-build folder too."""
    soc = Path(soc); directory = soc/'impl_reports'
    texts = {n: (directory/n).read_text(errors='replace') for n in
             ('timing_summary.rpt', 'clocks.rpt', 'check_timing.rpt', 'setup_paths.rpt',
              'hold_paths.rpt', 'utilization.rpt', 'drc.rpt', 'methodology.rpt')}
    timing = timing_summary(texts['timing_summary.rpt'])
    coverage(texts['check_timing.rpt']); coverage(texts['timing_summary.rpt'])
    actual = clocks(texts['clocks.rpt']); declared = {k: positive(v) for k, v in expected.items()}
    require(actual == declared == clocks(texts['timing_summary.rpt'], True), 'Routed clock differs from exact declaration')
    identities = []
    for n in ('timing_summary.rpt', 'setup_paths.rpt', 'hold_paths.rpt'):
        t = texts[n]; design = re.findall(r'^\| Design\s*:\s*(\S+)\s*$', t, re.M)
        speed = re.findall(r'^\| Speed File\s*:\s*(-\d+)\s', t, re.M)
        require(len(design) == len(speed) == 1 and speed[0] == '-2', 'Missing/wrong design/speed grade')
        identities.append((design[0], speed[0]))
    require(len(set(identities)) == 1, 'Mixed timing report designs')
    for name, kind in [('setup_paths.rpt', 'setup'), ('hold_paths.rpt', 'hold')]:
        t = texts[name]; slacks = re.findall(r'Slack \(MET\)\s*:\s*('+NUM+r')ns', t)
        require(slacks and all(Decimal(x) >= 0 for x in slacks)
                and float(min(map(Decimal, slacks))) == timing[kind]['worst_slack_ns'],
                'Missing/mismatched worst path: '+kind)
        require(('Setup (Max at Slow Process Corner)' if kind == 'setup' else 'Hold (Min at Fast Process Corner)') in t,
                'Missing path corner: '+kind)
        periods = re.findall(r'clocked by (\S+)\s+\{[^}]*period=('+NUM+r')ns\}', t)
        require(periods and all(c in actual and Decimal(p) == actual[c] for c, p in periods),
                'Path clock differs from routed declaration')
    log = (soc/'build_impl.log').read_text(errors='replace')
    for key, kind in [('WNS', 'setup'), ('WHS', 'hold')]:
        vals = re.findall(key+r'\s*[=:]\s*('+NUM+r')', log)
        require(vals and float(vals[-1]) == timing[kind]['worst_slack_ns'], 'Log/STA mismatch: '+key)
    usage = {}
    for label, key, limit in [('Slice LUTs', 'lut', 53200), ('Slice Registers', 'ff', 106400),
                              ('Block RAM Tile', 'bram_tiles', 140), ('DSPs', 'dsp', 220)]:
        m = re.search(r'\|\s*'+re.escape(label)+r'\s*\|\s*('+NUM+r')', texts['utilization.rpt'])
        require(m is not None and 0 <= Decimal(m[1]) <= limit, 'Missing/overcapacity resource: '+key)
        usage[key] = float(m[1])
    details = [d for n in ('drc.rpt', 'methodology.rpt') for d in warnings(texts[n], n)]
    return dict(timing=timing, clocks_ns={k: float(v) for k, v in actual.items()}, resources=usage,
                warning_details=details, warning_disposition='not_adjudicated', design=identities[0][0],
                setup_margin_fraction=timing['setup']['worst_slack_ns']/float(min(actual.values())))


def file_map(folder, expected):
    require(isinstance(expected, dict) and expected, 'Missing retained file hashes')
    actual = {p.relative_to(folder).as_posix(): sha(p) for p in Path(folder).rglob('*') if p.is_file()}
    require(actual == expected, 'Retained file set/hash differs: '+str(folder))


def review(soc, contract):
    soc = Path(soc).resolve()
    require(contract.get('schema') == 'research-timing-contract/1', 'Unknown timing contract')
    require(sha(soc/'manifest.json') == contract['soc_manifest_sha256'], 'SoC manifest hash differs')
    meta = read(soc/'manifest.json'); require(meta['status'] == 'passed', 'SoC build did not pass')
    file_map(soc/'impl_reports', meta['reports_sha256']); file_map(soc/'artifacts', meta['artifacts_sha256'])
    for n, h in meta['generated_tcl_sha256'].items():
        require(PurePosixPath(n).name == n and sha(soc/n) == h, 'Generated Tcl hash differs')
    require(sha(soc/'hls-ip-manifest.json') == meta['hls_manifest_sha256'], 'HLS IP manifest differs')
    ip = read(soc/'hls-ip-manifest.json'); compiled = read(soc/'hls-compiled-source.json')
    require(sha(soc/'hls-compiled-source.json') == ip['dependency_sha256']
            and ip['build_token'] == compiled['build_token'] == meta['hls_build_token']
            and ip['source_commit'] == compiled['source_commit'] == meta['kernel_commit']
            and ip['ip_files'] == meta['ip_files'], 'HLS/SoC source generation differs')
    require(positive(compiled['clock_ns']) == positive(contract['hls_target_ns']), 'HLS target differs')
    result = reports(soc, contract['clocks_ns'])
    request = positive(contract['requested_fabric_mhz'])
    matches = re.findall(r'CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ\s+\{('+NUM+r')\}', (soc/'bd.tcl').read_text())
    require(len(matches) == 1 and Decimal(matches[0]) == request, 'Requested SoC clock differs')
    bits = list((soc/'artifacts').glob('*.bit')); xsas = list((soc/'artifacts').glob('*.xsa'))
    require(len(bits) == len(xsas) == 1, 'Ambiguous/missing bit or XSA')
    with zipfile.ZipFile(xsas[0]) as z:
        bs = [n for n in z.namelist() if n.endswith('.bit')]
        hs = [n for n in z.namelist() if n.endswith('.hwh')]
        ps = [n for n in z.namelist() if n.endswith('ps7_init.tcl')]
        require(len(bs) == len(hs) == len(ps) == 1, 'Incomplete XSA')
        require(hashlib.sha256(z.read(bs[0])).hexdigest() == sha(bits[0]), 'XSA/bit mismatch')
        hwh = ET.fromstring(z.read(hs[0])); ps_digest = hashlib.sha256(z.read(ps[0])).hexdigest()
    modules = [m for m in hwh.findall('.//MODULE') if m.get('MODTYPE') == 'processing_system7']
    require(len(modules) == 1, 'Missing/ambiguous PS7 in XSA')
    params = {p.get('NAME'): p.get('VALUE') for p in modules[0].findall('./PARAMETERS/PARAMETER')}
    require(positive(params['PCW_FPGA0_PERIPHERAL_FREQMHZ']) == request, 'XSA/requested clock mismatch')
    fclk = positive(params['PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ'])
    require(fclk == positive(contract['xsa_actual_fabric_mhz']), 'XSA actual frequency differs from declaration')
    sta_period = positive(contract['clocks_ns']['clk_fpga_0'])
    # Vivado 2022.2 may truncate a period to 3 decimals, while HWH exports
    # 6-decimal MHz. Allow only that reporting precision, not a clock band.
    delta = sta_period-1000/fclk
    require(-Decimal('.001001') <= delta <= Decimal('.0005'),
            'STA/XSA clock differs beyond report precision')
    timer = positive(contract['timer_hz'])
    require(timer == int(timer), 'Timer Hz must be an integer')
    hz = int(timer); arms = contract['arm_manifests']
    require(arms, 'Missing ARM clock/timer evidence')
    for ref in arms:
        path = Path(ref['path']); require(sha(path) == ref['sha256'], 'ARM manifest hash differs')
        arm = read(path); folder = path.parent; build = Path(arm['build_directory'])
        require(arm['status'] == 'passed' and arm['soc_dependency_sha256'] == sha(soc/'manifest.json')
                and arm['timer_hz'] == hz and arm['bit_sha256'] == sha(bits[0])
                and arm['xsa_sha256'] == sha(xsas[0]) and arm['ps7_init_sha256'] == ps_digest,
                'ARM/SoC/timer binding differs')
        require(sha(folder/'ps7_init.tcl') == ps_digest and sha(folder/'application.elf') == arm['elf_sha256'],
                'ARM download artifact differs')
        file_map(build/'bsp', arm['bsp_sha256'])
        xp = (build/'bsp/ps7_cortexa9_0/include/xparameters.h').read_text()
        values = re.findall(r'^#define XPAR_CPU_CORTEXA9_0_CPU_CLK_FREQ_HZ\s+(\d+)\s*$', xp, re.M)
        require(len(values) == 1 and int(values[0])//2 == hz
                and abs(Decimal(values[0])-positive(params['PCW_ACT_APU_PERIPHERAL_FREQMHZ'])*1000000) <= 1,
                'BSP/APU timer frequency differs')
    # Detect changing retained evidence rather than certifying a mixed read.
    require(sha(soc/'manifest.json') == contract['soc_manifest_sha256'], 'SoC changed during review')
    file_map(soc/'impl_reports', meta['reports_sha256']); file_map(soc/'artifacts', meta['artifacts_sha256'])
    result.update(schema='research-timing-review/1', status='reports_and_clock_bindings_passed', checker_sha256=sha(__file__),
                  soc=str(soc), soc_manifest_sha256=sha(soc/'manifest.json'),
                  hls_target_ns=float(positive(contract['hls_target_ns'])),
                  requested_fabric_mhz=float(request), xsa_actual_fabric_mhz=float(fclk), timer_hz=hz,
                  sta_vs_xsa_period_delta_ns=float(sta_period-1000/fclk),
                  kernel_commit=meta['kernel_commit'], arm_manifests=arms,
                  formal_acceptance=False, standard_best_changed=False, board_actions=False,
                  limitations=['Retained evidence only; no independent board/clock instrument measurement.',
                               'Git source replay, numerical/RTL coverage, raw UART and matched comparison require separate review.',
                               'Warnings are preserved, not accepted. Thin nonnegative slack is not a failed STA or guaranteed future margin.'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--soc', required=True, type=Path)
    parser.add_argument('--contract', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path, help='Fresh evidence directory')
    args = parser.parse_args()
    require(not args.out.resolve().is_relative_to(args.soc.resolve()), 'Review output must be outside original SoC')
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        contract = read(args.contract)
        result = review(args.soc, contract)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, zipfile.BadZipFile, ET.ParseError) as exc:
        result = dict(schema='research-timing-review/1', status='rejected_or_incomplete',
                      error=type(exc).__name__+': '+str(exc), formal_acceptance=False,
                      standard_best_changed=False, board_actions=False)
    result['checker_sha256'] = sha(__file__)
    result['contract_sha256'] = sha(args.contract) if args.contract.is_file() else None
    (args.out/'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    summary = {k: result[k] for k in ('schema', 'status', 'error', 'timing', 'clocks_ns', 'hls_target_ns',
               'requested_fabric_mhz', 'xsa_actual_fabric_mhz', 'timer_hz', 'formal_acceptance',
               'standard_best_changed', 'board_actions') if k in result}
    summary['review'] = str((args.out/'review.json').resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'reports_and_clock_bindings_passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
