"""Observe research clock/build facts, including failed runs; never acceptance.

Read explicit retained files (or an explicitly supplied failed-build report
directory). No executor imports, EDA, board actions or historical rewrites.
Planned clocks, PS7 requests/configuration, STA and controller status are separate.
"""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile
from common import read, require, save, sha
from research_timing import NUM, clocks, positive

PARAMS = ('PCW_FPGA0_PERIPHERAL_FREQMHZ', 'PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ',
          'PCW_FCLK0_PERIPHERAL_CLKSRC', 'PCW_FCLK0_PERIPHERAL_DIVISOR0',
          'PCW_FCLK0_PERIPHERAL_DIVISOR1', 'PCW_ACT_APU_PERIPHERAL_FREQMHZ')


def parameters(text):
    result = {}
    for key in PARAMS:
        values = re.findall(r'CONFIG\.'+key+r'(?:\s*=\s*([^\r\n]+)|\s+\{([^}\r\n]+)\})', text)
        require(len(values) <= 1, 'Duplicate generated PS7 parameter: '+key)
        if values:
            result[key] = next(v.strip() for v in values[0] if v.strip())
    return result


def summary(text):
    parts = text.split('| Design Timing Summary')
    require(len(parts) == 2, 'Missing/duplicate timing summary')
    body = parts[1].split('| Clock Summary')[0]
    rows = re.findall(r'^\s*('+NUM+r'(?:\s+'+NUM+r'){11})\s*$', body, re.M)
    require(len(rows) == 1, 'Missing/ambiguous setup/hold/pulse values')
    values = list(map(Decimal, rows[0].split())); result = {}
    for i, kind in enumerate(('setup', 'hold', 'pulse_width')):
        slack, total, failing, endpoints = values[4*i:4*i+4]
        require(failing == int(failing) and endpoints == int(endpoints)
                and 0 <= failing <= endpoints and endpoints > 0, 'Invalid endpoint counts')
        result[kind] = dict(worst_slack_ns=float(slack), total_negative_slack_ns=float(total),
                            failing_endpoints=int(failing), total_endpoints=int(endpoints))
    passed = all(r['worst_slack_ns'] >= 0 and r['total_negative_slack_ns'] == 0
                 and r['failing_endpoints'] == 0 for r in result.values())
    return dict(values=result, summary_status='nonnegative_summary' if passed else 'violated_summary',
                full_timing_review=False)


def configuration(path, intent=None):
    """Cheap PS7 report check after BD generation, before implementation."""
    path = Path(path).resolve(); digest = sha(path); params = parameters(path.read_text())
    actual = params.get('PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ')
    requested = params.get('PCW_FPGA0_PERIPHERAL_FREQMHZ')
    require(actual is not None and requested is not None, 'Missing generated/requested PS7 frequency')
    actual = positive(actual); requested = positive(requested)
    intent = {} if intent is None else intent
    require(isinstance(intent, dict) and set(intent) <= {'clocks_ns', 'xsa_actual_fabric_mhz'}, 'Unknown clock intent fields')
    target = intent.get('xsa_actual_fabric_mhz')
    expected = {k: positive(v) for k,v in intent.get('clocks_ns', {}).items()}
    mismatch = target is not None and positive(target) != actual
    # BD configuration has not run STA; only compare intended clk_fpga_0 to
    # the generated frequency at the same documented report precision.
    if 'clk_fpga_0' in expected:
        delta = expected['clk_fpga_0']-1000/actual
        mismatch |= not -Decimal('.001001') <= delta <= Decimal('.0005')
    require(sha(path) == digest, 'Configuration changed during observation')
    return dict(schema='research-clock-configuration/1', configured_fabric_mhz=float(actual),
        requested_fabric_mhz=float(requested), params=params, intent=intent,
        target_status='mismatch' if mismatch else 'not_declared' if not intent else
                      'incomplete' if set(expected)-{'clk_fpga_0'} else 'matches_generated_configuration',
        evidence={str(path): digest}, formal_acceptance=False, board_actions=False,
        advisory_only=True, limitation='Generated configuration only, before STA. Resolve a target mismatch before repeating equivalent operating points; this is not implementation acceptance.')


