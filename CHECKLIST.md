# FPGA build status

- [x] User selected Hardware / FPGA on October 3, 2026.
- [x] Read official protocol, scoring and submission requirements.
- [x] Save organizer constraints and serial tests unchanged; verify matching SHA-256 hashes.
- [x] Implement UART receiver/transmitter, independent item state and shared signal engine.
- [x] Pass 10,907 complete engine-response vectors against independently computed expectations.
- [x] Pass all 100 practice packets through bit-level UART simulation at production settings.
- [x] Pass 807 additional bit-level packets and 100 packets at each +/-2% host baud offset; save current source hashes.
- [x] Prepare Gowin project and download the reference Windows Education installer.
- [x] Prepare project-local Python environment with pyserial 3.5 for official board tests.
- [x] Extract signed Gowin Education package locally and verify project in its compiler.
- [x] Synthesize current candidate: 267 total Logic, 189 registers, 2 BSRAM, 223 primitive LUTs, 43 ALUs; verify 27 MHz PnR with no setup/hold violations.
- [x] Generate candidate bitstream and save vendor reports plus source/output hashes.
- [x] Add repeatable build, serial-port/test helper, and read-only evidence preflight.
- [x] Pass final candidate's 21-packet mapped-circuit simulation and freshness audit.
- [x] Rerun and pass all 89 tooling safety/regression tests after promotion, including changed-source/bitstream and failed-serial rejection.
- [x] User collected Tang Nano 20K board **9** and USB data cable; COM6 detected.
- [x] Load baseline in SRAM mode and pass original quick + robust tests on the physical board: 100 responses, 168/168 scored actions, zero timeouts, 16.894 ms average.
- [x] Add verified Total Logic / register / BSRAM reporting for the October 3 ranking clarification.
- [x] Add fail-closed fullrange/qualification runner and hash-bound physical evidence capture.
- [x] Acquire and hash-pin the organizer full-range script from its complete Discord preview; disclose LF normalization and unavailable original-download byte hash.
- [x] Evaluate BSRAM history separately; preserve the original 503-Logic fallback and the physically verified 437-Logic release/evidence.
- [x] Evaluate shared arithmetic, metadata BSRAM and UART storage/timer changes in isolation; pass full RTL and mapped simulation before physical testing.
- [x] Preserve the fully verified 307-Logic fallback; replace stored previous prices with inclusive comparison flags in an isolated experiment.
- [x] Preserve verified 274-Logic fallback; reduce UART latch/counter/capture logic in an isolated experiment without changing engine, clock, baud divider or byte gap.
- [x] Independently check 8,436 responses and 16,872 metadata invariants across 137 sessions; reject four deliberate relation-logic mutations.
- [x] Match prior UART output for 592 packets / 28,446,837 clocks, including 32 malformed-input injections; exclude the interrupted long production-equivalence attempt.
- [x] Program current `6d37ce60...9ad167a` candidate into SRAM with a successful hash-bound receipt.
- [x] Pass five consecutive original robust -> full-range qualification pairs without reset/reprogramming: every run 100 responses, 168/168 scored actions, zero UART timeouts.
- [x] Record five current robust-run mean RTTs; median 16.850055 ms. Keep the verified 0.5 ms inter-byte gap.
- [x] Pass final quick test (21 packets) and supplemental stress (1,000 packets across 10 sessions without reset).
- [x] Preserve and disclose the previous 437-Logic image's incomplete 295-correct-packet stress run interrupted by Windows Modern Standby; do not count historical results toward this image.
- [x] Promote the physically tested source/settings/bitstream/netlist/reports byte-for-byte without rebuilding; record provenance and pass canonical preflight.
- [x] Freeze final tested source/bitstream and document metrics, team details and limitations.
- [x] Previously push the 437-Logic version to private `jiexiY/gqh-pulse16` at `22f573f9ac2e0b04537fbfdcd703fe3fad058b88`; this is not the new candidate.
- [x] Commit and push the new 267-Logic source, tested bitstream and evidence; verify the matching remote commit.
- [ ] Update the older Devpost draft's metrics from the verified current evidence before submission.
- [x] Make `jiexiY/gqh-pulse16` public and verify unauthenticated access on October 4, 2026.
- [ ] Submit the public repository URL/full final commit SHA on Devpost and verify final submission.
- [ ] Return board and all accessories in the **ballroom** by October 4, 11 AM EDT (latest Discord update).

The current source, simulation/build evidence, bitstream and local physical
qualification evidence are complete. The physical sequence passed 2,021 replies:
21 quick, 1,000 qualification and 1,000 supplemental stress packets. Current
bitstream SHA-256:
`6d37ce60101caf8d1580d44f368ef56a22af485da272043aff04627dc9ad167a`.
Current evidence is under `reports/board/competition-20261003/`; the previous
274-Logic evidence remains under `reports/board/relation-20261003/`, the
307-Logic evidence remains under `reports/board/optimized-20261003/`, and the
older 437-Logic physical summary remains under `reports/board/final-20261003/`.
The clock-route warning PR1014 remains documented. This version's source,
bitstream and evidence are now pushed to the public repository. Devpost submission
and board return remain pending; local passes are not an official judging score
or a first-place guarantee.

