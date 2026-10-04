# Pulse16 — GQH FPGA trade signals

A Tang Nano 20K implementation of the GQH Hardware Track challenge. The FPGA
receives two prices, maintains a separate 16-price history for each item,
calculates the required moving-average crossings, and returns one response.
All computation happens on the FPGA. Python is used only for verification.

## Current status

The optimized 267-Logic candidate has been programmed into **board 9's temporary SRAM**
and physically verified on COM6. **Five consecutive local qualification pairs
passed**: each original robust test was immediately followed by the organizer's
full-range unsigned 16-bit test, without reset or reprogramming. Every run received
all 100 responses, returned all 168 scored actions correctly, and had zero UART
timeouts. The median of the five robust-run mean round-trip latencies was
**16.850055 ms** on the team's Dell. The final quick test passed all 21 packets;
supplemental stress passed **1,000/1,000 packets across 10 sessions without reset**.
The complete physical sequence audited **2,021 replies**: quick, five qualification
pairs, then stress, without reset or reprogramming after the SRAM load.

Final `bitstream/trade_top.fs` SHA-256:
`6d37ce60101caf8d1580d44f368ef56a22af485da272043aff04627dc9ad167a`

Raw current evidence is in `reports/board/competition-20261003/`, with the summary in
`reports/physical-verification.json`. These are local practice results, not an
official judging score or a placement guarantee. The immutable build manifest
records the build-time state; physical evidence is separate and hash-bound.
**The source, tested bitstream and evidence are published in the public repository.
Devpost submission and board return remain.**

Verified October 3, 2026: **10,907 engine packets and 1,107 bit-level UART
packets passed**. The UART total includes 100 packets with production timing,
807 additional cases with shortened inter-byte gaps, and 100 packets at each
of two host baud offsets (+2% and -2%). This is a complete local simulation
verification of the final HDL. An additional **8,436 packets and 16,872 metadata
invariant checks** passed across 137 sessions, with four deliberately faulty variants
rejected; see `reports/relation-verification.json`. The new UART also matched the
previous transmitter over 592 packets and 28,446,837 simulated clocks, including
32 malformed-input injections during transmission. The production-gap subset
contained 64 packets; the 528-packet short-gap subset covered all values of both
echoed index bytes. Exact inputs, logs, and replay instructions are archived in
`reports/uart-equivalence-20261003/`. An earlier 528-packet production-gap
comparison was stopped for runtime and is explicitly not counted as a pass.
Gowin V1.9.11.03 Education reports **267 total Logic**,
189 registers, 2 BSRAM blocks, 223 primitive LUTs, 43 ALUs and 0 SSRAM blocks. Total Logic is
the ranking metric; the primitive LUT subtotal is a different measurement.
Place-and-route at 27 MHz reports **zero setup and hold violations**, with worst
setup slack 30.616 ns and worst hold slack 0.215 ns. Reported internal Fmax is
155.729 MHz; the design still runs at 27 MHz, not at that reported Fmax.

The build retains warning PR1014 for the required pin-4 clock input using some
generic routing. Internal timing and the physical tests described above pass;
the warning is retained rather than suppressed. The organizer pin constraints
have not been changed.

Quick commands from this folder:

```powershell
.\build.ps1                              # Compile, check timing, export candidate
.venv\Scripts\python.exe scripts/test_post_pnr.py  # Mapped-circuit simulation
.venv\Scripts\python.exe sim/verify_relation.py   # Supplemental stored-state invariants
.\preflight.ps1                          # Read-only source/report/hash audit
.\board-test.ps1                         # List COM ports; opens no port
.venv\Scripts\python.exe -m unittest discover -s tests -v # Tooling safety/regression checks
```

