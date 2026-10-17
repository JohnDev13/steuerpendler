# Steuerpendler — Build Spec v1

Status: 17 Oct 2026 · Owner: John · Tax year: 2026

## 0. How to use this file (agents read first)

- This file is the single source of truth. Read it fully before starting any task.
- Tasks are in section 10. Each has an ID, dependencies, outputs and acceptance tests. A task is done only when all of its acceptance tests pass and CI is green.
- Data formats in section 6 are contracts between tasks. Do not change them without updating this file in the same pull request.
- Items in section 14 (open decisions) belong to the owner. Use the stated default, and do not decide them yourself.
- Rules:
  - One branch and one pull request per task. Never push to `main` directly.
  - No backend, database, user accounts, cookies or tracking in v1. The site is static files only.
  - Do not edit `vendor/swisstaxcalculator/` except for patches recorded in its `STEUERPENDLER-PATCHES.md`.
  - Never commit secrets. Use GitHub Actions secrets.
  - Never invent reference values (tax amounts, SBB travel times). Look them up in the official source or leave the cell empty and report it.

## 1. Goal

A website where a person picks the town they work in and how long they are willing to commute by public transport, and gets every Gemeinde within that commute ranked by their total yearly income tax (Bund + Kanton + Gemeinde + Kirche), on a map and as a list.

Example: "I work in Zürich and accept at most 25 minutes by train or bus, plus up to 10 minutes' walk to the station. Where do I pay the least tax?"

## 2. Scope

**In v1**
- Workplace: any of the 2,110 Swiss Gemeinden.
- Commute filter: max travel time, max walk to the station, and a toggle that counts the walk inside the travel time.
- Tax profile: gross income, single or married, 0–3+ children, church (none, reformed, catholic).
- Results: ranked list, Switzerland map coloured by tax, and a breakdown per Gemeinde.
- Real 2026 tax data and the real Swiss timetable.
- Hosted on Cloudflare Pages, rebuilt from GitHub.

**Not in v1:** rent, health insurance premiums, wealth tax, two-earner couples (see O1), door-to-door routing, user accounts, saved searches, ads or payments.

## 3. Decisions already made (do not revisit)

| Topic | Decision |
| --- | --- |
| Hosting | Cloudflare Pages, deployed from the GitHub repo. Static files only. |
| Data | Precomputed once a year and committed to the repo as JSON. All filtering and tax maths run in the browser. |
| Tax source | ESTV 2026 tariffs and Steuerfüsse via the vendored open-source engine `swisstaxcalculator` (MIT), with three documented patches. |
| Travel source | Swiss GTFS timetable (opentransportdata.swiss) + OpenStreetMap footpaths, routed with r5py. |
| Map | Gemeinde boundaries 2026 from the `swiss-maps` npm package (4.7.0), drawn with d3-geo. No tile server, no map API key. |
| Frontend | Vite + TypeScript, vanilla DOM (no UI framework), d3-geo and topojson-client. Unit tests: Vitest. E2E tests: Playwright. |
| Lovable / Supabase | Not used. |

## 4. Current state

The repo (`steuerpendler/`, one commit, not yet on GitHub) contains:

- `vendor/swisstaxcalculator/`: tax engine + 2026 data, with these patches (documented in `STEUERPENDLER-PATCHES.md`):
  1. Exports internal functions.
  2. Federal per-child deduction set to CHF 263, the 2025/2026 value (was 251), and federal tax floored at 0.
  3. Fribourg: no crash above the top tariff step.
- `scripts/tax/build.ts`: writes `site/data/tax-2026-{s|m}-{0..3}.json` and `site/data/gemeinden-2026.json`.
- `scripts/tax/selftest.ts` (`npm run tax:test`): totals rebuilt from the tables match the full engine (500 cases on the CHF 1,000 grid: max error CHF 5.19, within tolerance; 300 cases between steps: max error CHF 9.38).
- `scripts/tax/reference.ts`: prints the engine totals in section 11.1.
- `docs/prototype.html`: clickable UX prototype with **sample data**. Use it as the reference for layout and interactions only, never for numbers.

