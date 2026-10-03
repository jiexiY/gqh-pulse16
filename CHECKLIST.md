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
- [x] Synthesize final candidate: 437 total Logic, 428 registers, 1 BSRAM, 327 primitive LUTs; verify 27 MHz PnR with no setup/hold violations.
- [x] Generate candidate bitstream and save vendor reports plus source/output hashes.
- [x] Add repeatable build, serial-port/test helper, and read-only evidence preflight.
- [x] Pass final candidate's 21-packet mapped-circuit simulation and freshness audit.
- [x] Pass 89 tooling safety/regression tests, including changed-source/bitstream and failed-serial rejection.
- [x] User collected Tang Nano 20K board **9** and USB data cable; COM6 detected.
- [x] Load baseline in SRAM mode and pass original quick + robust tests on the physical board: 100 responses, 168/168 scored actions, zero timeouts, 16.894 ms average.
- [x] Add verified Total Logic / register / BSRAM reporting for the October 3 ranking clarification.
- [x] Add fail-closed fullrange/qualification runner and hash-bound physical evidence capture.
- [x] Acquire and hash-pin the organizer full-range script from its complete Discord preview; disclose LF normalization and unavailable original-download byte hash.
- [x] Evaluate BSRAM history separately; promote after full RTL, canonical build/mapped simulation and physical verification; preserve the baseline fallback.
- [x] Program final `16cff3b2...4c630542` candidate into SRAM with a successful hash-bound receipt.
- [x] Pass five consecutive original robust -> full-range qualification pairs without reset/reprogramming: every run 100 responses, 168/168 scored actions, zero UART timeouts.
- [x] Record five robust-run mean RTTs; median 16.830057 ms. Keep the verified 0.5 ms inter-byte gap.
- [x] Pass final quick test (21 packets) and supplemental stress (1,000 packets across 10 sessions without reset).
- [x] Preserve and disclose the incomplete 295-correct-packet stress run interrupted by Windows Modern Standby; do not count it as a pass.
- [x] Freeze final tested source/bitstream and document metrics, team details and limitations.
- [x] Push to `jiexiY/gqh-pulse16` and verify private visibility and matching remote commit (private visibility does not satisfy the final public-repository requirement).
- [ ] Publish public repository and submit its URL/full commit SHA on Devpost.
- [ ] Return board and all accessories in the **ballroom** by October 4, 11 AM EDT (latest Discord update).

The final source, simulation/build evidence, bitstream and local physical
qualification evidence are complete. Final bitstream SHA-256:
`16cff3b2fd3e2b3f07c60f8001c922aac18c1b54edf8a1571514e5484c630542`.
The clock-route warning PR1014 remains documented. Public repository visibility,
Devpost submission and board return are still pending; local passes are not an
official judging score or a first-place guarantee.