def observe(soc, intent=None, reports_dir=None, generated_dir=None):
    soc = Path(soc).resolve(); seen = {}; issues = []; notes = []
    def load(path, binary=False):
        path = Path(path); raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(str(path) not in seen or seen[str(path)] == digest, 'Input changed during observation')
        seen[str(path)] = digest
        return raw if binary else raw.decode('utf-8', errors='strict')
    meta = json.loads(load(soc/'manifest.json'))
    intent = {} if intent is None else intent
    require(isinstance(intent, dict) and set(intent) <= {'clocks_ns', 'xsa_actual_fabric_mhz'}, 'Unknown clock intent fields')
    expected = {k: float(positive(v)) for k, v in intent.get('clocks_ns', {}).items()}
    expected_actual = float(positive(intent['xsa_actual_fabric_mhz'])) if 'xsa_actual_fabric_mhz' in intent else None
    request = parameters(load(soc/'bd.tcl')).get('PCW_FPGA0_PERIPHERAL_FREQMHZ')
    generated = []; xsa_actual = None
    directories = [soc] + ([Path(generated_dir).resolve()] if generated_dir is not None and Path(generated_dir).resolve() != soc else [])
    for directory in directories:
        for name in ('ps_config_report.txt', 'acp_elaborated_bd.tcl'):
            if (directory/name).is_file():
                generated.append(dict(source=str(directory/name), params=parameters(load(directory/name))))
    xsas = list((soc/'artifacts').glob('*.xsa'))
    require(len(xsas) <= 1, 'Ambiguous XSA')
    if xsas:
        with zipfile.ZipFile(io.BytesIO(load(xsas[0], True))) as z:
            hs = [n for n in z.namelist() if n.endswith('.hwh')]
            require(len(hs) == 1, 'Ambiguous/missing XSA HWH')
            root = ET.fromstring(z.read(hs[0]))
        modules = [m for m in root.findall('.//MODULE') if m.get('MODTYPE') == 'processing_system7']
        require(len(modules) == 1, 'Ambiguous/missing XSA PS7')
        pairs = [(p.get('NAME'), p.get('VALUE')) for p in modules[0].findall('./PARAMETERS/PARAMETER') if p.get('NAME') in PARAMS]
        require(len(dict(pairs)) == len(pairs), 'Duplicate XSA PS7 parameters')
        ps = dict(pairs); generated.append(dict(source=str(xsas[0]), params=ps))
        if 'PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ' in ps:
            xsa_actual = float(positive(ps['PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ']))
    for key in PARAMS:
        vals = {g['params'][key] for g in generated if key in g['params']}
        if key == 'PCW_FPGA0_PERIPHERAL_FREQMHZ' and request is not None:
            vals.add(request)
        if key != 'PCW_FCLK0_PERIPHERAL_CLKSRC':
            vals = {positive(v) for v in vals}
        if len(vals) > 1:
            issues.append('Conflicting generated parameter: '+key)
    actuals = {float(positive(g['params']['PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ'])) for g in generated
               if 'PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ' in g['params']}
    actual = next(iter(actuals)) if len(actuals) == 1 else None
    directory = Path(reports_dir).resolve() if reports_dir is not None else soc/'impl_reports'
    sta = {}; timing = None
    if (directory/'timing_summary.rpt').is_file():
        text = load(directory/'timing_summary.rpt')
        timing = summary(text); sta = {k: float(v) for k, v in clocks(text, True).items()}
        if (directory/'clocks.rpt').is_file():
            require(sta == {k: float(v) for k,v in clocks(load(directory/'clocks.rpt')).items()}, 'Clock reports disagree')
    else:
        issues.append('No retained timing summary; explicitly supply its exact report directory if available')
    mismatch = bool(expected and sta and expected != sta)
    mismatch |= bool(expected_actual is not None and actual is not None and expected_actual != actual)
    target_status = ('mismatch' if mismatch else 'not_declared' if not intent else
                     'incomplete' if (expected and not sta) or (expected_actual is not None and actual is None) else 'matches_observed')
    if actual and 'clk_fpga_0' in sta:
        delta = Decimal(str(sta['clk_fpga_0']))-1000/Decimal(str(actual))
        if not -Decimal('.001001') <= delta <= Decimal('.0005'):
            issues.append('STA/generated period disagreement beyond report precision')
    compiled = json.loads(load(soc/'hls-compiled-source.json'))
    ip = json.loads(load(soc/'hls-ip-manifest.json'))
    binding = (sha(soc/'hls-compiled-source.json') == ip.get('dependency_sha256')
               and sha(soc/'hls-ip-manifest.json') == meta.get('hls_manifest_sha256')
               and isinstance(compiled.get('source_commit'), str)
               and re.fullmatch('[0-9a-f]{40}', compiled['source_commit']) is not None
               and bool(compiled.get('build_token')) and bool(ip.get('ip_files'))
               and compiled.get('build_token') == ip.get('build_token') == meta.get('hls_build_token')
               and compiled.get('source_commit') == ip.get('source_commit') == meta.get('kernel_commit')
               and ip.get('ip_files') == meta.get('ip_files'))
    if not binding:
        issues.append('HLS generation chain differs/incomplete')
    for name, digest in meta.get('generated_tcl_sha256', {}).items():
        require(Path(name).name == name, 'Invalid generated Tcl path')
        raw = load(soc/name, True)
        if hashlib.sha256(raw).hexdigest() != digest:
            issues.append('Generated Tcl hash differs: '+name)
    for group, folder in [('reports_sha256', soc/'impl_reports'), ('artifacts_sha256', soc/'artifacts')]:
        for name, digest in meta.get(group, {}).items():
            p = (folder/name).resolve()
            require(p.is_relative_to(folder.resolve()), 'Invalid retained file path')
            if hashlib.sha256(load(p, True)).hexdigest() != digest:
                issues.append('Retained hash differs: '+str(p))
    strategies = re.findall(r'^\s*set_property\s+strategy\s+(\S+)\s+\[get_runs\s+impl_1\]', load(soc/'impl.tcl'), re.M)
    require(len(strategies) <= 1, 'Ambiguous implementation strategy')
    if mismatch: notes.append('Target operating point not realized; this is not timing evidence at the intended clock')
    if timing and timing['summary_status'] == 'violated_summary':
        notes.append('Timing violation belongs to the observed STA period only')
    if meta.get('status') == 'failed' and timing and timing['summary_status'] == 'nonnegative_summary':
        notes.append('Controller failed despite nonnegative STA summary; inspect configuration/binding/exit before attributing a timing failure')
    result = dict(schema='research-facts/1', status='observed_with_issues' if issues else 'observed',
        soc=str(soc), controller=dict(status=meta.get('status'), error=meta.get('error')),
        intent=intent, target_status=target_status, requested_fabric_mhz=float(positive(request)) if request else None,
        configured_fabric_mhz=actual, xsa_actual_fabric_mhz=xsa_actual, generated_configuration=generated,
        sta_clocks_ns=sta, sta_reciprocal_mhz={k: 1000/v for k,v in sta.items()}, timing=timing,
        hls_target_ns=float(positive(compiled['clock_ns'])), kernel_commit=compiled.get('source_commit'),
        compiled_source_sha256=compiled.get('sha256'), ip_hdl_sha256={k:v for k,v in ip.get('ip_files', {}).items() if k.startswith('hdl/')},
        hls_generation_bound=binding, implementation_strategy=strategies[0] if strategies else None,
        report_binding='manifest_hashed_files' if meta.get('reports_sha256') and directory == soc/'impl_reports' else 'explicit_unbound_observation',
        issues=issues, advisories=notes, evidence=seen, checker_sha256=sha(__file__),
        formal_acceptance=False, standard_best_changed=False, board_actions=False,
        limitation='Observed retained facts, not full STA/warning/source/board acceptance. Missing intent or configuration remains unknown. A printed STA reciprocal is never XSA actual MHz.')
    require(all(sha(p) == h for p,h in seen.items()), 'Input changed during observation')
    return result