## 5. Architecture

```
ESTV data (vendored) ──► scripts/tax ──────► site/data/tax-*.json, gemeinden-*.json ─┐
GTFS + OSM + STATPOP ──► scripts/travel ───► site/data/travel/**                    ├─► Vite build ─► dist/ ─► Cloudflare Pages
swiss-maps 4.7.0 ──────► scripts/map ──────► site/data/map/switzerland-2026.json ────┘
                         (GitHub Actions, manual run, yearly)        (CI on every push; Pages deploys main)
```

Target repo layout:

```
SPEC.md  README.md  package.json  vite.config.ts  index.html
src/                 # frontend (TypeScript)
  main.ts  state.ts  tax.ts  filter.ts  map.ts  list.ts  detail.ts  format.ts  strings.ts  styles.css
  *.test.ts          # Vitest unit tests next to the code
site/data/           # generated data, committed (Vite copies it to dist/data via publicDir)
  tax-2026-s-0.json … tax-2026-m-3.json  gemeinden-2026.json
  travel/meta.json  travel/access.json  travel/to/<bfs>.json
  map/switzerland-2026.json
scripts/tax/  scripts/travel/  scripts/map/
tests/e2e/           # Playwright
pages/               # impressum.html  datenschutz.html  methode.html
vendor/swisstaxcalculator/
docs/prototype.html
.github/workflows/ci.yml  build-tax.yml  build-travel.yml
```

## 6. Data contracts

All JSON is UTF-8 and minified. BFS ids are Gemeinde numbers as of 1 Jan 2026.

### 6.1 Tax profile files: `site/data/tax-2026-{civ}-{kids}.json` (exists)

`civ` is `s` (single) or `m` (married, one earner); `kids` is 0–3 (3 means "3 or more").

```json
{
  "meta": { "year": 2026, "incomes": { "from": 40000, "step": 1000, "count": 461 }, "...": "..." },
  "cantons": { "ZH": [[bund, base, personal], ...461 rows], "BE": [...], ... 26 cantons }
}
```

Row `i` is for gross income `from + i × step`. `bund` is the Bundessteuer in CHF, `base` the cantonal simple tax ("einfache Steuer", before Steuerfüsse), and `personal` the Personal-/Kopfsteuer in CHF.

### 6.2 Gemeinden: `site/data/gemeinden-2026.json` (exists)

```json
{ "meta": {...}, "gemeinden": { "261": ["Zürich", "ZH", 95, 119, 10, 10], ... 2110 entries } }
```

Columns: name, canton, rateCanton, rateGemeinde, rateReformed, rateCatholic. Rates are % of `base`.

### 6.3 Travel metadata: `site/data/travel/meta.json` (task T3)

```json
{ "timetable": "2027", "referenceDate": "2027-01-12", "window": "06:30-08:30", "maxMinutes": 60,
  "gtfsFile": "<name of zip used>", "built": "<ISO date>" }
```

### 6.4 Access: `site/data/travel/access.json` (task T3)

```json
{ "gemeinden": { "261": ["8503000", "Zürich HB", 6], "9999": null, ... } }
```

Value: main stop id (parent station), main stop name, walk minutes from the population centre. `null` means no usable stop within 2 km.

### 6.5 Travel times per workplace: `site/data/travel/to/<bfs>.json` (task T3)

```json
{ "to": 261, "rows": [[261, 0], [3, 7], [191, 9], ...] }
```

Each row is `[homeBfs, minutes]`, sorted by minutes. Only rows ≤ 60 minutes are kept. The workplace itself is always included with 0. One file per Gemeinde that has a main stop.

### 6.6 Map: `site/data/map/switzerland-2026.json` (task T2)

TopoJSON with these objects:
- `gemeinden`: one feature per polygon, `id` = BFS id, no properties.
- `cantons`: canton polygons, for borders.
- `lakes`

