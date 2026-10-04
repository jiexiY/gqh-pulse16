# Physically verified final candidate

`trade_top.fs` was generated with Gowin V1.9.11.03 Education from this project's
HDL and the unchanged organizer constraints. **This exact file passed physical
tests on Tang Nano 20K board 9, COM6, using temporary SRAM programming.**

SHA-256:
`6d37ce60101caf8d1580d44f368ef56a22af485da272043aff04627dc9ad167a`

Five consecutive robust -> full-range qualification pairs passed without reset
or reprogramming: all 100 responses, 168/168 scored actions and zero UART timeouts
in every run. The final quick test passed 21 packets; supplemental stress passed
1,000 packets across 10 sessions without reset. The median of five robust-run
mean round-trip times was 16.850055 ms on the team's Dell. These are local
practice measurements, not official judging results.

Final synthesis usage: **267 total Logic, 189 registers, 2 BSRAM, 223 primitive
LUTs**. Total Logic, not the primitive LUT subtotal, is the ranking metric.

`reports/build-summary.json` records its SHA-256, source hashes, resource usage,
and timing. Physical evidence is in `reports/board/competition-20261003/`, summarized
in `reports/physical-verification.json`. Run `preflight.ps1` to check that the
candidate and software evidence still match; the physical summary identifies the
exact tested bitstream separately. Reprogram this exact file in SRAM mode if
the board loses power, then rerun verification. The previous 437-Logic image's
interrupted host-sleep stress run is disclosed in the main README and is not
counted as a completed pass or as testing of this image.
Do not substitute an example bitstream or publish a different source revision.
The repository is public; unauthenticated access was verified on October 4, 2026.
Devpost submission and board return remain pending.

