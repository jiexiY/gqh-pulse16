# Pulse16

FPGA-based moving-average trade signals for the Gator Quant Hacks Hardware Track.
Pulse16 runs on a Tang Nano 20K and processes two independent streams of unsigned
16-bit prices. Each stream maintains a 16-price window and returns BUY, SELL or
NONE according to the challenge's crossing rules. All signal computation runs on
the FPGA; Python is used for verification only.

## Getting started

Choose the route that matches what you want to evaluate. Rebuilding is **not
required** to test the supplied bitstream on a board.

| Route | Required tools and hardware | Instructions |
|---|---|---|
| Test the supplied bitstream | Python + pyserial, Gowin Programmer, Tang Nano 20K, USB data cable and working JTAG/UART drivers | [Program and test](#program-and-test) |
| Simulate the RTL | Python and Icarus Verilog; no board or Gowin installation | [RTL simulation](#rtl-simulation) |
| Rebuild and verify from source | Python + pyserial, Gowin EDA Education and Icarus Verilog; no board required | [Build from source](#build-from-source) |

Start with the common [Python setup](#setup-and-release-verification), then follow
your chosen route. **Gowin Programmer loads an existing bitstream; the Gowin
compiler is needed only for rebuilding.** The full rebuild verification also uses
Gowin's simulation libraries. Physical USB/UART behavior and round-trip latency
can only be measured with a board.

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

The commands below target **Windows and Python 3.12 or newer**. Python 3.12 and
3.13 have been used for this project. Install only the additional tools required
by your chosen route:

- **Supplied-bitstream hardware test:** Gowin Programmer and working board
  JTAG/UART drivers. Neither the Gowin compiler nor Icarus is needed.
- **RTL simulation:** [Icarus Verilog](https://steveicarus.github.io/iverilog/).
  Make `iverilog` and `vvp` available on PATH or under `.tools/iverilog/app/bin`.
- **Full source rebuild:** Icarus plus the complete
  [Gowin V1.9.11.03 Education (Windows x64)](https://www.gowinsemi.com/en/document/main/database/1865/)
  package,
  including `gw_sh.exe` and the vendor simulation libraries. Programmer alone
  cannot rebuild the design.

Board drivers are not needed for either software-only route.

Extract the project to a short, ASCII-only directory such as `D:\GQH\Pulse16`.
Gowin does not have to be installed inside the project. Use the actual paths to
your installed compiler and programmer in the commands below; paths containing
spaces must be quoted. The verified tool version is **V1.9.11.03 Education**.

Enter the commands below in **Windows PowerShell or PowerShell 7**, from the
repository root. They launch Python directly: no `.ps1` script, virtual-environment
activation or execution-policy change is required for the application workflow.
The repository's `.ps1` files are optional convenience wrappers. Run commands in
order and stop if any fails; do not continue using stale outputs.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For software-only verification, choose [RTL simulation](#rtl-simulation) or the
complete [Build from source](#build-from-source) workflow.
For the supplied bitstream, keep the repository's `reports/` and `bitstream/`
directories and continue to [Program and test](#program-and-test).
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

## RTL simulation

After the Python setup and Icarus installation, run from the repository root:

```powershell
.venv\Scripts\python.exe -u sim/run_tests.py
```

This runs the actual RTL against generated reference vectors and writes fresh
results to `build/simulation-report.json`. A successful run checks **10,907
engine responses and 1,107 RTL UART packets**. No Gowin installation, FPGA board
or saved test logs are required. This route does not generate a bitstream,
measure hardware latency or verify placement-and-routing timing.

## Build from source

This route requires the full Gowin EDA installation and Icarus, but no board.

### Install and check the compiler

Download **Gowin V1.9.11.03 Education (Windows x64)** from the official link
above and install or extract the complete package. A location on `D:` or `E:`
is fine. Keep its directory structure intact; do not copy just `gw_sh.exe`.
An installation containing only `Programmer/bin/programmer_cli.exe` cannot
perform synthesis, place-and-route or mapped-circuit simulation.

Set these paths to the installation on this computer and check both files
**before starting a rebuild**:

```powershell
$GowinRoot = 'D:\Gowin\Gowin_V1.9.11.03_Education_x64'
$Gowin = Join-Path $GowinRoot 'IDE\bin\gw_sh.exe'
$GowinSimlib = Join-Path $GowinRoot 'IDE\simlib\gw2a\prim_sim.v'
if (!(Test-Path -LiteralPath $Gowin -PathType Leaf)) {
    throw 'Full Gowin EDA compiler missing. Install the Windows x64 Education package and correct $GowinRoot.'
}
if (!(Test-Path -LiteralPath $GowinSimlib -PathType Leaf)) {
    throw 'Gowin simulation library missing. Use the complete EDA installation, not Programmer alone.'
}
```

If either check fails, stop the rebuild route. The [RTL-only route](#rtl-simulation)
remains available with Icarus, but it does not establish a successful Gowin build.
The full toolchain must actually be installed on each computer doing a rebuild;
the repository does not bundle it.

### Generate fresh build results

For a clean rebuild, create a separate source-only copy containing `rtl/`,
`constraints/`, `host/`, `sim/`, `scripts/`, `tests/` and the root project files
(`*.ps1`, `trade_top.gprj`, `requirements.txt`, `README.md`, `CHECKLIST.md`,
`.gitattributes` and `.gitignore`). Do not copy `reports/`, `bitstream/`, `build/`,
`impl/`, `.tools/` or `.venv/`. Complete the Python setup above in this new copy
and make the externally installed tools available before running. Keep `$Gowin`
from the compiler check above in the same terminal:

```powershell
.venv\Scripts\python.exe -u sim/run_tests.py
if ($LASTEXITCODE -ne 0) { throw 'RTL simulation failed; stop here.' }
.venv\Scripts\python.exe scripts/build_fpga.py --gowin "$Gowin"
if ($LASTEXITCODE -ne 0) { throw 'Gowin build failed; stop here.' }
.venv\Scripts\python.exe scripts/test_post_pnr.py --gowin "$Gowin"
if ($LASTEXITCODE -ne 0) { throw 'Mapped-circuit simulation failed; stop here.' }
.venv\Scripts\python.exe scripts/preflight.py
if ($LASTEXITCODE -ne 0) { throw 'Artifact preflight failed; stop here.' }
```

This checks **10,907 engine responses, 1,107 RTL UART packets and 21
mapped-circuit packets**, then validates the freshly generated artifacts.

### Tooling regression tests

After the build and mapped simulation succeed, run the complete suite:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The complete suite has **100 tests**. Eight require the build reports and
artifacts, so full discovery in a source-only copy before building will fail;
do not copy old reports into that copy to obtain a pass.

Three tests exercise the optional `.ps1` wrappers. They use an existing `pwsh`
installation when available, otherwise Windows PowerShell, and require that
shell's existing policy to allow local scripts. This requirement applies to
those wrapper tests, not the direct-Python build and simulation commands above.
If policy blocks the wrapper tests, report them as blocked; do not weaken the
policy or claim 100 passing tests. Any failures or skips mean the full suite has
not passed.

The build uses `trade_top.gprj` and `scripts/build_gowin.tcl`, then exports the
bitstream and vendor reports. Use an ASCII-only project/tool path where possible.
Preserve original file line endings: source and evidence files are hash-bound.
Building regenerates release artifacts; a modified build requires its own
verification and must not inherit the supplied bitstream's physical-test results.

## Program and test

To evaluate the supplied bitstream, complete the Python setup and install Gowin
Programmer and the board drivers. **No compiler or source rebuild is required.**
Keep the supplied `reports/` and `bitstream/` directories: the preflight below
uses them to check artifact consistency, not to substitute for the live tests.

Detect the board's current JTAG location and UART port before programming.
`273` and `COM6` below are examples; replace them with the detected values.
Close other applications using the serial port.

```powershell
.venv\Scripts\python.exe scripts/preflight.py
# Replace this example with the programmer path on this computer.
$Programmer = 'D:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe'
.venv\Scripts\python.exe scripts/program_fpga.py --programmer "$Programmer" --list-cables
.venv\Scripts\python.exe scripts/program_fpga.py --programmer "$Programmer" --scan --location 273
.venv\Scripts\python.exe scripts/program_fpga.py --programmer "$Programmer" --program-sram --location 273
.venv\Scripts\python.exe scripts/board_test.py                         # List serial ports only
.venv\Scripts\python.exe scripts/board_test.py --port COM6 --test quick
.venv\Scripts\python.exe scripts/board_test.py --port COM6 --test qualification
.venv\Scripts\python.exe scripts/stress_board.py --port COM6
```

`--programmer` selects the installed executable explicitly. Without it, the helper
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

- **PowerShell says running scripts is disabled:** use the direct Python commands
  above, not the optional `.ps1` wrappers or `.venv\Scripts\Activate.ps1`.
  No execution-policy change is needed. The separate wrapper regression tests
  still require a shell policy that permits those scripts.
- **Compiler missing, but Programmer opens:** install the complete Gowin EDA
  Education package and repeat [the compiler checks](#install-and-check-the-compiler).
  `programmer_cli.exe` is not a substitute for `IDE/bin/gw_sh.exe`.
- **Missing installed programmer:** check `$Programmer` points to the actual
  `programmer_cli.exe`, then supply `--programmer "$Programmer"` for each operation.
- **Cannot locate Gowin for mapped simulation:** supply `--gowin $Gowin` to
  `scripts/test_post_pnr.py`. A previous build's `--gowin` argument is not persistent.
- **Missing `iverilog` or `vvp`:** install Icarus and add its `bin` folder to PATH
  in the terminal running the commands. Reopen the terminal after changing PATH.
- **Stale build or changed hashes:** do not edit the manifest to suppress the
  check. In a separate source copy, rerun simulation, build and mapped simulation
  in that order, then use the newly generated artifacts and their own test results.
