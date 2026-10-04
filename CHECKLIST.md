# Pulse16 release checklist — 243 Logic / 159 registers

- [x] Preserve organizer protocol, pin constraints and original host tests.
- [x] Build with Gowin V1.9.11.03 Education for GW2AR-LV18QN88C8/I7 at 27 MHz.
- [x] Verify 243 Total Logic, 159 registers, 206 primitive LUTs, 36 ALUs and 2 BSRAM.
- [x] Verify zero setup/hold violations; retain and document warning PR1014.
- [x] Pass 10,907 engine and 1,107 bit-level UART simulation packets.
- [x] Pass independent 133,272-packet engine replay and 307-packet UART contract audit.
- [x] Pass 21-packet mapped-circuit functional simulation.
- [x] Program the exact candidate to board 9 in SRAM mode with a hash-bound receipt.
- [x] Pass quick test: 21/21 responses.
- [x] Pass five robust/full-range qualification pairs: 1,000/1,000 responses.
- [x] Pass supplemental stress: 2,000/2,000 responses.
- [x] Pass extended soak: 10,000/10,000 responses.
- [x] Audit all 13,021 current physical responses; exclude historical image results.
- [x] Record median of five robust-run means: 16.856447 ms; claim no meaningful speedup.
- [x] Preserve earlier verified source, bitstreams and historical evidence.
- [ ] Confirm second-laptop results for this exact image before claiming portability verification.
- [ ] Verify remote final commit and matching current Devpost repository/commit fields after publication.
- [ ] Return board and accessories under organizer loan instructions.

Current bitstream SHA-256:
`87400736f80c5e2d8b2bd5250f278955cfb237753736f84473c832dc8e913707`

Physical summary: `reports/physical-verification.json`.
Raw current evidence: `reports/board/current243-20261004/`.
Build-time manifest flags are intentionally immutable; later physical results
are recorded separately. Local test success is not an official competition score.

