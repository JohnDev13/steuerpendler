# Steuerpendler — GitHub Pages preview deployment report v0.1

**Live test site:** https://johndev13.github.io/steuerpendler/  
**Public repository:** https://github.com/JohnDev13/steuerpendler  
**Status:** working non-production, non-commercial UI preview; not completion of the tax/commute product.

## Verified actual deployment

GitHub reports the `gh-pages` deployment **built**, HTTPS enforced, with no build error. The published site was opened and exercised in Chromium 156.0.8078.4, not inferred from a successful local build. Browser verification: **17 October 2026, 09:04:41 UTC**.

- HTTP 200 for the application and all three built content pages.
- Genuine map: 2,110 municipality IDs plus the three explicitly non-tax source areas, 2,113 selectable paths.
- Search/select Bern and keyboard-select Zug update details. Desktop and 400px-wide layout render without horizontal overflow.
- No unverified tax totals/recommendations shown; no ranked rows. Missing travel data is explicitly explained.
- No page/console errors, cookies or third-party requests during the tested ordinary app flow. Static requests remain GETs to this Pages origin. Hosting IP/path logs are still possible and are disclosed; this is not a claim that requests never leave the browser.
- A genuinely absent JSON URL returns **HTTP 404**, not a misleading HTML-200 fallback.
- **27 public static files fetched independently via HTTPS have exact SHA-256 byte equality with the built artifact**, including every generated profile, the map, app assets, content pages and notices. Deployment-control files `.nojekyll` and `_headers` are excluded from this HTTP test.
- Observed cold initial transfer: **375,079 bytes** including headers/compressed bodies. This incomplete-preview observation does not prove the future real commute-results budget, mobile P95, Lighthouse or full CDN/cache-coherence acceptance.

Raw evidence: [`browser-report.json`](browser-report.json), [`asset-verification.json`](asset-verification.json), [`preview-desktop.png`](preview-desktop.png), [`preview-mobile.png`](preview-mobile.png).

## Source / data / documentation traceability

- GitHub functional-source revision, merged via task PR #9: `11ef7459b601ecf3e8fe0ba04a0e68580ad79b12`.
- Canonical local source used to build the preview: `c7eb92cb03319f2049011a97e7afa06b2245c467`. Its functional source equals GitHub main; intentionally unuploaded workflow definitions are retained only in the source artifact. A later evidence-only PR does not change the deployed application.
- Actual Pages artifact revision: `bccf8ea9af801013e78aa71a24a864f47ebe9880`.
- Build-pinned data release: `cb3e5eb4dc751458873c410c1f5631f9d34336279d66045e5ea21f9683daa988`. Served-byte hashes are verified by the browser, and source/spec/lock/pipeline inputs are recorded in `site/data/release.json`.
- Preserved original supplied spec: [`../source/SPEC-v1-2026-10-17.md`](../source/SPEC-v1-2026-10-17.md), SHA-256 `1e42772fc4062d47c6b538e0c38a55ebd90257fe17a7f2d887251a856bde39d4`. Its Git blob exactly equals the original reconstruction-baseline `SPEC.md`.
- Canonical amended `SPEC.md`, SHA-256 `94394708ff96f381411270158a23e090b974ec76b54b3d3318cba4b92ac42099`. The amendment register, R1–R15 and §18 document drift from v1, practical integration choices and the owner's GitHub Pages test authorization. Cloudflare production choice and owner O1–O6 defaults are unchanged.

Source tasks were merged through separate PRs #1–#9; no agent push went directly to main. Original repository/prototype history was not recovered; this remains a reconstructed project.

## Real verification outcomes — separate from acceptance

| Check | Actual outcome |
|---|---|
| Fresh pinned `npm ci` | Installs successfully; audit reported 0 vulnerabilities; upstream deprecation warnings remain |
| Vitest unit/pipeline tests | 25 passed |
| Real map ID/topology/size/render/reproducibility | 8 passed, 0 skipped; two rebuilds identical |
| Deterministic release inventory | 1 passed |
| Travel diagnostic unit tests | 7 passed; this is NOT national routing or metric acceptance |
| Static-content tests | 14 passed including 320px/400px light/dark browser variants |
| Production project-prefix Playwright | 7 passed, including missing-data and stale-byte failure handling |
| Tax 500 on-grid cases | 500 pass individual `max(CHF 2, 0.1%)` bounds; max absolute error CHF 6.302668, not a blanket CHF 2 result |
| Tax 300 off-grid cases | **FAIL: 119 exceed CHF 10; max error CHF 46.792. Runner exits 1.** |
| Historical engine scenarios | 29 reproduced and table differences within CHF 10; NOT official ESTV reference verification |
| Exact r5py commute metric | **FAIL** on explicitly synthetic diagnostic GTFS; nationwide build remains blocked |
| GitHub feature CI | **BLOCKED**: OAuth credential lacks `workflow` scope; upload rejected. No unit/feature CI-green claim. GitHub's built-in Pages publishing job is a separate hosting job |

## What remains unfinished

1. Correct the tax off-grid accuracy issue without weakening the CHF 10 contract; obtain real official ESTV comparisons. All unverified tax recommendations stay withheld.
2. Resolve exact routing metric semantics/capacity, freeze authentic national transit/walking/population sources, generate real travel files and complete the 30 SBB checks. No fake travel times are shipped.
3. Enable project CI only after the owner grants the needed credential permission, through a reviewed workflow PR. Current preview publishing needs no broader token.
4. Supply/approve operator contact and legal texts, owner golden results, real-phone acceptance and all production gates. Existing public content pages are drafts.
5. Resolve commercial rights before commercial use. The current credited, adapted BFS map is used only for this non-commercial test; STAC/geocat commercial-permission discrepancy stays documented.
6. Complete Cloudflare-specific headers/cache/coherence, production performance/accessibility and launch review. GitHub Pages does not apply `_headers`; observed host cache policy is `max-age=600`.

The preview is ready for UI feedback, not financial or commuting decisions. Hosting success does not convert failed/missing data gates into passes.