Coordinates must be WGS84 (lon/lat) or pre-projected; whichever you choose, document it in `meta`. Size: ≤ 1.5 MB raw, ≤ 500 KB gzip.

## 7. Tax rules (frontend must implement exactly this)

For workplace-independent tax profile `(civ, kids, income, church)` and Gemeinde `g`:

```
x       = clamp((income − 40000) / 1000, 0, 460)
i       = min(floor(x), 459);  t = x − i
row     = cantons[g.canton][i] + (cantons[g.canton][i+1] − cantons[g.canton][i]) × t     (element-wise)
rateCh  = church == reformed ? g.rateReformed : church == catholic ? g.rateCatholic : 0
kanton  = row.base × g.rateCanton / 100
gemeinde= row.base × g.rateGemeinde / 100
kirche  = row.base × rateCh / 100
total   = row.bund + kanton + gemeinde + kirche + row.personal
```

Fixed assumptions, shown on the page: gross employment income, age 35, no wealth, standard deductions, and married couples have one income.

Display totals rounded to CHF 10. Income input: CHF 40,000–500,000. Below or above that range, clamp the value and show a note.

## 8. Travel-time rules (task T3 must implement exactly this)

- **Reference day:** a normal Tuesday inside the current timetable period, not a holiday or school-holiday week. Record it in `meta.json`.
- **Main stop of a Gemeinde:** among stops inside the Gemeinde polygon, aggregated by parent station, the one with the most departures 06:00–09:00 on the reference day. If no stop is inside, take the nearest stop with departures within 2 km of the population centre; otherwise the Gemeinde has no main stop (`null`). Manual fixes go in `scripts/travel/main-stop-overrides.csv` (`bfs,stop_id,reason`).
- **Population centre:** the population-weighted centre from BFS STATPOP hectare data. If STATPOP is not available, use the polygon's representative point and note it in `meta.json`.
- **Walk minutes:** walking time over OSM footpaths from the population centre to the main stop, rounded up, capped at 60.
- **Travel minutes:** from the home main stop to the workplace main stop, departing any minute 06:30–08:30. Take the minimum over the window (r5py `percentiles=[1]` or equivalent; check that it equals the fastest connection, not including the wait at the first stop). Transfers and transfer walks are included.
- Drop pairs over 60 minutes.

Frontend filter:

```
reachable(g) = access[g] != null
            && rows has g
            && walk(g) <= maxWalk
            && (countWalk ? minutes(g) + walk(g) : minutes(g)) <= maxTime
```

## 9. UI spec

Use `docs/prototype.html` as the reference for layout and interaction. Its data is fake.

**Controls**

| Control | Range | Default |
| --- | --- | --- |
| Workplace | search box over all Gemeinden, matching by name, accent-insensitive | Zürich |
| Max travel time | 5–60 min, step 1 | 25 |
| Max walk to station | 0–15 min, step 1 | 10 |
| Count the walk in the travel time | toggle | off |
| Gross income | slider CHF 40,000–500,000, step 1,000, plus a number field | 120,000 |
| Civil status | single / married | single |
| Children | 0 / 1 / 2 / 3+ | 0 |
| Church | none / reformed / catholic | none |

**Results**
- **Summary line:** number of Gemeinden reachable; the cheapest with its total.
- **Ranked list:** rank, name, canton, travel minutes, walk minutes, total CHF/year, and the difference to the workplace Gemeinde. Sort by total, then minutes, then name.
- **Map** of all of Switzerland:
  - Reachable Gemeinden coloured in 5 equal-count groups from cheapest (green) to most expensive (red); all others grey.
  - Top 10 numbered; workplace marked.
  - Zoom to the reachable area with padding.
  - Clicking a Gemeinde selects it.
- **Detail panel:** Bundes-, Kantons-, Gemeinde-, Kirchen- and Personalsteuer; the Gemeinde rate in %; main stop name; minutes + walk; rank. It also works for unreachable Gemeinden, with the label "out of reach".
- **Empty state:** "No Gemeinde in reach. Allow more time or walking."
- **Footer:** tax year, the assumptions, "Estimate, not tax advice", data sources, and links to Impressum / Datenschutz / Methode.

