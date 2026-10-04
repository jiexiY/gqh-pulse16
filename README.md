# Pulse16

FPGA-based moving-average trade signals for the Gator Quant Hacks Hardware Track.
Pulse16 runs on a Tang Nano 20K and processes two independent streams of unsigned
16-bit prices. Each stream maintains a 16-price window and returns BUY, SELL or
NONE according to the challenge's crossing rules. All signal computation runs on
the FPGA; Python is used for verification only.

## Results

| Metric | Verified result |
|---|---:|
| Synthesis Total Logic | 243 |
| Registers | 159 |
| Primitive LUTs / ALUs | 206 / 36 |
| BSRAM / SSRAM blocks | 2 / 0 |
| Operating clock | 27 MHz |
| Setup / hold violations | 0 / 0 |
| Worst setup / hold slack | +30.275 ns / +0.199 ns |
| Checked physical responses | 13,021 / 13,021 |
| Median of five robust-run mean round-trip latencies | 16.856447 ms |

The archived board test sequence includes 21 quick-test responses, 1,000
qualification responses, 2,000 stress responses and 10,000 soak responses.
No incorrect responses or functional-test timeouts were observed. Each of the
five robust/full-range pairs received all responses, with 84/84 scored packets
and 168/168 scored actions correct per test; warm-up responses were also checked.

These are local measurements, not official judging results or a proof of
exhaustive correctness. Round-trip latency includes UART, USB and host scheduling.
The figures above refer only to the evidence included in this repository.

## Hardware and protocol

- Board: Tang Nano 20K, assigned board **9**, device `GW2AR-LV18QN88C8/I7`.
- Team: **jiexi yang**; participant: **Jiexi Yang**, **University of Florida**.
- Top module: `trade_top`; toolchain: **Gowin V1.9.11.03 Education**.
- Pins: clock 4, reset 87, UART RX 70, UART TX 69, LEDs 15/16.
- Physical constraints: unchanged organizer-supplied `19_tang_nano_20k.cst`.

The interface is stop-and-wait UART at 115200 baud, 8N1. Byte bits are sent
LSB first; multi-byte fields use big-endian byte order.

```text
Request:  [index16][item1_8][price1_16][item2_8][price2_16]
Response: [index16][item1_8][action1_8][item2_8][action2_8][reserved16]
Items:    A = 0x11, B = 0x22
Actions:  NONE = 0, SELL = 1, BUY = 2
Reserved: always 0
```

Indices 0–15 fill the windows and return NONE. Index 0 starts a fresh session.
Items are routed by ID, and responses preserve request slot order. Averages use
integer floor division; when no crossing occurs, the previous action is retained.
Transmission begins only after the complete request. The transmitter adds no
intentional inter-byte gap. Its 234-clock divider produces approximately
115384.6 baud at 27 MHz (+0.16% from nominal).

## Setup and release verification

Use Python 3 and a USB data cable. To build or simulate the design, also install
[Gowin EDA Education](https://www.gowinsemi.com/en/support/database/1865/) and
[Icarus Verilog](https://steveicarus.github.io/iverilog/). Make `iverilog` and `vvp`
available on PATH or under `.tools/iverilog/app/bin`.

From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.\preflight.ps1
.venv\Scripts\python.exe scripts/verify_release_evidence.py
```

These checks validate the supplied source, build reports, bitstream and archived
test evidence without accessing the board. The supplied `bitstream/trade_top.fs`
has SHA-256:

```text
87400736f80c5e2d8b2bd5250f278955cfb237753736f84473c832dc8e913707
```

## Build from source

```powershell
.\test.ps1
.\build.ps1 -Gowin C:\path\IDE\bin\gw_sh.exe
.venv\Scripts\python.exe scripts/test_post_pnr.py
.\preflight.ps1
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The build uses `trade_top.gprj` and `scripts/build_gowin.tcl`, then exports the
bitstream and vendor reports. Use an ASCII-only project/tool path where possible.
Preserve original file line endings: source and evidence files are hash-bound.
Building regenerates release artifacts; a modified build requires its own
verification and must not inherit the supplied bitstream's physical-test results.

## Program and test

Detect the board's current JTAG location and UART port before programming.
`273` and `COM6` below are examples; replace them with the detected values.
Close other applications using the serial port.

```powershell
.\program-board.ps1 -ListCables
.\program-board.ps1 -Scan -Location 273
.\program-board.ps1 -ProgramSram -Location 273
.\board-test.ps1                         # List serial ports only
.\board-test.ps1 -Port COM6 -Test quick
.\board-test.ps1 -Port COM6 -Test qualification
.venv\Scripts\python.exe scripts/stress_board.py --port COM6
```

The programming helper expects Gowin Programmer under
`.tools/gowin-portable/Gowin_V1.9.11.03_Education_x64/`. With another installation,
use the vendor Programmer GUI in **SRAM mode**. No bridge firmware update or
flash programming is required. SRAM configuration is lost when power is removed.

The test runner preserves organizer scripts and changes only PORT in temporary
copies. Qualification runs robust followed by full-range without resetting or
reprogramming. Logs and CSVs are written to `build/board-tests/`. Keep the host
awake and the cable connected throughout testing.

## Verification and limitations

RTL simulation passed 10,907 engine packets and 1,107 bit-level UART packets,
including nominal timing and host baud offsets of +2% and -2%. Supplemental
checks include a 133,272-packet engine replay, a 307-packet UART contract audit
and startup equivalence. Mapped-circuit functional simulation passed 21 packets
using vendor primitive models without SDF delay annotation.

Resource counts and timing results are recorded in [the build report](reports/build-summary.json).
The reported Fmax is 147.878 MHz; the actual operating clock remains **27 MHz**.
Warning PR1014 identifies generic routing on the required clock pin and remains
documented in the vendor reports. Reported setup and hold timing pass.

The supported protocol assumes two valid item IDs and complete stop-and-wait
requests. Unknown IDs, missing or duplicated items, and arbitrary byte loss or
insertion are outside its scope. There is no framing marker for recovery from
every corrupted stream. Local measurements do not guarantee judge-PC latency.

See [verification results](CHECKLIST.md), [physical-test summary](reports/physical-verification.json)
and [evidence index](reports/README.md) for reproducible supporting records.

## Sources and disclosure

- [Official hardware resources](https://github.com/ShayanNazir/GQH-Hardware-Track-Submission),
  revision `80467b5d0e481373daf126de9a0f57e67f19906b`: organizer physical constraints
  and original quick/robust host tests.
- `host/22_robust_uart_test_fullrange.py` is a verbatim export of the organizer's
  Discord file preview, normalized to LF. Its text length, line count and checksum
  matched the displayed source. The original downloadable byte hash is unavailable;
  the adjacent provenance JSON records the pinned local hash.
- [Official participant guide](https://www.gqhacks.com/hardware/GQH_Hardware_Track_Participant_Guide.pdf):
  challenge protocol and algorithm specification.
- [Sipeed board examples](https://github.com/sipeed/TangNano-20K-example) informed
  project XML and device configuration; no Sipeed HDL was copied.
- Verilog, local tests and documentation were generated with OpenAI Codex
  assistance during the event.
- Local simulation uses Icarus Verilog. Vendor and simulator binaries are not
  distributed with this repository.

