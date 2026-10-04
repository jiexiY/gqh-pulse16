# Supplemental UART waveform equivalence evidence

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
.venv\Scripts\python.exe reports/uart-equivalence-20261003/replay.py --verify-only
.venv\Scripts\python.exe reports/uart-equivalence-20261003/replay.py
```

Replay uses only this archive and installed Icarus Verilog tools. It does not
need the original experiments/checkpoint folders or current production HDL.
If needed pass `--iverilog PATH` and `--vvp PATH`. Generated binaries, raw logs,
and the new replay report go into a new `build/uart-equivalence-replay/` folder;
the archived evidence is not overwritten.