**Non-functional**
- Works at 400 px width without horizontal scroll.
- Keyboard-usable; all controls labelled.
- Light and dark themes.
- First load ≤ 1 MB gzip in total.
- Any control change updates the list and map in < 100 ms on a mid-range phone.
- No cookies; no third-party requests except the font host, if one is used.
- Money format: `CHF 12'345`.
- Language: see O2.

## 10. Tasks

### T1 — Repo on GitHub, CI skeleton
Depends on the owner creating the repo (O4).
1. Push the existing repo.
2. Add `ci.yml`: on every push and PR, run `npm ci`, `npm run tax:test`, `npm test` (Vitest), `npm run build`, and Playwright e2e.
3. Add `build-tax.yml`: manual run that executes `npm run tax:build` and `npm run tax:test`, and opens a PR with the changed data.

**Accept:** CI is green on `main`; the tax workflow can run by hand and produces no diff on unchanged data.

### T2 — Map data
1. `scripts/map/build.*` reads `swiss-maps@4.7.0` (2026 municipalities, cantons, lakes; LV95 shapefiles in the package).
2. Simplify and write §6.6.

**Accept (scripted, `npm run map:test`):**
- Every one of the 2,110 BFS ids in `gemeinden-2026.json` has exactly one feature.
- The 3 extra polygons (2391, 5391, 5394) are not Gemeinden. They are kept and drawn grey, labelled "no data".
- File size within §6.6.
- A rendered PNG of the map looks like Switzerland, with no slivers or gaps between neighbours (attach it to the PR).

### T3 — Travel-time data
Depends on T1.
1. `scripts/travel/build.py`, pinning versions in `requirements.txt` (r5py, geopandas, pandas).
2. Download inputs:
   - the GTFS zip for the current timetable from opentransportdata.swiss / opendata.swiss;
   - the Switzerland OSM extract (Geofabrik);
   - BFS STATPOP (hectares);
   - the swiss-maps 2026 polygons.
3. Implement §8 and write §6.3–6.5.
4. Add `build-travel.yml`: manual run that builds the data and opens a PR. If memory runs out on the runner, see R3.
5. Add `npm run travel:test` (or `pytest`) with the checks below.

**Accept (scripted):**
- ≥ 95% of Gemeinden have a main stop; the list of those without one is attached to the PR.
- These main stops are correct: Zürich → Zürich HB; Bern → Bern; Basel → Basel SBB; Genève → Genève (Cornavin); Lausanne → Lausanne; Luzern → Luzern; Winterthur → Winterthur; St. Gallen → St. Gallen; Lugano → Lugano. Fix wrong ones via overrides.
- Every `to/<bfs>.json` contains itself with 0, rows ≤ 60, sorted.
- Plausibility: no pair is faster than straight-line distance at 150 km/h; flag any pair faster than 100 km/h for review.
- Total size of `travel/` ≤ 25 MB; each file ≤ 100 KB.

**Accept (manual, section 11.2):** 30 pairs within 3 minutes of the SBB timetable.

### T4 — Tax module
In `src/tax.ts`:
1. Load `gemeinden-2026.json` once and the profile file for the chosen civil status and children on demand; cache it.
2. Implement §7.

**Accept (Vitest):**
- For the 29 cases in §11.1, the module equals the engine total within CHF 10.
- Interpolation at a grid point equals the row exactly.
- Clamping below CHF 40,000 and above CHF 500,000.
- Church none/reformed/catholic picks the right rate.

### T5 — Filter and ranking
In `src/filter.ts`, implement the §8 filter and the §9 sorting and colour groups.

**Accept (Vitest):**
- The walk toggle changes membership as specified.
- `null` access is excluded.
- The workplace is always included when the walk filter allows it.
- Ties are sorted by minutes, then name.
- 5 colour groups of equal size (±1).
- The empty set returns the empty state.

