# Verification evidence

The current release is the 243-Logic / 159-register candidate. Start with
`physical-verification.json`, `build-summary.json`, and `board/current243-20261004/`.
The latter preserves raw programming receipts, quick/qualification/stress/soak
results, and supplemental simulation evidence byte-for-byte. `sha256.json` maps
relative artifact names to their hashes. Original absolute paths inside raw
records are provenance, not portable lookup paths.

`archive267/` preserves superseded top-level reports for the previous release,
recoverable in full from Git tag `verified-267-20261004`. Other dated `board/`
folders and `uart-equivalence-20261003/` are historical and are not counted for
the current release. Build manifests retain their compilation-time status;
completed physical tests are recorded separately against the bitstream hash.

There are 13,021 locally checked physical responses for this release. No official
competition result or second-laptop verification of this release is claimed.
