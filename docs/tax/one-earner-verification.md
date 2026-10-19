# One-earner tax verification

## Verified engine parity

Against the pinned vendored engine, the regenerated shipped profiles pass all 500 on-grid and 300 off-grid self-test cases with zero error. The browser parity report covers the same 800 cases with zero failures (maximum absolute error CHF 1). Two real generations produced identical SHA-256 hashes for all eight tax profiles and `gemeinden-2026.json`. Every profile retains 26 cantons, 461 rows per canton, and the `ESTV2026Age35` marker; the municipality authority retains 2,110 entries.

See `one-earner-selftest-report.json` and `browser-parity-report.json`.

## Official comparison remains failing

Vendored-engine parity is not official ESTV approval. The separate 29-case official comparison passes 8 cases and fails 21, with maximum absolute error CHF 20,315. Its comparability decision and official approval remain pending; the official gate remains failed and no threshold, evidence, quarantine, or approval was changed.

See `official-comparison-report.json`.