### T6 — App UI
Depends on T2, T4 and T5; can use T3's file format with stub files until T3 lands.
1. Build §9.
2. Reuse the prototype's look, adapted to all of Switzerland.
3. Put all UI text in `src/strings.ts`.

**Accept (Playwright, `tests/e2e`):**
- **Default state:** list count > 0, first row = the cheapest, map drawn, no console errors.
- **Golden scenario:** Zürich, 25 min, walk 10, single, 120,000, no church. The top 10 matches a snapshot that the owner approved once (store it in `tests/e2e/golden-zurich.json`).
- Changing each control changes the result as expected: lower time → fewer rows; married + 2 children → lower totals; reformed church → higher totals.
- Switching the workplace to Bern shows Bern-area Gemeinden.
- 400 px viewport: no horizontal scroll, and all controls are reachable.
- Keyboard: you can tab to and operate every control.
- Missing data file: a readable error message appears, not a blank page.

### T7 — Content pages
1. `pages/impressum.html` (owner data, O5).
2. `pages/datenschutz.html` under the Swiss Data Protection Act: no cookies, hosting by Cloudflare, analytics per O6.
3. `pages/methode.html`: explain §7 and §8 in plain words, the assumptions, the data year, and the sources with licences/credits (§16).

**Accept:** the owner has reviewed and approved the texts; the links work from the footer.

### T8 — Deploy
Depends on T1, T6 and T7.
1. Create a Cloudflare Pages project linked to the repo: build command `npm run build`, output `dist`, production branch `main`, with previews for PRs.
2. Connect the domain (O3).
3. Analytics per O6.

**Accept:**
- The production URL serves the site over https.
- PR previews work.
- The Lighthouse mobile run (performance, accessibility, best practices) scores ≥ 90 each.
- Response headers include `Cache-Control` for `/data/*`, at least 1 day with revalidation.

### T9 — Official verification and go/no-go
Depends on T3 and T6.
1. Fill in the empty columns of §11.1 from the official ESTV calculator and §11.2 from the SBB timetable.
2. Commit them as `tests/reference/estv-2026.csv` and `tests/reference/sbb-pairs.csv`.

**Accept:**
- Every tax case is within CHF 5 or 0.1% (whichever is larger) of ESTV.
- Every travel pair is within 3 minutes of SBB.
- **Any canton that fails is hidden**: its Gemeinden are greyed out as "data under review" through a list in `src/config.ts`, until the engine is fixed and the case passes.

## 11. Reference values

### 11.1 Tax: engine totals (2026, gross employment income, no wealth)

The "Engine" column comes from `scripts/tax/reference.ts`. "ESTV" is to be filled from https://swisstaxcalculator.estv.admin.ch (T9). Married = one earner (partner income 0).

