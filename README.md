# Pulse16 — GQH FPGA trade signals

A Tang Nano 20K implementation of the GQH Hardware Track challenge. The FPGA
receives two prices, maintains independent 16-price histories, computes the
specified moving-average crossings, and returns an eight-byte response.
All signal computation runs on the FPGA; Python provides verification.

## Verified release — October 4, 2026

The current **243-Logic / 159-register** image passed **13,021 checked physical
responses** on Tang Nano 20K board 9 using temporary SRAM programming: 21 quick,
1,000 qualification, 2,000 stress and 10,000 additional soak packets. No incorrect
responses or functional-test timeouts were observed in these runs.

| Metric | Current result |
|---|---:|
| Synthesis Total Logic / registers | 243 / 159 |
| Primitive LUTs / ALUs | 206 / 36 |
| BSRAM / SSRAM blocks | 2 / 0 |
| Actual clock | 27 MHz |
| Setup / hold violations | 0 / 0 |
| Worst setup / hold slack | +30.275 ns / +0.199 ns |
| Median of five robust-run mean round-trip latencies | 16.856447 ms |

Final bitstream SHA-256:
`87400736f80c5e2d8b2bd5250f278955cfb237753736f84473c832dc8e913707`

The five robust-run means were 16.856447, 16.865141, 16.869819, 16.855650 and
16.855006 ms. Each robust/full-range run received all 100 responses, with
84/84 scored packets and 168/168 scored actions correct; warm-up responses were
checked separately. These are local measurements, not official judging results.
Host USB/Windows scheduling contributes to round-trip latency. No meaningful
end-to-end speed improvement over the prior release is claimed.

Compared with the previous 267-Logic / 189-register release, this version saves
24 Logic units and 30 registers, with unchanged BSRAM. Previous releases and
historical evidence remain preserved. Second-laptop results for this exact
image are not yet confirmed and are not included in the current totals.

