# Preview verification and blockers

Snapshot: 17 October 2026. This file is a status/evidence index, not a launch approval.

- Public repository: https://github.com/JohnDev13/steuerpendler
- Verified Pages HTTPS test URL: https://johndev13.github.io/steuerpendler/ — actual live browser and 27-file byte-integrity evidence in `docs/deployment/Deployment-Report-v0.1.md`.
- Original source file: supplied SPEC v1; canonical amended reconstruction spec v1.1 and `docs/spec-amendments-v1.1.md` retain drift traceability.

## Established locally

- Real pinned tax source/data `43064402b1e52dbbc34dded6a305d7d536737c73`; vendor patch audit and original MIT notice.
- Eight generated profiles, 26 cantons × 461 rows each, and exact 2,110 Gemeinde IDs. Two tax generations have identical hashes.
- On-grid tax gate: 500/500 pass; maximum absolute error CHF 6.302668 remains within the per-case relative tolerance. This is not a blanket CHF 2 result.
- Off-grid gate: **FAIL**, 119/300 exceed CHF 10; maximum CHF 46.792. Reproduced by the parent in `docs/tax/integration-selftest.json`; no relaxed tolerance.
- 29 historical engine scenarios reproduce and table comparisons pass within CHF 10, max CHF 0.831. No official ESTV values were filled.
- Authentic map, exact ID join, shared topology and size checks. Public non-commercial testing is supported by current official attributed-use terms; commercial rights discrepancy remains open (`docs/map/publication-assessment.md`).
- Routing diagnostic uses real pinned r5py/R5 on explicitly synthetic tiny fixtures. Exact metric conformance **fails**; no national data was invented. 7 stdlib diagnostic tests pass, not T3 acceptance.
- Browser checks target the actual production build below `/steuerpendler/`; verify real map, search/selection, controls, profile loading, no unchecked financial output, content links, 400px layout, readable asset errors, pinned-byte mismatch, no cookies and no third-party requests.

## Not established / blocked

- **GitHub CI:** OAuth credential lacks `workflow` scope; workflow upload was rejected. Source task PRs may record local test results, never GitHub CI success.
- **Tax:** off-grid numeric gate fails; all tax-derived recommendations/totals are withheld in the public preview. ESTV verification and unverified-canton launch policy/owner approval pending.
- **Travel:** exact first-boarding metric, genuine frozen nationwide inputs, capacity pilot, full generation and all 30 official SBB checks pending. A preflight is not a generator.
- **Owner/legal:** operator contact and text approval, real-data golden Zürich top 10, commercial-rights resolution if relevant, production approval and real-phone acceptance pending.
- **Production hosting:** Cloudflare headers/cache/coherence checks, PR previews and production Lighthouse gates are not proved by a GitHub Pages preview. GitHub Pages uses its own host headers.

A working preview is useful for UI review; it is not completion of T1–T9. Actual HTTPS verification, deployed/source revisions, original-spec lineage, screenshots and 27-file byte-integrity evidence are recorded in `docs/deployment/Deployment-Report-v0.1.md`. No production gate is cleared by that hosting proof.