def contrast(rows):
    """Flag mixed controls/repeated generated clocks, never certify causality."""
    require(isinstance(rows, list) and len(rows) >= 2, 'Need at least two observations')
    axes = ('compiled_source_sha256', 'hls_target_ns', 'ip_hdl_sha256', 'configured_fabric_mhz', 'sta_clocks_ns')
    changed = [k for k in axes if any(r.get(k) != rows[0].get(k) for r in rows[1:])]
    missing = [k for k in axes if any(not r.get(k) for r in rows)]
    return dict(schema='research-contrast/1', changed_axes=changed, missing_axes=missing,
        strategy_only_evidence=not changed and not missing and all(not r['issues'] for r in rows),
        same_observed_working_clock=all(r.get('configured_fabric_mhz') == rows[0].get('configured_fabric_mhz')
            and r.get('sta_clocks_ns') == rows[0].get('sta_clocks_ns') for r in rows) and bool(rows[0].get('configured_fabric_mhz')),
        advisory_only=True, limitation='Even matching axes require source/topology/constraints and tool review; this is not a causal certificate or a promotion gate.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--soc', type=Path)
    source.add_argument('--configuration', type=Path, help='Generated PS7 configuration report, before expensive implementation')
    parser.add_argument('--intent', type=Path, help='Optional exact clocks_ns and/or xsa_actual_fabric_mhz; never inferred from request')
    parser.add_argument('--reports-dir', type=Path, help='Explicit retained failed-build reports; no directory search')
    parser.add_argument('--generated-dir', type=Path, help='Explicit failed-build generated PS7 files; no directory search')
    parser.add_argument('--out', required=True, type=Path, help='Fresh external observation directory')
    a = parser.parse_args()
    protected = a.soc.resolve() if a.soc else a.configuration.resolve().parent
    protected_dirs = [protected] + [p.resolve() for p in (a.reports_dir, a.generated_dir) if p is not None]
    require(not any(a.out.resolve().is_relative_to(p) for p in protected_dirs) and not a.out.exists(), 'Use a fresh output outside original source')
    intent = read(a.intent) if a.intent else None
    result = (observe(a.soc, intent, a.reports_dir, a.generated_dir) if a.soc else configuration(a.configuration, intent))
    if a.intent: result['intent_sha256'] = sha(a.intent)
    save(a.out/'facts.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'controller', 'target_status', 'requested_fabric_mhz',
          'configured_fabric_mhz', 'xsa_actual_fabric_mhz', 'sta_clocks_ns', 'timing', 'issues') if k in result}, indent=2))
    # Exit 0 says observation finished, not that the candidate/clock/timing passed.


if __name__ == '__main__':
    main()