Current physical evidence is summarized in `reports/physical-verification.json`;
raw evidence is under `reports/board/current243-20261004/`. The immutable build
manifest records build-time state; later physical verification is separate and
hash-bound. Public repository:
[jiexiY/gqh-pulse16](https://github.com/jiexiY/gqh-pulse16).

## Hardware and interface

- Tang Nano 20K, assigned board **9**, device `GW2AR-LV18QN88C8/I7`.
- Team: **jiexi yang**; participant **Jiexi Yang**, **University of Florida**.
- Top module: `trade_top`; compiler: **Gowin V1.9.11.03 Education**.
- Clock pin 4; reset pin 87; UART RX pin 70; UART TX pin 69; LEDs pins 15/16.
- Organizer physical constraints are unchanged. No external circuit or soldering is needed.

115200 baud, 8N1, byte bits LSB first, multi-byte values big-endian:

```text
Request:  [index16][item1_8][price1_16][item2_8][price2_16]
Response: [index16][item1_8][action1_8][item2_8][action2_8][reserved16]
Items:    A = 0x11, B = 0x22
Actions:  NONE = 0, SELL = 1, BUY = 2
Reserved: always 0
```

Indices 0–15 fill the windows and return NONE. Index 0 starts a fresh session.
Routing is by item ID; responses preserve request slot order. The interface is
stop-and-wait. The current transmitter adds **no intentional inter-byte gap**.
Its 234-clock divider gives approximately 115384.6 baud at 27 MHz (+0.16%).

## Build and verify

Create a project-local Python environment and install `requirements.txt`.
Install Icarus Verilog (`iverilog` and `vvp` on PATH, or under
`.tools/iverilog/app/bin`) and
[Gowin EDA Education](https://www.gowinsemi.com/en/support/database/1865/).
Local vendor tools are not included in the repository.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.\test.ps1
.\build.ps1 -Gowin C:\path\IDE\bin\gw_sh.exe
.venv\Scripts\python.exe scripts/test_post_pnr.py
.\preflight.ps1
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The build uses `scripts/build_gowin.tcl` and `trade_top.gprj`, checks resources
and timing, then exports the bitstream, vendor reports and hash manifest. Use
Total Logic, not the primitive LUT subtotal, for ranking. Reported internal
Fmax is 147.878 MHz; the design actually runs at **27 MHz**. Any source/settings
change requires fresh verification. Do not rebuild while a test is running.

Current RTL verification passed 10,907 engine packets and 1,107 bit-level UART
packets: 100 at production timing, 807 additional serial cases and 100 at each
of two host baud offsets (+2% and -2%). An independent exact-engine replay
checked 133,272 packets, and an additional UART contract audit checked 307.
The mapped-circuit functional simulation passed 21 packets using vendor
primitive models without SDF delay annotation. It does not simulate USB latency.

The Gowin helper uses existing Windows short-path aliases where available;
an ASCII-only project/tool path is preferable on another machine. A nonzero
compiler exit is failure even when an output exists. Keep original file line
endings: organizer scripts and build evidence are hash-bound.

## Program and test the board

Re-detect the actual JTAG location and COM port after connecting the USB data
cable. The numbers below are examples from the original host, not portable IDs.
Close other applications using the serial port before testing.

```powershell
.\program-board.ps1 -ListCables
.\program-board.ps1 -Scan -Location 273
.\program-board.ps1 -ProgramSram -Location 273
.\board-test.ps1                         # List serial ports only
.\board-test.ps1 -Port COM6 -Test quick
.\board-test.ps1 -Port COM6 -Test qualification
.venv\Scripts\python.exe scripts/stress_board.py --port COM6
```

The programming helper expects the local vendor-tool layout under
`.tools/gowin-portable/Gowin_V1.9.11.03_Education_x64/`. On another installation,
the vendor Programmer GUI in **SRAM mode** is also valid. Do not change drivers,
update bridge firmware or flash-program for this procedure. SRAM configuration
disappears on power loss: reload the exact checked bitstream. The helper verifies
the FPGA and records a hash-bound programming receipt.

Board-test helpers keep organizer `host/` originals unchanged, changing only
PORT in temporary copies. Each run saves logs/CSVs under `build/board-tests/`.
Qualification runs robust then full-range without reset or reprogramming. Keep
the laptop awake and cable undisturbed; retain failed and interrupted evidence.

## Implementation

One shared arithmetic datapath serves both items. A 32-word by 16-bit BSRAM
holds price histories; a second BSRAM stores per-item sums, comparison flags,
previous action and pointer. A 20-bit sum holds `16 * 65535 = 1048560`; shifting
right four bits implements floor division. Inclusive previous-price flags
preserve equality behavior; current crossing comparisons are strict. Without a
crossing, the prior action repeats. Index zero masks old metadata and warm-up
overwrites history.

The UART reuses stable request fields and resulting actions instead of redundant
copies. Receive/transmit share control where the stop-and-wait contract permits.
A startup sequence replaces the former counter while preserving its 255-clock
duration. The receiver checks start and stop bits; transmission begins only after
the complete request. No PLL or generated clock is used.

## Ranking and limitations

The organizer's October 3 clarification requires official and hidden full-range
qualification first. Qualified entries rank by **Total Logic**, then registers,
then five-run median latency; latency differences within 5% tie. BSRAM is allowed
and excluded from Total Logic. Judges rebuild committed sources/settings.
[Scoring clarification](https://discord.com/channels/1492317189968105502/1554962057672269905/1556050530592366734).

Local passes do not prove exhaustive correctness, hidden-seed success, judge-PC
latency or placing. Unknown IDs, missing/duplicated items and arbitrary byte
loss/insertion are outside the defined protocol. There is no framing marker for
recovery from every corrupted stream. PR1014 remains documented: the required
clock pin uses some generic routing. Reported setup/hold timing passes; organizer
pin constraints were not changed to suppress the warning.

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

Submission identifies the public repository and full final commit SHA. Return
the board and accessories under the organizer's loan instructions.