`reports/post-pnr-simulation.json` records a **passed** 21-packet functional
simulation of the mapped circuit on October 3. Its bitstream/netlist
hashes must match the build; `preflight.ps1` checks this. This test uses the
production UART divider and byte gap, with vendor primitive models but no SDF
delay annotation. Full-range history values exercise bit 15 and the maximum
16-price running sum. It does not model the USB bridge. The tested HDL, settings,
bitstream, mapped netlist and reports were promoted byte-for-byte from the isolated
competition-optimization experiment, without rebuilding. `reports/rtl-simulation-origin.json`
records the matching hashes and test inputs; the simulator runner differs only
in tool-path lookup, with the remaining AST identical. The canonical freshness
audit passed after promotion. All **89 tooling safety/regression tests passed**
again after promotion.

Still required before submission:

- Enter the public repository URL and its full final commit SHA on Devpost.
  Use `git rev-parse HEAD` after syncing the published `main` branch.
- Verify the completed Devpost submission and return the borrowed board and accessories.

The **public** repository
[jiexiY/gqh-pulse16](https://github.com/jiexiY/gqh-pulse16) contains the current
267-Logic source, tested `.fs`, and verification evidence. Public visibility and
unauthenticated access were verified on October 4, 2026. Publication does not
submit the entry to Devpost: the entry has not been officially judged or submitted.
The prior 437-Logic release and later optimization evidence remain in history,
clearly separate from the current candidate's measurements.

## Start here if FPGA is new to you

This team collected **one Tang Nano 20K, board 9, and a USB data cable**. No
external circuit, soldered header pins or extra peripherals are needed for this
challenge. The pickup form's number identifies the assigned board, not a quantity.
Review the loan terms yourself. Return the board and accessories in the ballroom
by Sunday, October 4, 2026 at 11 AM EDT; the loan form lists possible replacement
liability up to $50.

An FPGA is a configurable digital circuit. Verilog describes that circuit.
Gowin converts our Verilog into a `.fs` programming file; USB loads it onto the
board. A simulator can check the design before the board is available.

The data flow is:

```text
PC test → USB serial bridge → UART receiver → packet decoder
                                            ↓
                              two item histories + shared arithmetic
                                            ↓
PC test ← USB serial bridge ← UART sender ← 8-byte response
```

The trading rule is fixed by the challenge, so our engineering choices are how
to implement it correctly, use fewer chip resources, and communicate reliably.

## Hardware and project

- Board: Tang Nano 20K, device `GW2AR-LV18QN88C8/I7`, device family `GW2AR-18C`.
- Assigned board ID: **9** (confirmed by the participant).
- Team name: **jiexi yang**; participant: **Jiexi Yang**, **University of Florida**.
- Top module: **`trade_top`**.
- Clock: 27 MHz; clock constraint is `constraints/trade_top.sdc`.
- Gowin EDA version used for the completed build: **V1.9.11.03 Education**.
- Organizer reference tool version: V1.9.11.03 Education.
- Additional peripherals: none; the on-board USB serial bridge is used.

| Port | Pin | Function |
|---|---:|---|
| sys_clk | 4 | 27 MHz input |
| reset_btn | 87 | Optional reset, active high / pull-down |
| uart_rx_i | 70 | Serial input from BL616 |
| uart_tx_o | 69 | Serial output to BL616 |
| led0_n | 15 | Low while processing/sending |
| led1_n | 16 | Unused, driven high |

The physical constraints are copied without modification from the organizer's
`19_tang_nano_20k.cst`. The simulation and private tools directories are excluded
from synthesis by the project file.

## Build and program

1. On this machine, the signed vendor package is extracted under
   `.tools/gowin-portable/Gowin_V1.9.11.03_Education_x64/`; the command-line
   compiler works without a system-wide installation. The programming helper
   does not install drivers or update board firmware. On another machine, obtain
   [Gowin EDA Education](https://www.gowinsemi.com/en/support/database/1865/).
2. Run `build.ps1`. It uses `scripts/build_gowin.tcl`, opens `trade_top.gprj`,
   sets the top module and 27 MHz targets, and runs synthesis and place-and-route.
   For another installation, use `build.ps1 -Gowin C:\path\IDE\bin\gw_sh.exe`.
   A fresh checkout first needs Python, Icarus Verilog, and a passing `test.ps1` run.
3. The script checks **total Logic**, registers, BSRAM and primitive LUT usage,
   timing violations, required clock/device, source freshness, and output freshness.
   The current ranking count is 267 Logic. The separate primitive LUT count is
   223; use the report's aggregate Total Logic for ranking, not its LUT subtotal.
4. On success it exports `bitstream/trade_top.fs`, unmodified vendor reports in
   `reports/gowin/`, and a source/output hash manifest. Run the mapped-circuit test
   and `preflight.ps1` before moving on. Do not rebuild while a test is running.
5. Keep the candidate unchanged between programming and testing. If any RTL,
   constraints, or build settings change, rerun the relevant verification and build.
6. Connect the board with the data cable. Run `program-board.ps1 -ListCables`,
   then `program-board.ps1 -Scan -Location 273`, substituting the current decimal
   location from the listing. On the tested machine, JTAG was cable 0/location 273;
   do not assume that location remains the same after reconnecting.
7. Run `program-board.ps1 -ProgramSram -Location 273` with that verified location.
   This checks the candidate and exact FPGA, loads **temporary SRAM only**, and
   records a hash-bound programming receipt. No arguments display help without
   touching hardware. No flash erase/program or firmware-update operation is exposed.
8. Close any Gowin Programmer GUI before opening the UART port. Do not change board
   firmware or USB drivers without guidance from the organizers. SRAM contents are
   lost when the board loses power; reprogram the same `.fs` after reconnecting.

The GUI project was successfully opened by the actual Gowin command-line tool.
Build options live in the checked-in Tcl script; use the script for reproducibility
instead of relying on an ignored GUI process-configuration file under `impl/`.

Windows path note: this Gowin release generated output but crashed during cleanup
with our long Unicode paths (exit code `0xC0000374`). The build helper uses existing
Windows short-path aliases for the compiler and project. Two consecutive builds
then exited successfully. If aliases are unavailable, use an ASCII-only tool/project
path. A nonzero compiler exit is still treated as failure, even if a `.fs` exists.
In the restricted automation environment Gowin cannot write its optional AppData
`sh.log`; the full build output is instead captured under `reports/gowin/build.log`.
For the Programmer CLI, the helper resolves the parent directory's existing
short path while preserving the exact `.fs` basename. This path handling was
physically verified by the successful SRAM receipt at
`reports/board/competition-20261003/programming/receipt.json`.

## Verification

Run the local HDL simulations with Icarus Verilog installed, or with the local
simulator under `.tools/iverilog/app/bin`:

```powershell
.\test.ps1
# Or specify Python explicitly:
.\test.ps1 -Python C:\path\to\python.exe
```

The core test checks full response packets against a model that recomputes the
entire window sum; the model is also checked against the organizer's Python
reference class. Cases cover the practice seed, 100 other random seeds with
16-bit prices, all-zero/all-maximum prices, rounding boundaries, equality,
held actions, swapped slots during warm-up and scoring, high packet indices,
and repeated sessions without an external reset.

The serial test drives and decodes individual bits through the actual top
module, including nominal baud, +/-2% host baud, false start pulses, malformed
stop bits, pauses between request bytes, exact response length, and no reply
before the complete request. All serial tests use the production clock divider.
The 100 official practice packets exercise the production byte gap; broader
serial regressions shorten that gap to save simulator time.

For the physical board, find its actual COM port and close Gowin Programmer and
other port users. The helper leaves the official `host/` originals unchanged and
runs copies with **only `PORT` changed**. Each run has its own timestamped directory
under `build/board-tests/`, including logs and the official robust CSV/summary.
It rejects Bluetooth ports and checks output verdicts, not merely exit codes.

```powershell
.\board-test.ps1                       # Read-only port listing
.\board-test.ps1 -Port COM6             # Replace COM6 with the actual FPGA port
.\board-test.ps1 -Port COM6 -Test robust # Repeat without resetting the board
.\board-test.ps1 -Port COM6 -Test qualification # Robust then fullrange, no reset/reprogram
.venv\Scripts\python.exe scripts/stress_board.py --port COM6 # Supplemental 1,000-packet stress
```

You may also run the official scripts directly after changing only their PORT
assignment, but then the helper's unchanged-source check will reject those originals.
Keep the robust test's CSV and summary. Run it again without resetting the board
to check session restart. Never alter the official protocol or scoring logic.
If cloning this project elsewhere, first create `.venv` with `python -m venv .venv`
and install `requirements.txt` into it. Put `iverilog` and `vvp` on PATH (or under
`.tools/iverilog/app/bin`). Set the Gowin compiler path using `-Gowin`/`--gowin`
as shown above. The SRAM helper expects the documented local vendor-tool layout;
on a different installation, the vendor Programmer GUI in SRAM mode is also valid.
The repository's `.gitattributes` preserves mixed LF/CRLF file bytes because the
organizer originals and build evidence are hash-bound. Do not normalize line endings.

## Implementation choices

`signal_engine.v` processes the two slots through one arithmetic datapath, while
maintaining independent sums, previous comparison flags, pointers, and last actions. A
32-word by 16-bit synchronous memory holds the two price windows in one BSRAM.
One additional BSRAM block holds two 28-bit item records: 20-bit sum, two inclusive
comparison flags, 2-bit action and 4-bit pointer. At each commit, the flags record
whether the current price is less than or equal to, and greater than or equal to,
its newly completed average. Equality sets both flags. On the next packet these
are exactly the prior-price comparisons the trading rule needs, so the previous
16-bit price and repeated comparison-selection logic are unnecessary. Flags are
updated during warm-up too, including index 15 before the first scored packet.
Request acceptance captures only the prices and item
selectors needed for the two slots, rather than another complete packet copy.
Gowin's documented `syn_ramstyle = "block_ram"` attribute selects block memory,
which the revised ranking excludes from Total Logic. Avoiding a
physical reset on the memory permits synthesis to infer RAM instead of a bank
of resettable registers. Index zero masks old sums and pointers to zero for both
items, while warm-up forces NONE and writes fresh metadata. Warm-up overwrites
each history entry before it can affect an average, invalidating old-session data.

The sum uses 20 bits: `16 * 65535 = 1048560`, which fits. Dividing by 16 is a
four-bit shift, which implements the specified floor operation. Old-price
comparisons use the old average; current-price comparisons use the updated
average. Prior comparisons are inclusive and current comparisons are strict.
One zero-extended 17-bit subtractor compares the current price and updated average;
one 20-bit add/subtract unit removes the oldest price and then adds the new one.
With no crossing, the previous action is repeated.

The receiver synchronizes the input, checks the start bit, samples near each
bit's center, and rejects an invalid stop bit. It shifts sampled UART bits and
writes incoming packet bytes into indexed fields. For the required IDs 0x11 and
0x22, one selector bit preserves each item's identity and slot order. Transmission
reuses the stable request index/item fields, stores only the resulting actions,
and shares one timer between baud timing and inter-byte idle. Receive and transmit
share a byte counter because valid traffic is stop-and-wait; framing errors during
transmission cannot reset that counter. Two-byte fields use enabled byte shifts,
and the receiver exposes its completed shift register only through a valid-qualified
interface. A stop-bit shift sentinel replaces the transmit bit counter while
preserving every output bit's duration. The transmitter inserts an
**0.5 ms gap between response bytes** to accommodate the BL616 bridge. This
setting passed the final quick test, five consecutive robust/full-range pairs
and the completed 1,000-packet supplemental stress test.
The 234-clock bit divider gives approximately 115384.6 baud at 27 MHz, a +0.16%
offset from nominal. There is no PLL or generated clock.

## Fixed interface

115200 baud, 8N1, byte bits LSB first, multi-byte values big-endian.

```text
Request:  [index16][item1_8][price1_16][item2_8][price2_16]
Response: [index16][item1_8][action1_8][item2_8][action2_8][reserved16]
Items:    A = 0x11, B = 0x22
Actions:  NONE = 0, SELL = 1, BUY = 2
Reserved: always 0
```

Indices 0–15 fill the windows and return NONE. Index 0 starts a fresh session.
Routing is by item ID and responses preserve the request's slot order.

## Hardware measurements — current 267-Logic candidate, October 3

| Metric | Measured result |
|---|---|
| Qualification pairs | 5 / 5 passed; robust then full-range, without reset/reprogramming |
| Correct packets / 84 scored | 84 / 84 in every robust and full-range run; all 100 replies audited |
| Correct actions / 168 scored | 168 / 168 in every robust and full-range run |
| UART timeouts | 0 across all five qualification pairs |
| Median of five robust-run mean RTTs | 16.850055 ms on the team's Dell |
| Final quick test | 21 / 21 packets passed |
| Supplemental stress | 1,000 / 1,000 packets, 10 sessions without reset |
| Total Logic / registers / BSRAM | 267 / 189 / 2, synthesis report |
| Primitive Gowin LUT usage | 223 (synthesis report; not a physical measurement) |
| Place-and-route timing | Pass at 27 MHz; setup +30.616 ns, hold +0.215 ns |
| Board / UART / PC used | Tang Nano 20K board 9 / COM6 / Dell Inspiron 15 3520 |

The five robust-run mean RTTs, in order, were **16.860392, 16.839586, 16.839027,
16.876044 and 16.850055 ms**. Full-range runs establish correctness, not an
additional rescored latency result. The evidence directory contains the final
programming receipt, `qualification-1` through `qualification-5`, `quick`, and
`stress`. All five pairs, the quick test and the stress run passed for this image.

The immediate predecessor used **274 Logic, 203 registers and 2 BSRAM**, with
16.857986 ms median RTT. Its exact source, bitstream and reports are preserved at
`build/checkpoints/verified-274-before-competition/`; its physical evidence remains
at `reports/board/relation-20261003/`. This round saves **7 Logic units (2.6%)**
and **14 registers**, with unchanged BSRAM usage. The small RTT change is not
treated as a meaningful speed improvement. Total Logic is **46.9% below the
original 503-Logic baseline**. All current physical tests were rerun for this image.

Earlier, replacing prior-price storage with relation flags reduced 307 Logic to
274, with one fewer BSRAM. The 307-Logic fallback remains at
`build/checkpoints/verified-307-before-relation/`, with physical evidence at
`reports/board/optimized-20261003/`. Additional shared-ALU and byte-serial arithmetic
experiments measured 276 and 296 Logic and were rejected. Removing duplicate
engine input capture saved registers but no Logic and changed the standalone
handshake contract, so that experiment was also rejected.

An older physically verified version used **437 Logic, 428 registers and
1 BSRAM**, with a five-run median of 16.830057 ms. Its bitstream SHA-256 was
`16cff3b2fd3e2b3f07c60f8001c922aac18c1b54edf8a1571514e5484c630542`;
its physical summary and raw evidence remain under `reports/board/final-20261003/`.
The current design saves **170 Logic units (38.9%) and 239 registers** relative to
that version, using one more BSRAM block. Judge-PC results remain unknown.

The earlier historical baseline used **503 Logic, 444 registers and 0 BSRAM** and
passed the original quick/robust tests at 16.894 ms mean RTT. Moving its history
to BSRAM produced the 437-Logic version, saving 66 Logic units (13.1%). That
baseline's local fallback checkpoint is `build/checkpoints/baseline-before-bsram/`.
None of these older physical results are counted as tests of the current image.

### October 3 scoring clarification

The organizer's 5:09 PM Discord announcement supplements the original guide:
qualification requires official 100/100 and a second hidden full-range price test
(0–65535), immediately afterward without reprogramming. Qualified entries rank
by lowest synthesis **Total Logic**, then registers, then median latency over five
runs; latency differences within 5% tie. BSRAM is allowed and excluded from Logic.
Judges rebuild committed sources/settings using Gowin V1.9.11.03. A local pass
does not prove hidden-seed success or judge-PC latency.

[Scoring announcement](https://discord.com/channels/1492317189968105502/1554962057672269905/1556050530592366734)

## Known limitations

The judge's valid stop-and-wait traffic is supported; this is not a general
market feed protocol. Unknown item IDs, missing/duplicated items, missing
packets, and arbitrary packet framing corruption are outside that protocol.
A byte framing error discards the partial request. The protocol has no framing
marker to recover reliably from every possible dropped or inserted byte.

Local full-range qualification and the supplemental stress test passed, but
unknown judge seeds, judge-PC USB scheduling, and arbitrary traffic are not
exhaustively verified. Synthesis inferred one SDPB BSRAM block for history, with
16-bit read/write ports, and one additional block for metadata; no SSRAM is used.
The generated netlist retains the power-on
and reset-synchronizer initialization values. Simulated wire behavior cannot
predict USB/Windows latency. No test result constitutes a first-place guarantee.

During testing of the previous 437-Logic image, one supplemental stress run was
stopped by its 180-second overall
safety limit after **295 correct packets**. Windows event logs confirmed Modern
Standby from **6:23:12 PM to 6:27:48 PM EDT** after an idle timeout. This was a
host sleep interruption, not a DUT UART timeout or correctness failure. Its
partial evidence is retained under `reports/board/final-20261003/interrupted-stress`;
the subsequent complete 1,000-packet historical run passed. Keep the laptop awake
and the cable undisturbed during testing. The interrupted run is not a completed
pass, and neither historical run is counted in the current candidate's results.

PR1014 is documented rather than suppressed: the required clock pin is listed as
LPLL1_T_in, not a GCLK pin, and the report shows a generic route feeding the primary
clock network. The reported static timing margins above pass; this does not prove
physical reliability. Do not change the official `.cst` to make the warning disappear.

## Sources and disclosure

- [Official hardware resources](https://github.com/ShayanNazir/GQH-Hardware-Track-Submission),
  downloaded at revision `80467b5d0e481373daf126de9a0f57e67f19906b`.
  `constraints/19_tang_nano_20k.cst` and the original quick/robust `host/` scripts
  are organizer files.
- `host/22_robust_uart_test_fullrange.py` is a verbatim export of the complete
  organizer Discord file preview, normalized to LF after browser download stalled.
  Its text length, line count and checksum matched the displayed source; its local
  SHA-256 is pinned. The original downloadable byte hash is unavailable. See the
  adjacent provenance JSON. The runner changes only PORT in temporary test copies.
- [Official participant guide](https://www.gqhacks.com/hardware/GQH_Hardware_Track_Participant_Guide.pdf)
  controls the protocol, algorithm and judging requirements.
- [Sipeed board examples](https://github.com/sipeed/TangNano-20K-example)
  informed the project XML/device configuration. No Sipeed HDL was copied.
- Verilog, local tests and documentation were generated with OpenAI Codex
  assistance during the event. The team must review and understand the code.
- Local simulation uses [Icarus Verilog](https://steveicarus.github.io/iverilog/).
  Tool binaries under `.tools/` are local dependencies, not submission assets.

The Hardware-specific instructions and the current Hacker Guide give Sunday,
October 4, 2026, **11 AM EDT** for non-Quant submission and hardware board return.
The latest organizer instruction says return the FPGA in the **ballroom** at
11 AM, and there are **no presentations** for this track.
[Return update](https://discord.com/channels/1492317189968105502/1554962057672269905/1556037210308870238)
Aim to submit by 10 AM as a safety buffer; check organizer announcements for changes.
The final submission requires a public repository and full final commit SHA.
Put the SHA in Devpost; do not try to include a commit's own SHA in its README.

