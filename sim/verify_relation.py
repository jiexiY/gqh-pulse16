"""Independent stored-state verification; no serial or programming access."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import random
import re
import struct
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve()
ROOT = next(parent for parent in SCRIPT.parents
            if (parent/"host/22_robust_uart_test.py").is_file()
            and (parent/"rtl/signal_engine.v").is_file())
OUT = SCRIPT.parent
CANDIDATE = ROOT / "rtl/signal_engine.v"
REFERENCE = ROOT / "host/22_robust_uart_test.py"
TB = OUT / "tb_relation.sv"
REQUEST = struct.Struct(">HBHBH")
RESPONSE = struct.Struct(">HBBBBH")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_class():
    tree = ast.parse(REFERENCE.read_text(encoding="utf-8-sig"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                and n.name == "MovingAverageReference")
    namespace = dict(deque=deque, WINDOW_SIZE=16, ACTION_NONE=0,
                     ACTION_SELL=1, ACTION_BUY=2)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(REFERENCE), "exec"), namespace)
    return namespace["MovingAverageReference"]


def vectors():
    cases = []
    def add(name, a, b, offset=0):
        assert len(a) == len(b)
        cases.append((name, a, b, offset))
    add("equality_buy_sell", [100]*16+[101,100,99,98,101,100],
        [100]*16+[98,99,101,100,98,100])
    add("floor_equality_no_cross", [100]*16+[99,99,100,100],
        [100]*16+[100,99,99,101])
    add("max_sum_and_zero", [65535]*16+[0,65535,65534,32768,32767]*8,
        [0]*16+[65535,0,1,32767,32768]*8)
    add("alternating_unsigned_extremes", [0,65535]*80, [65535,0]*80)
    add("floor_threshold_15_16", [15]*15+[16]+[15,16,14,0,65535]*20,
        [0]*15+[1]+[0,1,2,65535,0]*20)
    add("max_packet_index", [100]*16+[101,98,100]*10,
        [100]*16+[98,101,100]*10, offset=65490)
    def distribute(total, count):
        """Construct bounded prices with an exact independently checkable sum."""
        assert 0 <= total <= count * 65535
        values = []
        for _ in range(count):
            value = min(65535, total)
            values.append(value)
            total -= value
        assert total == 0
        return values

    # Exercise every potential serial arithmetic carry/borrow boundary, including
    # 4/8/12/16-bit chunk boundaries and the upper bits of the 20-bit sum.
    for bit in range(1, 20):
        carry = [0] + distribute((1 << bit) - 1, 15)
        borrow = [1] + distribute((1 << bit) - 1, 15)
        assert sum(carry) == (1 << bit) - 1 and carry[0] == 0
        assert sum(borrow) == (1 << bit) and borrow[0] == 1
        add(f"carry_borrow_boundary_{bit}",
            carry + [1] + [0] * 16 + [65535] * 17,
            borrow + [0] + [65535] * 16 + [0] * 17)

    add("max_sum_full_window_replacement",
        [65535] * 16 + [0] * 16 + [65535] * 16 + [0] * 16,
        [0] * 16 + [65535] * 16 + [0] * 16 + [65535] * 16)

    # Last warm-up price equals its floored average. Sweep remainders around
    # floor division boundaries, not just random sums that rarely hit equality.
    for quotient in (0, 1, 15, 16, 17, 255, 256, 257, 4095, 4096,
                     4097, 32767, 32768, 65534, 65535):
        for remainder in (0, 1, 7, 14, 15):
            total = 16 * quotient + remainder
            if total > 16 * 65535 or total - quotient > 15 * 65535:
                continue
            initial = distribute(total - quotient, 15) + [quotient]
            assert sum(initial) // 16 == quotient and initial[-1] == quotient
            low, high = max(0, quotient - 1), min(65535, quotient + 1)
            add(f"floor_q{quotient}_r{remainder}",
                initial + [low, quotient, high, quotient] * 9,
                initial + [high, quotient, low, quotient] * 9)

    # Each is a new index-zero session, with no hardware reset between sessions.
    for length in [1,1,2,15,16,17,18,40]:
        add(f"restart_after_{length}", [length]*length, [65535-length]*length)
    for seed in range(32):
        rng = random.Random(0x51DE0000 + seed)
        a = [rng.randrange(65536) for _ in range(100)]
        b = [rng.randrange(65536) for _ in range(100)]
        add(f"independent_fullrange_{seed}", a, b)

    klass = reference_class()
    output, sessions, equality_commits = [], [], 0
    for n, (name, a, b, offset) in enumerate(cases):
        refs = {0x11:klass(), 0x22:klass()}
        windows = {0x11:[], 0x22:[]}
        start = len(output)
        for i, (pa,pb) in enumerate(zip(a,b)):
            index = i if i < 16 else i+offset
            assert 0 <= index <= 65535
            slots = [(0x11,pa),(0x22,pb)]
            if (i+n)%2:
                slots.reverse()
            actions, meta = {}, {}
            for item, price in slots:
                ref = refs[item]
                actions[item] = ref.process(price) or 0
                # Cross-check organizer running sum against independently stored values.
                windows[item] = (windows[item]+[price])[-16:]
                independent_sum = sum(windows[item])
                assert ref.running_sum == independent_sum
                average = independent_sum//16
                le, ge = int(price<=average), int(price>=average)
                equality_commits += int(le and ge)
                meta[item] = ((independent_sum<<8) | (le<<7) | (ge<<6)
                              | (actions[item]<<4) | ((i+1)&15))
            request = REQUEST.pack(index,*slots[0],*slots[1])
            expected = RESPONSE.pack(index,slots[0][0],actions[slots[0][0]],
                                     slots[1][0],actions[slots[1][0]],0)
            output.append(f"{request.hex()} {expected.hex()} {meta[0x11]:07x} {meta[0x22]:07x}\n")
        sessions.append(dict(name=name, start_packet=start, packets=len(a)))
    # Explicit expected transitions make the important boundary cases reviewable.
    first_actions = [RESPONSE.unpack(bytes.fromhex(output[i].split()[1]))
                     for i in (16,17,18)]
    by_item = [{r[1]:r[2],r[3]:r[4]} for r in first_actions]
    assert [r[0x11] for r in by_item] == [2,2,1]
    assert by_item[0][0x22] == 1
    floor_case_start = sessions[1]["start_packet"]
    r = RESPONSE.unpack(bytes.fromhex(output[floor_case_start+16].split()[1]))
    assert {r[1]:r[2],r[3]:r[4]}[0x11] == 0
    return output, sessions, equality_commits


def simulate(source, stem):
    compiler = ROOT/".tools/iverilog/app/bin/iverilog.exe"
    simulator = ROOT/".tools/iverilog/app/bin/vvp.exe"
    binary = OUT/f"{stem}.vvp"
    compile_result = subprocess.run([str(compiler),"-g2012","-Wall","-s","tb_relation",
                                    "-o",str(binary),str(source),str(TB)],
                                   cwd=OUT,capture_output=True,text=True,timeout=90)
    (OUT/f"{stem}-compile.log").write_text(compile_result.stdout+compile_result.stderr,encoding="utf-8")
    if compile_result.returncode:
        raise RuntimeError(f"Compilation failed for {stem}")
    result = subprocess.run([str(simulator),str(binary),"+VECTORS=relation-vectors.txt"],
                            cwd=OUT,capture_output=True,text=True,timeout=90)
    (OUT/f"{stem}.log").write_text(result.stdout+result.stderr,encoding="utf-8")
    return result


def main():
    global ROOT, OUT, CANDIDATE, REFERENCE, TB
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT,
                        help="Project containing host/, rtl/, and local Icarus tools")
    parser.add_argument("--engine", type=Path,
                        help="Engine to verify; relative to project root, default rtl/signal_engine.v")
    parser.add_argument("--out", type=Path,
                        help="Output directory inside build/; relative to project root")
    parser.add_argument("--testbench", type=Path, default=SCRIPT.with_name("tb_relation.sv"),
                        help="Testbench path; defaults beside this script")
    args = parser.parse_args()
    ROOT = args.project_root.resolve()
    def project_path(value):
        return (value if value.is_absolute() else ROOT/value).resolve()
    CANDIDATE = project_path(args.engine or Path("rtl/signal_engine.v"))
    OUT = project_path(args.out or Path("build/relation-verification"))
    if not OUT.is_relative_to(ROOT / "build"):
        raise RuntimeError("All supplemental outputs must stay inside the project build folder")
    REFERENCE = ROOT/"host/22_robust_uart_test.py"
    TB = project_path(args.testbench)
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    checked = [CANDIDATE, REFERENCE, TB, Path(__file__).resolve()]
    before = {str(p.relative_to(ROOT)):sha(p) for p in checked}
    data, sessions, equalities = vectors()
    vector_path = OUT/"relation-vectors.txt"
    vector_path.write_text("".join(data),encoding="ascii")
    result = simulate(CANDIDATE,"candidate")
    print(result.stdout, end="")
    if result.returncode or f"PASS relation: {len(data)} packets, {len(data)*2} metadata invariants" not in result.stdout:
        raise RuntimeError("Candidate failed supplemental relation verification")

    # Mutation traps establish that the tests detect the principal implementation errors.
    original = CANDIDATE.read_text(encoding="utf-8")
    # Mutate semantic wire definitions instead of matching one particular
    # subtractor implementation. Keep the arithmetic-independent monitor strict.
    def relation_assignment(source, name):
        pattern = rf"(\bwire\s+{name}\s*=\s*)([^;]+)(;)"
        matches = list(re.finditer(pattern, source))
        if len(matches) != 1:
            raise RuntimeError(f"Relation assignment not unique: {name}")
        return pattern, matches[0].group(2).strip()

    le_pattern, le_expression = relation_assignment(original, "current_le")
    ge_pattern, ge_expression = relation_assignment(original, "current_ge")

    def substitute_relations(source, le=None, ge=None):
        for pattern, expression in ((le_pattern, le), (ge_pattern, ge)):
            if expression is not None:
                source, changed = re.subn(
                    pattern, lambda match: match.group(1) + expression + match.group(3),
                    source)
                if changed != 1:
                    raise RuntimeError("Relation mutation changed an unexpected assignment count")
        return source

    mutations = {
        "strict_previous_le": substitute_relations(original, le="!current_ge"),
        "no_warmup_relations": substitute_relations(
            original,
            le=f"(warmup ? 1'b0 : ({le_expression}))",
            ge=f"(warmup ? 1'b0 : ({ge_expression}))"),
        "stored_old_relations": substitute_relations(
            original, le="previous_le", ge="previous_ge"),
        "swapped_current_relations": substitute_relations(
            original, le=ge_expression, ge=le_expression),
    }
    traps = []
    for name, mutated_source in mutations.items():
        source = OUT/f"mutation-{name}.v"
        source.write_text(mutated_source, encoding="utf-8")
        mutated = simulate(source,f"mutation-{name}")
        rejected = mutated.returncode != 0 and ("invariant failed" in mutated.stdout
                    or "Loaded relation failed" in mutated.stdout or "Response failed" in mutated.stdout)
        if not rejected:
            raise RuntimeError(f"Mutation unexpectedly passed or failed for unrelated reason: {name}")
        traps.append(dict(name=name, rejected=True, source_sha256=sha(source),
                          evidence=mutated.stdout.strip()))
        print(f"PASS mutation rejected: {name}")
    after = {str(p.relative_to(ROOT)):sha(p) for p in checked}
    if before != after:
        raise RuntimeError("Verification inputs changed during run")
    evidence = dict(status="supplemental_relation_simulation_passed",
                    tested_at_utc=datetime.now(timezone.utc).isoformat(),
                    physical_board_tested=False, gowin_build_performed=False,
                    candidate_engine=str(CANDIDATE.relative_to(ROOT)),
                    packets=len(data), metadata_invariant_checks=2*len(data),
                    sessions_without_external_reset=len(sessions),
                    equality_metadata_cases=equalities,
                    reference="Unmodified organizer MovingAverageReference class extracted with AST; serial code not executed",
                    invariant="After every commit, LE=(last price<=floor(stored sum/16)); GE=(last price>=floor(stored sum/16)), including warm-up",
                    input_sha256=before, vectors_sha256=sha(vector_path),
                    simulator_sha256=sha(ROOT/".tools/iverilog/app/bin/vvp.exe"),
                    compiler_sha256=sha(ROOT/".tools/iverilog/app/bin/iverilog.exe"),
                    test_output=result.stdout.strip(), mutation_traps=traps,
                    sessions=sessions, runtime_seconds=round(time.monotonic()-started,3))
    (OUT/"relation-verification.json").write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
    print(f"PASS {len(data)} packets / {2*len(data)} metadata checks / {len(traps)} mutation traps")


if __name__ == "__main__":
    main()