| Gemeinde | Kt | BFS | Civil | Kids | Income | Church | Engine CHF | ESTV CHF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Zürich | ZH | 261 | single | 0 | 120,000 | none | 17,407 | |
| Winterthur | ZH | 230 | married | 2 | 150,000 | reformed | 14,277 | |
| Zug | ZG | 1711 | single | 0 | 120,000 | none | 9,467 | |
| Freienbach | SZ | 1322 | single | 0 | 120,000 | none | 9,270 | |
| Baden | AG | 4021 | married | 0 | 100,000 | catholic | 8,087 | |
| Aarau | AG | 4001 | single | 1 | 80,000 | none | 4,939 | |
| Bern | BE | 351 | single | 0 | 90,000 | reformed | 15,860 | |
| Basel | BS | 2701 | married | 2 | 180,000 | none | 24,336 | |
| Riehen | BS | 2703 | single | 0 | 250,000 | none | 55,739 | |
| Luzern | LU | 1061 | married | 1 | 120,000 | catholic | 10,333 | |
| St. Gallen | SG | 3203 | single | 0 | 70,000 | catholic | 10,144 | |
| Lausanne | VD | 5586 | married | 2 | 140,000 | none | 23,651 | |
| Genève | GE | 6621 | single | 0 | 150,000 | none | 35,726 | |
| Lugano | TI | 5192 | married | 0 | 200,000 | catholic | 36,109 | |
| Fribourg | FR | 2196 | married | 0 | 300,000 | none | 78,815 | |
| Chur | GR | 3901 | single | 3 | 60,000 | reformed | 1,317 | |
| Sion | VS | 6266 | married | 3 | 110,000 | catholic | 23,933 | |
| Neuchâtel | NE | 6458 | single | 0 | 100,000 | none | 19,232 | |
| Schaffhausen | SH | 2939 | married | 0 | 400,000 | reformed | 93,308 | |
| Frauenfeld | TG | 4566 | single | 2 | 95,000 | none | 7,599 | |
| Appenzell | AI | 3101 | single | 0 | 100,000 | catholic | 12,344 | |
| Herisau | AR | 3001 | married | 2 | 120,000 | none | 13,641 | |
| Liestal | BL | 2829 | single | 0 | 100,000 | none | 17,901 | |
| Glarus | GL | 1632 | married | 1 | 90,000 | reformed | 6,130 | |
| Delémont | JU | 6711 | single | 0 | 80,000 | catholic | 12,403 | |
| Stans | NW | 1509 | married | 0 | 160,000 | none | 20,351 | |
| Sarnen | OW | 1407 | single | 0 | 100,000 | none | 13,284 | |
| Solothurn | SO | 2601 | married | 2 | 130,000 | reformed | 13,827 | |
| Altdorf (UR) | UR | 1201 | single | 0 | 75,000 | catholic | 10,892 | |

Check first: **Sion (VS)** looks too high. Kantons- plus Gemeindesteuer come to about CHF 23,600 on a taxable income of CHF 85,324, which is far above what Valais families usually pay. Treat VS as suspect until the ESTV check passes (see R1). Fribourg at CHF 300,000 tests patch 3.

### 11.2 Travel: pairs to check against the SBB timetable

Fastest connection between the two main stops, departing a Tuesday 06:30–08:30. Fill the "SBB min" column from sbb.ch (T9).

| # | From | To | SBB min | Ours min |
| --- | --- | --- | --- | --- |
| 1 | Uster | Zürich | | |
| 2 | Winterthur | Zürich | | |
| 3 | Zug | Zürich | | |
| 4 | Freienbach | Zürich | | |
| 5 | Wollerau | Zürich | | |
| 6 | Baden | Zürich | | |
| 7 | Kilchberg (ZH) | Zürich | | |
| 8 | Dübendorf | Zürich | | |
| 9 | Wetzikon (ZH) | Zürich | | |
| 10 | Affoltern am Albis | Zürich | | |
| 11 | Maur (bus) | Zürich | | |
| 12 | Stallikon (bus) | Zürich | | |
| 13 | Baar | Zug | | |
| 14 | Cham | Zug | | |
| 15 | Thun | Bern | | |
| 16 | Köniz | Bern | | |
| 17 | Burgdorf | Bern | | |
| 18 | Fribourg | Bern | | |
| 19 | Liestal | Basel | | |
| 20 | Riehen | Basel | | |
| 21 | Rheinfelden | Basel | | |
| 22 | Kriens | Luzern | | |
| 23 | Sursee | Luzern | | |
| 24 | Morges | Lausanne | | |
| 25 | Vevey | Lausanne | | |
| 26 | Nyon | Genève | | |
| 27 | Carouge (GE) | Genève | | |
| 28 | Gossau (SG) | St. Gallen | | |
| 29 | Bellinzona | Lugano | | |
| 30 | Olten | Aarau | | |

## 12. Testing summary

