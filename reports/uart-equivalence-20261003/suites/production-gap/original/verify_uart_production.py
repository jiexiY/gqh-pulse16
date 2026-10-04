"""Snapshot and compare UART pin timing; generated outputs stay in this folder."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import re
import struct
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve()
OWNED = SCRIPT.parent
ROOT = next(p for p in SCRIPT.parents if (p/'host/22_robust_uart_test.py').is_file())
OUT = OWNED/'runs/uart-267-production64'
CANDIDATE = ROOT/'build/experiments/uart-small-20261003/variants/receive-shift-fields'
TB = OWNED/'tb_uart_equivalence.sv'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, log, timeout=1200):
    result = subprocess.run([str(v) for v in argv], cwd=OUT, capture_output=True,
                            text=True, timeout=timeout)
    (OUT/log).write_text(result.stdout+result.stderr, encoding='utf-8')
    print(result.stdout, end='', flush=True)
    if result.returncode:
        raise RuntimeError(f'Command failed; see {OUT/log}')
    return result.stdout


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checked = [ROOT/'rtl/trade_top.v', ROOT/'rtl/uart_rx.v', ROOT/'rtl/signal_engine.v',
               CANDIDATE/'trade_top.v', CANDIDATE/'uart_rx.v', TB, SCRIPT,
               ROOT/'sim/run_tests.py', ROOT/'host/22_robust_uart_test.py']
    hashes = {str(p.relative_to(ROOT)):sha(p) for p in checked}
    (OUT/'initial-input-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
    sources=[]
    for label,folder in [('baseline',ROOT/'rtl'),('candidate',CANDIDATE)]:
        for name in ['trade_top','uart_rx']:
            original = (folder/f'{name}.v').read_text(encoding='utf-8')
            renamed = re.sub(r'\btrade_top\b',f'{label}_trade_top',original)
            renamed = re.sub(r'\buart_rx\b',f'{label}_uart_rx',renamed)
            target=OUT/f'{label}_{name}.v'
            target.write_text(renamed, encoding='utf-8')
            sources.append(target)

    spec=importlib.util.spec_from_file_location('canonical_sim_oracle',ROOT/'sim/run_tests.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    oracle=module.Oracle()
    refs={item:module.official_reference()() for item in (0x11,0x22)}
    request_struct=struct.Struct('>HBHBH')
    response_struct=struct.Struct('>HBBBBH')
    byte_patterns=[0,1,2,15,16,31,32,63,64,85,127,128,
                   170,191,192,224,239,240,253,254,255,51,204,240]
    indices=list(range(16))
    for n in range(48):
        index=(byte_patterns[n%24]<<8)|byte_patterns[(n+11)%24]
        indices.append(index if index>=16 else index+16)
    assert len(indices)==64 and all(index>=16 for index in indices[16:])
    prices=[0,65535,32767,32768,15,16,255,256,4095,4096,100,100]
    vectors=[]
    actions=set()
    for n,index in enumerate(indices):
        slots=[(0x11,prices[n%len(prices)]),(0x22,prices[(n+5)%len(prices)])]
        if n%2: slots.reverse()
        expected=oracle.packet(index,slots)
        ref_actions=tuple(refs[item].process(price) or 0 for item,price in slots)
        result=response_struct.unpack(expected)
        assert (result[2],result[4]) == ref_actions
        actions.update(ref_actions)
        vectors.append(f'{request_struct.pack(index,*slots[0],*slots[1]).hex()} {expected.hex()}\n')
    assert actions == {0,1,2}
    high_bytes={response_struct.unpack(bytes.fromhex(v.split()[1]))[0]>>8 for v in vectors}
    low_bytes={response_struct.unpack(bytes.fromhex(v.split()[1]))[0]&255 for v in vectors}
    assert {0,1,15,16,127,128,255}.issubset(high_bytes)
    assert {0,1,15,16,127,128,255}.issubset(low_bytes)
    vector_path=OUT/'vectors.txt'
    vector_path.write_text(''.join(vectors),encoding='ascii')
    compiler=ROOT/'.tools/iverilog/app/bin/iverilog.exe'
    simulator=ROOT/'.tools/iverilog/app/bin/vvp.exe'
    started=time.monotonic()
    results=[]
    for gap in (13500,):
        binary=OUT/f'equivalence-gap{gap}.vvp'
        command([compiler,'-g2012','-Wall','-s','tb_uart_equivalence',
                 f'-Ptb_uart_equivalence.GAP_CYCLES={gap}','-o',binary,
                 *sources,ROOT/'rtl/signal_engine.v',TB],f'compile-gap{gap}.log')
        output=command([simulator,binary,'+VECTORS=vectors.txt'],f'run-gap{gap}.log')
        if f'PASS UART equivalence: {len(vectors)} packets' not in output:
            raise RuntimeError('Missing successful waveform-equivalence verdict')
        results.append({'gap_cycles':gap,'output':output.strip()})
    after={str(p.relative_to(ROOT)):sha(p) for p in checked}
    if hashes != after:
        raise RuntimeError('Verification input changed while checking the candidate')
    report={'status':'uart_waveform_equivalence_passed', 'packets_per_gap':len(vectors),
            'compared_gaps':[13500], 'input_sha256':hashes,
            'vectors_sha256':sha(vector_path),'results':results,
            'physical_board_tested':False,
            'tested_at_utc':datetime.now(timezone.utc).isoformat(),
            'runtime_seconds':round(time.monotonic()-started,3)}
    (OUT/'uart-equivalence.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'PASS {len(vectors)} packet waveform-equivalence checks',flush=True)


if __name__=='__main__':
    main()
