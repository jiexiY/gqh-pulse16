"""Replay an archived UART comparison without its original experiments tree.

This file is copied to reports/uart-equivalence-20261003/replay.py by the
archival helper. Inputs are immutable; generated binaries/logs go under build/.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_file(archive, relative):
    path = (archive / relative).resolve()
    if not path.is_relative_to(archive) or not path.is_file():
        raise ValueError(f'Invalid archived input: {relative}')
    return path


def verify(archive):
    provenance = json.loads((archive/'provenance.json').read_text(encoding='utf-8'))
    if provenance['status'] != 'verified_supplemental_archive':
        raise ValueError('Archive provenance is not verified')
    for relative, expected in provenance['archive_sha256'].items():
        if sha(archive_file(archive, relative)) != expected:
            raise ValueError(f'Archive hash mismatch: {relative}')
    if set(provenance['suites']) != {'short-gap', 'production-gap'}:
        raise ValueError('Both archived suites are required')
    for suite in provenance['suites'].values():
        report_path = archive_file(archive, suite['original_report_archive_path'])
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if sha(report_path) != suite['original_report_sha256']:
            raise ValueError('Original report hash differs')
        if report['status'] != 'uart_waveform_equivalence_passed':
            raise ValueError('Original report is not a pass')
        if sha(archive_file(archive, suite['vectors_archive_path'])) != report['vectors_sha256']:
            raise ValueError('Original report vector hash mismatch')
        mappings = suite['original_input_mapping']
        if set(mappings) != set(report['input_sha256']):
            raise ValueError('Not every original input is archived')
        for original, entry in mappings.items():
            expected = report['input_sha256'][original]
            if entry['expected_sha256'] != expected:
                raise ValueError(f'Input provenance differs from original report: {original}')
            if sha(archive_file(archive, entry['archive_path'])) != expected:
                raise ValueError(f'Original input copy differs: {original}')
        for entry in suite['renamed_source_mapping']:
            original = archive_file(archive, entry['original_archive_path'])
            expected = original.read_text(encoding='utf-8')
            for name in ('trade_top', 'uart_rx'):
                expected = re.sub(r'\b'+name+r'\b', entry['namespace']+'_'+name, expected)
            if archive_file(archive, entry['archive_path']).read_text(encoding='utf-8') != expected:
                raise ValueError(f'Unexpected namespace transformation: {entry["archive_path"]}')
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--iverilog', type=Path)
    parser.add_argument('--vvp', type=Path)
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    archive = Path(__file__).resolve().parent
    root = archive.parents[1]
    provenance = verify(archive)
    if args.verify_only:
        print('PASS archived input hashes and namespace transformations')
        return
    compiler = args.iverilog or root/'.tools/iverilog/app/bin/iverilog.exe'
    simulator = args.vvp or root/'.tools/iverilog/app/bin/vvp.exe'
    if not compiler.is_file() or not simulator.is_file():
        raise ValueError('Install Icarus Verilog or pass --iverilog and --vvp')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = root/'build/uart-equivalence-replay'/stamp
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for suite_name, suite in provenance['suites'].items():
        suite_output = output/suite_name
        suite_output.mkdir()
        shutil.copyfile(archive_file(archive, suite['vectors_archive_path']), suite_output/'vectors.txt')
        sources = [archive_file(archive, name) for name in suite['rtl_archive_paths']]
        if len(suite['verified_runs']) != 1:
            raise ValueError('Expected one completed gap per suite')
        expected = suite['verified_runs'][0]
        gap = expected['gap_cycles']
        binary = suite_output/f'equivalence-gap{gap}.vvp'
        commands = [
            ('compile', [str(compiler), '-g2012', '-Wall', '-s', 'tb_uart_equivalence',
                         f'-Ptb_uart_equivalence.GAP_CYCLES={gap}', '-o', str(binary),
                         *map(str, sources), str(archive_file(archive, suite['testbench_archive_path']))]),
            ('run', [str(simulator), str(binary), '+VECTORS=vectors.txt'])]
        for kind, argv in commands:
            result = subprocess.run(argv, cwd=suite_output, capture_output=True, text=True,
                                    timeout=args.timeout)
            text = result.stdout+result.stderr
            (suite_output/f'{kind}-gap{gap}.log').write_text(text, encoding='utf-8')
            print(text, end='', flush=True)
            if result.returncode:
                raise RuntimeError(f'{kind} failed; see {output}')
        match = re.search(r'PASS UART equivalence: (\d+) packets, (\d+) clocks, '
                          r'(\d+) active-TX errors, gap (\d+) clocks', text)
        if not match or tuple(map(int, match.groups())) != (
                expected['packets'], expected['compared_clocks'],
                expected['active_tx_errors'], gap):
            raise RuntimeError(f'Replay differs from original verified counts: gap {gap}')
        results.append({'suite': suite_name, 'gap_cycles': gap, 'output': text.strip()})
    verify(archive)
    result = {'status': 'uart_waveform_equivalence_replay_passed',
              'physical_board_tested': False,
              'original_report_sha256': {name:suite['original_report_sha256'] for name,suite in provenance['suites'].items()},
              'results': results, 'finished_at_utc': datetime.now(timezone.utc).isoformat()}
    (output/'replay-report.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(f'PASS independent replay. Evidence: {output}')


if __name__ == '__main__':
    main()
