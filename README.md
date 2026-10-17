# Steuerpendler

**Non-production, non-commercial test preview. Not a finished tax/commute service.**

- Preview address: https://johndev13.github.io/steuerpendler/ — verified live, not just built locally. [Deployment evidence, source revisions and known blockers](docs/deployment/Deployment-Report-v0.1.md).
- Source specification: [`SPEC.md`](SPEC.md), with preserved supplied-v1 lineage and amendment register.
- Original repository/prototype were not recovered. This is a reconstruction from real pinned upstream sources.

## What you can test

German labelled controls; a capital-only workplace selector (19 destinations); a separate accent-insensitive residential search across all 2,110 genuine 2026 Gemeinden in all 26 cantons; the actual Switzerland map with zoom, pan, touch pinch and reset; municipality selection, keyboard controls, responsive layout, light/dark themes and static content pages. Only destinations are narrowed: tax candidates and access origins remain all Gemeinden, including neighbouring cantons. See [scope clarification v1.2](docs/spec-amendments-v1.2.md). Tax-profile JSON loads on demand and validates its pinned served-byte hash. All calculations are client-side; no backend, accounts, cookies or analytics.

**Tax totals, cheapest recommendations and commute rankings are intentionally withheld.** The on-grid tax gate passes, but 119/300 off-grid cases exceed CHF 10 (max error CHF 46.792). All 29 historical engine scenarios reproduce, which is not official ESTV verification. Exact r5py travel-metric conformance fails; no nationwide travel data or SBB verification is claimed. See `docs/tax/` and `docs/travel/` for actual reports. These gates were not relaxed.

## Run locally

Use Node 22.23.2 or a compatible newer supported Node, and Python 3.11 for routing diagnostic unit tests.

```sh
npm ci
npm run dev
npm test
npm run map:test
npm run release:test
npm run build
npm run preview
```

The eight genuine 2026 profiles, 2,110-ID Gemeinde file and simplified map are committed under `site/data/`. Raw Swiss GTFS/OSM inputs are not committed. Tax engine source/data and all reconstructed patches retain their upstream provenance and MIT notice.

```sh
npm run tax:build
npm run tax:test       # CURRENTLY exits 1: off-grid accuracy gate genuinely fails
npm run tax:reference  # Engine/table regression only; not official ESTV acceptance
python3 -m unittest discover -s tests/travel -v
node --test tests/content/*.test.mjs
npx playwright install --with-deps chromium
npm run test:e2e
```

On a locked-down Linux host, Playwright system libraries may require a separately approved local/system installation. The repo does not silently install system dependencies.

## GitHub Pages project-path build

```sh
PAGES_BASE=/steuerpendler/ npm run build
PAGES_BASE=/steuerpendler/ npm run test:e2e
```

`PAGES_BASE` defaults to `/` for the intended Cloudflare production host. JSON URLs and navigation respect the base. `dist/` is the static deliverable; `scripts/preview-server.mjs` is a local-only verification server, never a production backend. It returns actual 404s, not an HTML-200 SPA fallback for missing data.

The original preview credential lacked `workflow`; it was refreshed on 17 October 2026 and the effective login now has that scope. Historical rejection is recorded in the v0.1 report, not treated as a permanent restriction. A workflow upload or scope alone is not CI success: source-check run results and any still-failing numerical gates must be reported separately. The test deployment continues to use built files on `gh-pages` and branch-based Pages publishing. Source changes use task PRs, never direct main pushes. Cloudflare `_headers` files do not configure GitHub Pages; production cache/launch acceptance remains pending.

## Sources, rights and privacy

Map: **Bundesamt für Statistik (BFS), GEOSTAT — Generalisierte administrative Grenzen G1, 01.01.2026**, via pinned `swiss-maps@4.7.0`. Simplified jointly with shared topology, LV95/EPSG:2056. See `docs/map/publication-assessment.md`; current official sources agree on attributed non-commercial use, but differ on commercial permissions. The preview has no advertising, payments, monetization or lead generation. Commercial clearance is not claimed. Verbatim notices are served under `credits/`.

GitHub Pages logs visitor IP addresses for security purposes. Profile/workplace filenames can disclose a selected profile/place to the host; the numeric income is not sent for server-side calculation. See the draft Datenschutz page. Operator contact, legal/content approval, official ESTV/SBB fixtures, owner golden snapshot, real-phone testing and production launch all remain pending.