| Layer | Command / where | Runs in CI | Gate |
| --- | --- | --- | --- |
| Tax tables vs engine | `npm run tax:test` | yes | 500 on-grid cases within CHF 2 / 0.01% |
| Map data | `npm run map:test` | yes | §T2 |
| Travel data | `npm run travel:test` | yes | §T3 scripted checks |
| Unit | `npm test` (Vitest) | yes | §T4, §T5 |
| E2E | `npx playwright test` | yes | §T6, incl. golden snapshot and 400 px |
| Official tax | ESTV calculator, `tests/reference/estv-2026.csv` | no (manual, yearly) | §T9 |
| Official travel | SBB timetable, `tests/reference/sbb-pairs.csv` | no (manual, yearly) | §T9 |
| Production | Lighthouse mobile on the live URL | no | §T8 |

## 13. Launch checklist

- [ ] T1–T9 done, CI green on `main`
- [ ] All 29 ESTV cases pass, or failing cantons hidden
- [ ] All 30 SBB pairs pass
- [ ] Owner approved the golden Zürich top 10
- [ ] Impressum, Datenschutz, Methode live and approved
- [ ] Disclaimer and assumptions visible next to the results
- [ ] Source credits in the footer
- [ ] Domain live over https
- [ ] Tested on a real iPhone and Android phone

## 14. Open decisions (owner)

| ID | Question | Default until decided |
| --- | --- | --- |
| O1 | Married couples: one earner only, or add a second income? Needs a new tax profile dimension. | One earner |
| O2 | Languages: German only, or also French/English? | German UI; all text in `src/strings.ts` so more languages can be added later |
| O3 | Domain name | none (use `*.pages.dev`) |
| O4 | GitHub repo: public or private? Public gets 16 GB runners (needed for T3, see R3); the data is public anyway. | public |
| O5 | Impressum: name, address, email | placeholder, blocks launch |
| O6 | Analytics: none, or a cookie-free tool (which one)? | none |

## 15. Risks and known issues

- **R1 Valais suspect.** See §11.1. The engine may mishandle VS (e.g., family rebates). Mitigation: T9 hides failing cantons.
- **R2 Unofficial engine.** It is maintained by a small open-source project and recomputes the ESTV calculator. It already needed two fixes. Every year: re-run all 29 official checks.
- **R3 Memory.** GitHub runners for private repos have 2 vCPU / 8 GB, public ones 4 vCPU / 16 GB. Routing all of Switzerland with r5py may need more than 8 GB (estimate, unverified). Options: public repo, a larger paid runner, or run T3 once on a 16 GB+ machine and commit the output. Jobs on GitHub-hosted runners stop after 6 hours.
- **R4 GTFS route types.** The Swiss feed uses extended route types. If r5 rejects them, map them to basic GTFS types in a preprocessing step (unverified).
- **R5 Main-stop rule.** Cities with several stations (Zürich HB vs Oerlikon) are reduced to one stop. Accepted for v1; fix individual cases via overrides.
- **R6 Gemeinde mergers on 1 Jan 2027.** Tax data uses 2026 ids. At the yearly update, switch tax, map and travel to the same year together.
- **R7 Fribourg patch.** Applying the top rate above the table is an assumption. The Fribourg case in §11.1 verifies it.

## 16. Sources and credits (show in footer and Methode page)

- Tax tariffs and Steuerfüsse: ESTV (Eidgenössische Steuerverwaltung), via swisstaxcalculator by devbrains-com (MIT licence).
- Timetable: opentransportdata.swiss / opendata.swiss. Terms require naming the source.
- Footpaths: © OpenStreetMap contributors (ODbL).
- Boundaries: swisstopo, via the swiss-maps package. Check the package's licence and credit line before launch.
- Population: BFS STATPOP. Name the source.

## 17. Yearly maintenance

| When | Do |
| --- | --- |
| December (timetable change) | Run `build-travel.yml` on the new GTFS file; repeat the 30 SBB checks |
| When the new tax-year data is out | Update the vendored data (`importdata <year> --download` in the upstream project), re-apply the patches, run `build-tax.yml`; repeat the 29 ESTV checks; update the tax year in the UI |
| January | Gemeinde mergers: update the map to the new swiss-maps year, then rebuild tax and travel on the same ids |
