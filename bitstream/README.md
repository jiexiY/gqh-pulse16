# Physically verified final candidate

`trade_top.fs` was generated with Gowin V1.9.11.03 Education from this project's
HDL and the unchanged organizer constraints. **This exact file passed physical
tests on Tang Nano 20K board 9, COM6, using temporary SRAM programming.**

SHA-256:
`16cff3b2fd3e2b3f07c60f8001c922aac18c1b54edf8a1571514e5484c630542`

Five consecutive robust -> full-range qualification pairs passed without reset
or reprogramming: all 100 responses, 168/168 scored actions and zero UART timeouts
in every run. The final quick test passed 21 packets; supplemental stress passed
1,000 packets across 10 sessions without reset. The median of five robust-run
mean round-trip times was 16.830057 ms on the team's Dell. These are local
practice measurements, not official judging results.

Final synthesis usage: **437 total Logic, 428 registers, 1 BSRAM, 327 primitive
LUTs**. Total Logic, not the primitive LUT subtotal, is the ranking metric.

`reports/build-summary.json` records its SHA-256, source hashes, resource usage,
and timing. Physical evidence is in `reports/board/final-20261003/`, summarized
in `reports/physical-verification.json`. Run `preflight.ps1` to check that the
candidate and software evidence still match; the physical summary identifies the
exact tested bitstream separately. Reprogram this exact file in SRAM mode if
the board loses power, then rerun verification. The interrupted host-sleep stress
run is disclosed in the main README and is not counted as a completed pass.
Do not substitute an example bitstream or publish a different source revision.
Public repository visibility, Devpost submission and board return remain pending.

