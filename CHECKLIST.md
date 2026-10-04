# Verification results

These results apply to the supplied 243-Logic / 159-register bitstream and its
archived local test evidence.

| Check | Result |
|---|---|
| Target | Tang Nano 20K, GW2AR-LV18QN88C8/I7, 27 MHz |
| Toolchain | Gowin V1.9.11.03 Education |
| Synthesis | 243 Total Logic, 159 registers, 206 primitive LUTs, 36 ALUs, 2 BSRAM |
| Static timing | Zero setup/hold violations; PR1014 documented |
| RTL simulation | 10,907 engine packets and 1,107 UART packets passed |
| Supplemental simulation | 133,272-packet engine replay and 307-packet UART contract audit passed |
| Mapped-circuit simulation | 21 packets passed; no SDF delay annotation |
| SRAM programming | Board 9; hash-bound programming receipt archived |
| Quick test | 21 / 21 responses correct |
| Five robust/full-range pairs | 1,000 / 1,000 responses correct |
| Stress test | 2,000 / 2,000 responses correct |
| Extended soak | 10,000 / 10,000 responses correct |
| Total physical responses | 13,021 / 13,021 correct |
| Robust round-trip latency | 16.856447 ms median of five run averages |

Bitstream SHA-256:

```text
87400736f80c5e2d8b2bd5250f278955cfb237753736f84473c832dc8e913707
```

No incorrect responses or functional-test timeouts were observed in the archived
sequence. These finite local tests do not establish an official competition score
or exhaustive correctness. Host round-trip latency includes UART, USB and operating
system effects.

## Evidence verification

From the repository root, after setting up the Python environment:

```powershell
.\preflight.ps1
.venv\Scripts\python.exe scripts/verify_release_evidence.py
```

The checks validate current source/build consistency and all 92 artifacts listed
in the physical evidence manifest. They do not program or test connected hardware.

- [Physical-test summary](reports/physical-verification.json)
- [Raw evidence and hash manifest](reports/board/current243-20261004/)
- [Build manifest](reports/build-summary.json)
- [Evidence index](reports/README.md)

