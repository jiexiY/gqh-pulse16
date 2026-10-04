# Pulse16

FPGA-based moving-average trade signals for the Gator Quant Hacks Hardware Track.
Pulse16 runs on a Tang Nano 20K and processes two independent streams of unsigned
16-bit prices. Each stream maintains a 16-price window and returns BUY, SELL or
NONE according to the challenge's crossing rules. All signal computation runs on
the FPGA; Python is used for verification only.

## Getting started

Start with software verification; **no FPGA board is required** for the build and
simulation steps.

1. **Set up your environment.** Follow [Setup and release verification](#setup-and-release-verification)
   to install Python, Gowin EDA Education and Icarus Verilog, then create a local
   Python environment. Gowin can be installed outside the project.
2. **Build and verify the design.** Follow [Build from source](#build-from-source)
   to run RTL simulation, compile a new bitstream, simulate the mapped circuit
   and run the regression tests. These steps generate new results.
3. **Test on hardware when available.** Follow [Program and test](#program-and-test)
   to detect a Tang Nano 20K, program SRAM and run the UART tests.

A successful software run reports **10,907 engine responses, 1,107 RTL UART
packets, 21 mapped-circuit packets and 100 passing regression tests**. Physical
USB/UART behavior and round-trip latency require the hardware step.

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

Use **Windows and Python 3.12 or newer**. Python 3.12 and 3.13 have been used for
this project. To build or simulate the design, also install
[Gowin EDA Education](https://www.gowinsemi.com/en/support/database/1865/) and
[Icarus Verilog](https://steveicarus.github.io/iverilog/). Make `iverilog` and `vvp`
available on PATH or under `.tools/iverilog/app/bin`.
Only physical-board testing requires a Tang Nano 20K and USB data cable; board
drivers are not needed for software-only verification.

Extract the project to a short, ASCII-only directory such as `D:\GQH\Pulse16`.
Gowin does not have to be installed inside the project. Use the actual paths to
your installed compiler and programmer in the commands below; paths containing
spaces must be quoted. The verified tool version is **V1.9.11.03 Education**.

From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For software-only verification, continue to [Build from source](#build-from-source).
For the supplied bitstream, run `.\preflight.ps1` before [Program and test](#program-and-test).
Preflight checks source, build reports and bitstream consistency; it does **not**
run the design or require archived physical-test logs. A fresh source-only build
runs preflight after generating its own reports and bitstream.

Optional: `.venv\Scripts\python.exe scripts/verify_release_evidence.py` verifies
the archived evidence only. It is not a fresh functional test, and is not a step
in the rebuild workflow. The supplied `bitstream/trade_top.fs`
has SHA-256:

```text
87400736f80c5e2d8b2bd5250f278955cfb237753736f84473c832dc8e913707
```

## Build from source

For a clean rebuild, create a separate source-only copy containing `rtl/`,
`constraints/`, `host/`, `sim/`, `scripts/`, `tests/` and the root project files
(`*.ps1`, `trade_top.gprj`, `requirements.txt`, `README.md`, `CHECKLIST.md`,
`.gitattributes` and `.gitignore`). Do not copy `reports/`, `bitstream/`, `build/`,
`impl/`, `.tools/` or `.venv/`. Complete the Python setup above in this new copy
and make the externally installed tools available before running:

```powershell
# Replace this example with the compiler path on this computer.
$Gowin = 'D:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe'
.\test.ps1
.\build.ps1 -Gowin $Gowin
.venv\Scripts\python.exe scripts/test_post_pnr.py --gowin $Gowin
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
# Replace this example with the programmer path on this computer.
$Programmer = 'D:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe'
.\program-board.ps1 -Programmer $Programmer -ListCables
.\program-board.ps1 -Programmer $Programmer -Scan -Location 273
.\program-board.ps1 -Programmer $Programmer -ProgramSram -Location 273
.\board-test.ps1                         # List serial ports only
.\board-test.ps1 -Port COM6 -Test quick
.\board-test.ps1 -Port COM6 -Test qualification
.venv\Scripts\python.exe scripts/stress_board.py --port COM6
```

`-Programmer` selects the installed executable explicitly. Without it, the helper
retains the optional project-local installation under
`.tools/gowin-portable/Gowin_V1.9.11.03_Education_x64/`. A missing explicit path
stops with an error; it never silently selects another programmer. Alternatively,
use the vendor Programmer GUI in **SRAM mode**. No bridge firmware update or
flash programming is required. SRAM configuration is lost when power is removed.

The test runner preserves organizer scripts and changes only PORT in temporary
copies. Qualification runs robust followed by full-range without resetting or
reprogramming. Logs and CSVs are written to `build/board-tests/`. Keep the host
awake and the cable connected throughout testing.

The helper verifies the selected FPGA and candidate hashes before SRAM
programming. No arguments display help without accessing hardware. A programmer
receipt is not a functional pass: run the quick and qualification tests afterward.

### Tool-path troubleshooting

- **Missing installed programmer:** check `$Programmer` points to the actual
  `programmer_cli.exe`, then supply `-Programmer $Programmer` for each operation.
- **Cannot locate Gowin for mapped simulation:** supply `--gowin $Gowin` to
  `scripts/test_post_pnr.py`. A previous build's `-Gowin` argument is not persistent.
- **Missing `iverilog` or `vvp`:** install Icarus and add its `bin` folder to PATH
  in the terminal running the commands. Reopen the terminal after changing PATH.
- **Stale build or changed hashes:** do not edit the manifest to suppress the
  check. In a separate source copy, rerun simulation, build and mapped simulation
  in that order, then use the newly generated artifacts and their own test results.

## Verification and limitations

The tooling in [commit `2842bc6`](https://github.com/jiexiY/gqh-pulse16/commit/2842bc6abb4b9ace380cf55f7dd0b1222df55022)
passed 10/10 fresh source-only workflows on one Windows host, including RTL
simulation, Gowin synthesis and place-and-route, mapped-circuit simulation and
all 100 regression tests per run. This verifies software execution on that host;
it does not establish physical-board behavior or compatibility with every laptop.

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
