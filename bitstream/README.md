# Physically verified 243-Logic candidate

`trade_top.fs` was generated with Gowin V1.9.11.03 Education from the current HDL
and unchanged organizer constraints. This exact image passed physical tests on
Tang Nano 20K board 9 using **temporary SRAM programming**.

SHA-256:
`87400736f80c5e2d8b2bd5250f278955cfb237753736f84473c832dc8e913707`

All **13,021 checked responses passed**: 21 quick, 1,000 qualification, 2,000
stress and 10,000 additional soak packets. Five robust/full-range qualification
pairs each received all responses, with 84/84 scored packets and 168/168 scored
actions correct per run. The median of five robust-run mean round-trip latencies
was **16.856447 ms**. These are local results, not official judging scores.

Synthesis: **243 Total Logic, 159 registers, 206 primitive LUTs, 36 ALUs,
2 BSRAM and 0 SSRAM**. Total Logic is distinct from primitive LUT count.
Place-and-route passed at the actual 27 MHz clock with zero setup/hold violations.
The transmitter has no intentional inter-byte gap; its nominal interface remains
115200 baud, 8N1. No meaningful host round-trip speedup is claimed.

`reports/build-summary.json` binds sources, bitstream and vendor reports.
`reports/physical-verification.json` summarizes later board verification; raw
evidence is in `reports/board/current243-20261004/`. Build-time physical-test flags
are unchanged historical records, not the later physical verification verdict.
Run `preflight.ps1` to check source/report/hash consistency before use.

After power loss, reprogram this exact file in SRAM mode and rerun verification.
Do not substitute another bitstream or attribute earlier-image tests to this one.
Second-laptop verification of this exact candidate has not yet been confirmed.

