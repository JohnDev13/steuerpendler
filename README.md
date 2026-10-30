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
with ESTV 2026 data and 30 recorded patches (`vendor/swisstaxcalculator/STEUERPENDLER-PATCHES.md`) generates
one profile per civil status and number of children. The browser evaluates the tariffs exactly between the
CHF 1,000 grid rows. Assumptions: gross employment income, age 35, no wealth, ESTV standard deductions,
married couples with one income. Checked against 29 frozen cases from the official ESTV calculator:
28 match within tolerance; the remaining case (VS) fails. A broader 650-case sample passes
625 cases (all except VS) at one Gemeinde per canton; a further 3,286 ESTV results check every Gemeinde the site can
show (all 726 within 30 minutes of a workplace, four profiles each) and all match. Estimates for VS, VD and JU are withheld; JU's
parish-rate issue is not settled by its sampled cases. Neither check grants official ESTV approval.

**Commute.** `scripts/travel/matrix.py` scans every connection of the official Swiss GTFS timetable
([opentransportdata.swiss](https://opentransportdata.swiss), feed of 28 Oct 2026) for Tuesday 27 Oct 2026:
shortest time from first boarding at any stop in the Gemeinde (06:30–08:30) to arrival at the workplace
station, any number of changes (including frequency trips and trip-specific transfer rules), up to 30 minutes.
CI checks it against 30 SBB reference journeys fetched
from transport.opendata.ch (29 within 3 minutes; the 30th needs over 30 minutes on SBB too). Walking to the first
stop is not measured. Refresh with the **Travel evidence** workflow.

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

Regenerate data: `npm run tax:build` (tax tables), `npm run map:build` (map), and for travel the
**Travel evidence** workflow (or `python3 scripts/travel/run_matrix.py --gtfs <feed.zip> --date 2026-10-27`
followed by `python3 scripts/travel/fetch_reference.py --date 2026-10-27`). `npm run build` regenerates the release manifest (`site/data/release.json`), which CI checks is
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
