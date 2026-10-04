# Verification evidence

## Current bitstream

| Record | Contents |
|---|---|
| [build-summary.json](build-summary.json) | Source/output hashes, resources and static timing |
| [physical-verification.json](physical-verification.json) | Summary of 13,021 checked physical responses |
| [board/current243-20261004/](board/current243-20261004/) | Programming receipt, raw tests and supplemental simulation records |
| [rtl-simulation.json](rtl-simulation.json) | RTL simulation results |
| [post-pnr-simulation.json](post-pnr-simulation.json) | Mapped-circuit functional simulation results |
| [gowin/](gowin/) | Unmodified vendor build, synthesis, placement and timing reports |

`board/current243-20261004/sha256.json` records hashes for all 92 archived
artifacts. Run `scripts/verify_release_evidence.py` from the repository root to
validate the manifest and its relationship to the current source and bitstream.

Build-time status fields and later physical verification are separate records.
Absolute paths within raw logs record the original test environment; they are
not required local paths. Reported response totals cover only the included
evidence. Local tests do not establish an official competition score.

## Archive scope

`archive267/`, other dated `board/` directories and `uart-equivalence-20261003/`
contain historical evidence. These records are not included in the current
bitstream's response totals. Raw reports, receipts and manifests are retained
without modification for traceability.
