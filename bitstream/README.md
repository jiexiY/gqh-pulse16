# FPGA bitstream

`trade_top.fs` targets the Tang Nano 20K (`GW2AR-LV18QN88C8/I7`) at 27 MHz.
It was built with Gowin V1.9.11.03 Education using the checked-in HDL and
organizer-supplied physical constraints.

SHA-256:

```text
87400736f80c5e2d8b2bd5250f278955cfb237753736f84473c832dc8e913707
```

Resources: **243 Total Logic, 159 registers, 206 primitive LUTs, 36 ALUs,
2 BSRAM and 0 SSRAM**. Static timing reports zero setup/hold violations.
The interface is 115200-baud UART, 8N1, with no intentional inter-byte gap.

This exact image passed **13,021 checked physical responses** on board 9.
Its median of five robust-run mean round-trip latencies was **16.856447 ms**.
These are local results for the archived test sequence, not official judging scores.

Run `preflight.ps1` from the repository root before use. Program in **SRAM mode**;
the configuration must be reloaded after power loss. See the
[project README](../README.md#program-and-test) for setup and commands.

The [build manifest](../reports/build-summary.json) binds source and output hashes.
The [physical-test summary](../reports/physical-verification.json) and
[raw evidence](../reports/board/current243-20261004/) document the board results.

