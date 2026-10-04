"""Exhaustive startup timeline/reset-state proof plus actual RTL comparison.

The startup machine is independent of the button synchronizer. Enumerating its
entire path, and all four two-bit synchronizer states at every clock, establishes
the unchanged reset OR behavior for arbitrary synchronized button histories.
An actual dual-RTL run separately checks both machines and button synchronization.
This is not physical power-cycle evidence or a proof of analog clock stability.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[2]
BASELINE = PROJECT/"build/experiments/meta-gap0-final-20261004"
OUT = ROOT/"build/startup-proof"
OUT.mkdir(parents=True, exist_ok=False)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

checked = [Path(__file__).resolve(), ROOT/"rtl/trade_top.v", BASELINE/"rtl/trade_top.v"]
before = {str(path):sha(path) for path in checked}
candidate_text = checked[1].read_text(encoding="utf-8")
baseline_text = checked[2].read_text(encoding="utf-8")
for text in (candidate_text, baseline_text):
    if "reg [1:0] reset_sync = 0;" not in text or "reset_sync <= {reset_sync[0], reset_btn};" not in text:
        raise ValueError("Button synchronizer was modified; compositional proof no longer applies")
if "wire rst = !startup_done || reset_sync[1];" not in candidate_text:
    raise ValueError("Candidate reset combination differs from the checked equation")
if "wire rst = !(&power_on) || reset_sync[1];" not in baseline_text:
    raise ValueError("Baseline reset combination differs from the checked equation")

state = 0
preterminal = []
comparisons = 0
for cycle in range(1024):
    counter = min(cycle, 255)
    assert (state == 128) == (counter == 255), (cycle, state, counter)
    for sync in range(4):
        assert ((state != 128) or bool(sync & 2)) == ((counter != 255) or bool(sync & 2))
        comparisons += 1
        for button in range(2):
            # Same unchanged two-flop equation is closed over all states/inputs.
            new_sync = ((sync << 1) | button) & 3
            assert 0 <= new_sync <= 3
    if state != 128:
        assert state not in preterminal
        preterminal.append(state)
        feedback = ((state >> 7) ^ (state >> 5) ^ (state >> 4) ^ (state >> 3) ^ (state == 0)) & 1
        state = ((state << 1) | feedback) & 255
assert len(preterminal) == 255 and state == 128

for name, text in (("baseline", baseline_text), ("candidate", candidate_text)):
    renamed, replacements = re.subn(r"\btrade_top\b", name+"_trade_top", text)
    if replacements != 1:
        raise ValueError("Unexpected module namespace replacement count")
    (OUT/(name+"_trade_top.v")).write_text(renamed, encoding="utf-8")
bench = r'''`timescale 1ns/1ps
module tb_startup;
    reg sys_clk=0, reset_btn=0, uart_rx_i=1;
    wire btx, bled0, bled1, ctx, cled0, cled1;
    reg [7:0] counter_model=0, lfsr_model=0;
    reg [1:0] sync_model=0;
    integer cycle;
    baseline_trade_top baseline(.sys_clk(sys_clk),.reset_btn(reset_btn),.uart_rx_i(uart_rx_i),
        .uart_tx_o(btx),.led0_n(bled0),.led1_n(bled1));
    candidate_trade_top candidate(.sys_clk(sys_clk),.reset_btn(reset_btn),.uart_rx_i(uart_rx_i),
        .uart_tx_o(ctx),.led0_n(cled0),.led1_n(cled1));
    always #18.519 sys_clk=~sys_clk;
    initial begin
        #1;
        if (baseline.rst !== 1 || candidate.rst !== 1) $fatal(1,"Initial reset not asserted");
        for(cycle=1;cycle<=1024;cycle=cycle+1) begin
            @(posedge sys_clk);
            if(counter_model != 255) counter_model=counter_model+1'b1;
            if(lfsr_model != 128)
                lfsr_model={lfsr_model[6:0],lfsr_model[7]^lfsr_model[5]^lfsr_model[4]^lfsr_model[3]^(lfsr_model==0)};
            sync_model={sync_model[0],reset_btn};
            #1;
            if(baseline.power_on !== counter_model || candidate.power_on !== lfsr_model)
                $fatal(1,"Actual startup state differs from exhaustive model at clock%0d",cycle);
            if(baseline.reset_sync !== sync_model || candidate.reset_sync !== sync_model)
                $fatal(1,"Button synchronization differs at clock%0d",cycle);
            if(baseline.rst !== candidate.rst || candidate.rst !== ((counter_model!=255)||sync_model[1]))
                $fatal(1,"Reset timeline differs at clock%0d",cycle);
            if(btx !== ctx || bled0 !== cled0 || bled1 !== cled1)
                $fatal(1,"Idle outputs differ across reset at clock%0d",cycle);
            @(negedge sys_clk);
            reset_btn=((cycle>=247 && cycle<263) || ((cycle%17)<5));
        end
        $display("PASS startup RTL: 1024 clocks, exact255-clock completion, overlapping and repeated button resets");
        $finish;
    end
endmodule
'''
(OUT/"tb_startup.sv").write_text(bench, encoding="utf-8")
compiler=PROJECT/".tools/iverilog/app/bin/iverilog.exe"
simulator=PROJECT/".tools/iverilog/app/bin/vvp.exe"
sources=[ROOT/"rtl/uart_rx.v",ROOT/"rtl/uart_tx.v",ROOT/"rtl/signal_engine.v",
         OUT/"baseline_trade_top.v",OUT/"candidate_trade_top.v",OUT/"tb_startup.sv"]
binary=OUT/"startup.vvp"
for name, argv in (("compile",[str(compiler),"-g2012","-s","tb_startup","-o",str(binary),*map(str,sources)]),
                   ("run",[str(simulator),str(binary)])):
    result=subprocess.run(argv,cwd=OUT,capture_output=True,text=True,timeout=90)
    text=result.stdout+result.stderr
    (OUT/(name+".log")).write_text(text,encoding="utf-8")
    print(text,end="",flush=True)
    if result.returncode:
        raise ValueError(name+" failed")
if "PASS startup RTL: 1024 clocks" not in text:
    raise ValueError("Startup RTL pass marker missing")
if before != {str(path):sha(path) for path in checked}:
    raise ValueError("Startup proof inputs changed")
report=dict(status="startup_timeline_equivalence_passed",physical_power_cycle_tested=False,
            first_completed_clock=255,unique_preterminal_states=255,terminal_state="0x80",
            enumerated_clock_states=1024,reset_boolean_comparisons=comparisons,
            all_two_bit_sync_states_enumerated=True,button_synchronizer_byte_equations_unchanged=True,
            actual_rtl_clock_comparisons=1024,input_sha256=before,
            generated_input_sha256={str(path.relative_to(OUT)):sha(path) for path in sources[-3:]},
            common_rtl_sha256={str(path.relative_to(ROOT)):sha(path) for path in sources[:3]},
            completed_at_utc=datetime.now(timezone.utc).isoformat(),result=text.strip())
(OUT/"results.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print("PASS exhaustive startup path and all4 synchronized-button states:4096 reset comparisons")
