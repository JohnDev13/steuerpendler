# Engineering amendment v1.3 — 17 October 2026

Canonical specification: `SPEC.md` v1.3, especially §§7, 7.1 and 20.
Previous complete specification: `docs/source/SPEC-v1.2-2026-10-17.md`.
Verified SHA-256 of that preserved file: `b63c1249507fca42005ec1f54eb3f97604912855b13f659e33aba906e32bce03`.

## Approved engineering contract

The schema-v2 precision program in `docs/tax/schema-v2.md` is integrated into the engineering specification. It replaces linear interpolation only for off-grid evaluation of valid v2 profiles. Exact grid rows remain authoritative; schema-v1 profiles retain the prior interpolation path. The program preserves authentic deduction and tariff transitions, taxable-income floors and splits, formula evaluation, federal CHF 263-per-child handling, personal tax, church-factor per-person normalization, and independent integer half-even rounding of final canton, Gemeinde and church components. CHF 10 display rounding remains separate.

New v2 profiles use the owner-selected ESTV standard defaults throughout: employed age-35 BVG via `meta.pensionDefault: "ESTV2026Age35"` and standard household-budget/estimated-rent handling via the matching `meta.budgetDefault: "ESTV2026Age35"`, without additional personal-expense inputs. The `rent30` operation derives 30% of estimated annual rent from current post-BVG net income and applies the authentic format and cap. Legacy compatibility does not permit removing markers or precision programs to evade current acceptance.

The visible qualification remains: **„Dies ist eine indikative Schätzung mit ESTV-Standardannahmen, keine individuelle oder verbindliche Steuerveranlagung und keine Steuerberatung.“**

## Preserved scope and gates

- All eight tax profiles, 461 grid rows per profile/canton, all 26 cantons and all 2,110 residential/tax Gemeinden remain required. Only workplaces are restricted to the 19 selected capitals.
- §7.1 limits are unchanged: on-grid `error <= max(2, 0.0001 * abs(expected))` over at least 500 deterministic cases; off-grid `error <= 10` over at least 300 deterministic cases; direct official `error <= max(5, 0.001 * abs(expected))` for all 29 scenarios. Exact-grid component selection remains within `1e-9` CHF.
- Frozen captures, dated failed observations and source/version/hash traceability remain evidence and are not rewritten by this amendment.
- Vendor/full-engine agreement is not independent official acceptance. Official-input comparability, direct ESTV acceptance, withholding/quarantine release, legal/data-rights/financial decisions and production approval remain pending unless separately evidenced. Existing quarantine and withholding stay fail-closed.

## Documentation changed from v1.2

- `SPEC.md`: v1.3 header, standard-default contract and §20 engineering amendment.
- `docs/tax/schema-v2.md`: integrated schema and arithmetic contract.
- `docs/source/SPEC-v1.2-2026-10-17.md`: byte-for-byte preserved v1.2 specification at the SHA-256 above.
- `docs/spec-amendments-v1.3.md`: this amendment register.