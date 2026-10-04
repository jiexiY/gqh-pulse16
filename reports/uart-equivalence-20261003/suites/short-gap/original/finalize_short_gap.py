"""Finalize the already-passed short-gap phase without rerunning its simulation."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

OWNED=Path(__file__).resolve().parent
ROOT=next(p for p in OWNED.parents if (p/'host/22_robust_uart_test.py').is_file())
OUT=OWNED/'runs/uart-267-equivalence'
CANDIDATE=ROOT/'build/experiments/uart-small-20261003/variants/receive-shift-fields'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    log=(OUT/'run-gap16.log').read_text(encoding='utf-8')
    verdict='PASS UART equivalence: 528 packets, 19970534 clocks, 28 active-TX errors, gap 16 clocks'
    assert verdict in log and 'FATAL' not in log and 'ERROR' not in log
    checked=[ROOT/'rtl/trade_top.v',ROOT/'rtl/uart_rx.v',ROOT/'rtl/signal_engine.v',
             CANDIDATE/'trade_top.v',CANDIDATE/'uart_rx.v',OWNED/'tb_uart_equivalence.sv',
             OWNED/'verify_uart_equivalence.py',ROOT/'sim/run_tests.py',
             ROOT/'host/22_robust_uart_test.py']
    assert sha(ROOT/'rtl/signal_engine.v') == 'd9b322cdb19c86ed4ec183cbf42e6ebf51c5d3e3ad6385a9af911f1d310c8c91'
    for label,folder in [('baseline',ROOT/'rtl'),('candidate',CANDIDATE)]:
        for name in ('trade_top','uart_rx'):
            expected=(folder/f'{name}.v').read_text(encoding='utf-8')
            expected=re.sub(r'\btrade_top\b',f'{label}_trade_top',expected)
            expected=re.sub(r'\buart_rx\b',f'{label}_uart_rx',expected)
            assert (OUT/f'{label}_{name}.v').read_text(encoding='utf-8') == expected
    vectors=(OUT/'vectors.txt').read_text(encoding='ascii').splitlines()
    assert len(vectors)==528
    report={
        'status':'uart_waveform_equivalence_passed',
        'packets_per_gap':528,'compared_gaps':[16],
        'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in checked},
        'vectors_sha256':sha(OUT/'vectors.txt'),
        'results':[{'gap_cycles':16,'output':log.strip()}],
        'physical_board_tested':False,
        'finalized_at_utc':datetime.now(timezone.utc).isoformat(),
        'input_validation':'The preserved namespaced DUT snapshots exactly match current original sources under the documented module-name substitutions; shared engine matches frozen274 hash.',
        'scope_note':'Only completed gap16 phase is counted. Full528 production-gap phase was stopped incomplete. Separate production64 suite has its own vectors and report.',
        'incomplete_phase_record':'production-incomplete.json',
        'finalizer_sha256':sha(Path(__file__).resolve())
    }
    (OUT/'uart-equivalence.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(verdict)
    print('Short-gap result finalized; interrupted production phase is not counted.')


if __name__=='__main__':
    main()
