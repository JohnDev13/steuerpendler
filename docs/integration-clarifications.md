# Integration clarifications — 16 October 2026

The first v1.1 amendment draft introduced requirements beyond the approved review. During integration they were narrowed to preserve v1's allowed choices, rather than misreport the existing map as satisfying a newly invented contract.

- Map remains LV95/EPSG:2056, explicitly allowed by v1 §6.6. No forced WGS84 reprojection or unvalidated 20 m displacement threshold.
- Three extra IDs remain in `gemeinden`, classified by `meta.noDataIds`. No fourth object is necessary.
- Geometric checks and joint shared topology remain mandatory; no unsupported claim of exhaustive cadastral/sub-metre or 1 m² gap certification.
- Coherent release uses deterministic final-file SHA-256 inventory embedded in the bundle. Original per-file schemas are preserved, instead of injecting release metadata into all payloads or adding an unnecessary RFC8785 implementation.
- Source versions, exact ID joins, reproducible builds, pending official checks and real CDN/cache coherence tests remain mandatory. This clarification does not waive size, correctness, licensing or owner launch gates.

Canonical technical wording is in SPEC.md §§6.6–6.7 and T2. Original supplied spec/review remain retained for traceability.
