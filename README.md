# Steuerpendler

**Non-production, non-commercial test preview. Estimates only, no tax advice.**

Pick the town you work in (one of 19 German-speaking cantonal capitals) and how long you are willing to
commute by public transport; get the Gemeinden within that commute ranked by total yearly income tax
(Bund + Kanton + Gemeinde + Kirche), on a map and as a list. Static site, all calculations in the browser,
no backend, cookies or analytics.

- Preview: https://johndev13.github.io/steuerpendler/
- Current state, gates and open decisions: [`docs/STATUS.md`](docs/STATUS.md)
- Requirements: [`SPEC.md`](SPEC.md)

## How the numbers are made

**Tax.** The vendored open-source engine [`swisstaxcalculator`](https://github.com/devbrains-com/swisstaxcalculator)
with ESTV 2026 data and 19 recorded patches (`vendor/swisstaxcalculator/STEUERPENDLER-PATCHES.md`) generates
one profile per civil status and number of children. The browser evaluates the tariffs exactly between the
CHF 1,000 grid rows. Assumptions: gross employment income, age 35, no wealth, ESTV standard deductions,
married couples with one income. Checked against 29 frozen cases from the official ESTV calculator:
21 match within tolerance; cantons more than 5 % off are withheld (currently VS, VD, GE, JU).

**Commute.** The site currently uses the hash-pinned observed-positive export; unlisted
Gemeinden remain unknown. `scripts/travel/matrix.py` is an *experimental*, inactive candidate
Connection Scan for an official GTFS feed. It has not been run and independently audited on a
real national feed; frequency trips, transfer precedence and origin coverage remain unresolved.
Direct-only journeys are scanned separately. Its presence cannot override the public preview
while `availability.travel=false`, and it is not proof of globally fastest routes. External
walking access to the first stop remains unmeasured (zero by owner interim assumption).

**Map.** Bundesamt für Statistik (BFS), GEOSTAT — Generalisierte Grenzen G1, 01.01.2026, via
`swiss-maps@4.7.0`; attributed non-commercial use (`docs/map/publication-assessment.md`).

## Run locally

Node 22.23.2 or newer, Python 3.11 or newer.

```sh
npm ci
npm run dev                 # local site
npm test                    # unit tests (includes tax regression vs engine and ESTV ratchet)
npm run tax:test            # SPEC 7.1 numeric gates
npm run tax:official        # 29 official ESTV cases
python3 -m unittest discover -s tests/travel
npx playwright install --with-deps chromium && npm run test:e2e
PAGES_BASE=/steuerpendler/ npm run build
```

Regenerate data: `npm run tax:build` (tax tables), `npm run map:build` (map), and for travel
`python3 scripts/travel/run_matrix.py --gtfs <feed.zip> --date 2026-10-27` or the **Build travel matrix**
workflow. `npm run build` regenerates the release manifest (`site/data/release.json`), which CI checks is
committed.

## Contributing

One topic per branch, PRs against `main` only, squash merge. CI (`.github/workflows/ci.yml`) must be green.
Keep data and its schema in sync with `SPEC.md`. Never invent ESTV or SBB reference values; add evidence as
frozen captures with a test, not as prose.

## Sources and rights

Tax: ESTV via swisstaxcalculator (MIT). Timetable: opentransportdata.swiss. Footpaths: © OpenStreetMap
contributors (ODbL). Boundaries: BFS GEOSTAT. Notices are served under `credits/`. GitHub Pages logs visitor
IP addresses; see the draft Datenschutz page. Operator contact, legal review, commercial map rights and a
production launch are pending.
