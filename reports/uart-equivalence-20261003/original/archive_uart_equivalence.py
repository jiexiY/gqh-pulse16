"""Archive a passed, hash-checked UART comparison AFTER canonical267 promotion.

Run --check-only for read-only validation. By default creates a new immutable
supplemental report folder; never overwrites existing reports or programs a board.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

SCRIPT = Path(__file__).resolve()
OWNED = SCRIPT.parent
ROOT = SCRIPT.parents[3]
VERIFY = ROOT/'build/experiments/competition-verification-20261003'
CHECKPOINT = ROOT/'build/checkpoints/verified-274-before-competition'
CANDIDATE = OWNED/'variants/receive-shift-fields'
DESTINATION = ROOT/'reports/uart-equivalence-20261003'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def checked(path, expected):
    if not path.is_file() or sha(path) != expected:
        raise ValueError(f'Missing or changed source: {path}')
    return path


def relative(path):
    return path.relative_to(ROOT).as_posix()


def prepare_suite(suite_name, run, runner, gap, packet_count):
    prefix = f'suites/{suite_name}/'
    report_path = run/'uart-equivalence.json'
    report = read_json(report_path)
    if report.get('status') != 'uart_waveform_equivalence_passed':
        raise ValueError('Original waveform comparison has not passed')
    if report.get('physical_board_tested') is not False:
        raise ValueError('Supplemental waveform report must remain simulation-only')
    if report.get('compared_gaps') != [gap] or report.get('packets_per_gap') != packet_count:
        raise ValueError(f'Expected exact {suite_name} scope')
    baseline_manifest = read_json(CHECKPOINT/'reports/build-summary.json')
    canonical_manifest = read_json(ROOT/'reports/build-summary.json')
    if baseline_manifest['metrics']['synthesis_total_logic'] != 274:
        raise ValueError('Expected verified274 baseline checkpoint')
    if canonical_manifest['metrics']['synthesis_total_logic'] != 267:
        raise ValueError('Canonical267 must be promoted before archiving')
    inputs = report['input_sha256']
    normalized_inputs = {name.replace('\\', '/'): expected for name, expected in inputs.items()}
    expected_keys = {
        'rtl/trade_top.v', 'rtl/uart_rx.v', 'rtl/signal_engine.v',
        relative(CANDIDATE/'trade_top.v'), relative(CANDIDATE/'uart_rx.v'),
        relative(VERIFY/'tb_uart_equivalence.sv'), relative(runner),
        'sim/run_tests.py', 'host/22_robust_uart_test.py'}
    if set(normalized_inputs) != expected_keys or len(normalized_inputs) != len(inputs):
        raise ValueError('Unexpected original input set; inspect report schema before archiving')
    copies = {}
    mappings = {}
    for original_key, expected in inputs.items():
        original = original_key.replace('\\', '/')
        if original in ('rtl/trade_top.v', 'rtl/uart_rx.v'):
            source = CHECKPOINT/original
            archive = 'original/baseline/'+Path(original).name
            if baseline_manifest['source_sha256'][original] != expected:
                raise ValueError(f'Baseline manifest hash differs: {original}')
        elif original == 'rtl/signal_engine.v':
            source = ROOT/original
            archive = 'rtl/signal_engine.v'
            checked(CHECKPOINT/original, expected)
            if (baseline_manifest['source_sha256'][original] != expected or
                    canonical_manifest['source_sha256'][original] != expected):
                raise ValueError('Engine changed across baseline and candidate')
        elif original.startswith(relative(CANDIDATE)+'/'):
            source = ROOT/original
            archive = 'original/candidate/'+Path(original).name
            canonical_key = 'rtl/'+Path(original).name
            checked(ROOT/canonical_key, expected)
            if canonical_manifest['source_sha256'][canonical_key] != expected:
                raise ValueError(f'Canonical267 manifest mismatch: {canonical_key}')
        elif original == relative(VERIFY/'tb_uart_equivalence.sv'):
            source = ROOT/original
            archive = 'testbench/tb_uart_equivalence.sv'
        elif original == relative(runner):
            source = ROOT/original
            archive = 'original/'+runner.name
        else:
            source = ROOT/original
            archive = 'original/'+original
        copies[prefix+archive] = checked(source, expected)
        mappings[original_key] = {'archive_path': prefix+archive, 'expected_sha256': expected,
                              'resolved_source_at_archive': relative(source)}
    renamed = []
    for namespace in ('baseline', 'candidate'):
        for name in ('trade_top', 'uart_rx'):
            original_archive = prefix+f'original/{namespace}/{name}.v'
            text = copies[original_archive].read_text(encoding='utf-8')
            for module in ('trade_top', 'uart_rx'):
                text = re.sub(r'\b'+module+r'\b', namespace+'_'+module, text)
            source = run/f'{namespace}_{name}.v'
            if source.read_text(encoding='utf-8') != text:
                raise ValueError(f'Renamed snapshot differs from original input: {source}')
            archive = prefix+'rtl/'+source.name
            copies[archive] = source
            renamed.append({'archive_path': archive, 'namespace': namespace,
                            'original_archive_path': original_archive,
                            'transformation': 'Whole-word trade_top and uart_rx namespace substitution; normalized text equality verified'})
    copies[prefix+'vectors.txt'] = checked(run/'vectors.txt', report['vectors_sha256'])
    verified_runs = []
    results = {entry['gap_cycles']: entry for entry in report['results']}
    if set(results) != {gap}:
        raise ValueError('Unexpected comparison result set')
    for gap in (gap,):
        compile_path, run_path = run/f'compile-gap{gap}.log', run/f'run-gap{gap}.log'
        run_text = run_path.read_text(encoding='utf-8')
        if results[gap]['output'].strip() != run_text.strip():
            raise ValueError(f'Report and raw run log differ: gap {gap}')
        match = re.search(r'PASS UART equivalence: (\d+) packets, (\d+) clocks, '
                          r'(\d+) active-TX errors, gap (\d+) clocks', run_text)
        if not match:
            raise ValueError(f'No complete success line in raw log: gap {gap}')
        packets, clocks, errors, actual_gap = map(int, match.groups())
        if actual_gap != gap or packets <= 0 or clocks <= 0 or errors <= 0:
            raise ValueError('Invalid waveform comparison counts')
        if isinstance(report.get('packets_per_gap'), int) and packets != report['packets_per_gap']:
            raise ValueError('Packet count differs from original report')
        verified_runs.append({'gap_cycles': gap, 'packets': packets,
                              'compared_clocks': clocks, 'active_tx_errors': errors})
        copies[prefix+'logs/'+compile_path.name] = compile_path
        copies[prefix+'logs/'+run_path.name] = run_path
    copies[prefix+'uart-equivalence.json'] = report_path
    if 'finalizer_sha256' in report:
        copies[prefix+'original/finalize_short_gap.py'] = checked(VERIFY/'finalize_short_gap.py', report['finalizer_sha256'])
        copies[prefix+'production-incomplete.json'] = run/'production-incomplete.json'
        incomplete = read_json(run/'production-incomplete.json')
        if incomplete['incomplete_phase']['counted_as_pass'] is not False:
            raise ValueError('Interrupted phase must not count as a pass')
    if (run/'initial-input-hashes.json').is_file():
        if read_json(run/'initial-input-hashes.json') != inputs:
            raise ValueError('Initial hashes differ from completed report')
        copies[prefix+'initial-input-hashes.json'] = run/'initial-input-hashes.json'
    for source in copies.values():
        if not source.is_file():
            raise ValueError(f'Missing archive source: {source}')
    provenance = {
        'original_report_sha256': sha(report_path),
        'original_report_source': relative(report_path),
        'original_report_archive_path': prefix+'uart-equivalence.json',
        'vectors_archive_path': prefix+'vectors.txt',
        'testbench_archive_path': prefix+'testbench/tb_uart_equivalence.sv',
        'rtl_archive_paths': [prefix+'rtl/'+name for name in ('baseline_trade_top.v', 'baseline_uart_rx.v', 'candidate_trade_top.v', 'candidate_uart_rx.v', 'signal_engine.v')],
        'original_input_mapping': mappings, 'renamed_source_mapping': renamed,
        'verified_runs': verified_runs,
    }
    return copies, provenance


def prepare():
    copies, suites = {}, {}
    for name, folder, runner, gap, packets in (
        ('short-gap', 'uart-267-equivalence', 'verify_uart_equivalence.py', 16, 528),
        ('production-gap', 'uart-267-production64', 'verify_uart_production.py', 13500, 64)):
        suite_copies, suite_provenance = prepare_suite(name, VERIFY/'runs'/folder, VERIFY/runner, gap, packets)
        copies.update(suite_copies)
        suites[name] = suite_provenance
    copies['original/baseline-build-summary.json'] = CHECKPOINT/'reports/build-summary.json'
    copies['original/candidate-build-summary.json'] = ROOT/'reports/build-summary.json'
    copies['replay.py'] = OWNED/'replay_uart_equivalence_archive.py'
    copies['original/archive_uart_equivalence.py'] = SCRIPT
    provenance = {'status': 'verified_supplemental_archive', 'physical_board_tested': False,
        'suites': suites, 'baseline_checkpoint': relative(CHECKPOINT),
        'canonical_logic_at_archive': 267,
        'replay': '.venv/Scripts/python.exe reports/uart-equivalence-20261003/replay.py',
        'verification_scope': 'Functional RTL and exact UART output waveform comparison, not formal proof, mapped timing, physical USB testing or official qualification'}
    return copies, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    copies, provenance = prepare()
    source_hashes = {name: sha(source) for name, source in copies.items()}
    if args.check_only:
        print(f'PASS archive preflight: {len(copies)} exact files, no writes performed')
        return
    if DESTINATION.exists():
        raise ValueError(f'Refusing to overwrite existing evidence: {DESTINATION}')
    # Inherit the workspace ACL on Windows. Python's mode-0700 mkdtemp creates
    # an owner-only directory that a restricted child token may not re-enter.
    stage = ROOT/'build'/('uart-equivalence-stage-' + uuid.uuid4().hex)
    stage.mkdir(exist_ok=False)
    for name, source in copies.items():
        destination = stage/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha(destination) != source_hashes[name] or sha(source) != source_hashes[name]:
            raise ValueError(f'Input changed while archiving; incomplete stage retained: {stage}')
    readme = '''# Supplemental UART waveform equivalence evidence

Each original report is preserved byte-for-byte under its own `suites/` folder.
The short-gap suite checks 528 packets; the production-gap suite checks 64.
The interrupted 528-packet production phase is preserved as incomplete and
is not counted as a pass.
`provenance.json` maps every reported original input to its archived exact copy.
Namespace-renamed RTL is checked against the archived originals. No simulator
binaries are archived. These results are simulation evidence, not physical-board
qualification or formal exhaustive equivalence.

From the repository root:

```powershell
.venv\\Scripts\\python.exe reports/uart-equivalence-20261003/replay.py --verify-only
.venv\\Scripts\\python.exe reports/uart-equivalence-20261003/replay.py
```

Replay uses only this archive and installed Icarus Verilog tools. It does not
need the original experiments/checkpoint folders or current production HDL.
If needed pass `--iverilog PATH` and `--vvp PATH`. Generated binaries, raw logs,
and the new replay report go into a new `build/uart-equivalence-replay/` folder;
the archived evidence is not overwritten.
'''
    (stage/'README.md').write_text(readme, encoding='utf-8')
    provenance['archived_at_utc'] = datetime.now(timezone.utc).isoformat()
    provenance['archive_sha256'] = {
        path.relative_to(stage).as_posix(): sha(path)
        for path in sorted(stage.rglob('*')) if path.is_file()}
    (stage/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n', encoding='utf-8')
    # Revalidate originals before publishing the completed directory.
    _, current = prepare()
    if current['suites'] != provenance['suites']:
        raise ValueError(f'Original report changed; stage retained: {stage}')
    stage.rename(DESTINATION)
    print(f'PASS archived {len(provenance["archive_sha256"])} files: {DESTINATION}')


if __name__ == '__main__':
    main()
