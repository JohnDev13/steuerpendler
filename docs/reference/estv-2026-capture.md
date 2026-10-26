# ESTV 2026 anonymous reference capture

## Outcome

A bounded anonymous capture covers all **29 tax cases in SPEC §11.1** and all **26 cantons**. It is not the 19-workplace subset and is not the older one-income capital sample. The official source returned HTTP 200 for all 87 case operations (29 location lookups, 29 detailed calculations, 29 native-budget calculations).

The captured official amounts are in `tests/reference/estv-2026.csv`; raw request, response and metadata sidecars are under `tests/reference/estv-2026/`. `tests/reference/SHA256SUMS` binds every committed evidence file. `scripts/reference/estv_collector.py` collects and validates the catalogue using Python 3.11 standard-library code only.

## Official source and contract

- Public application: <https://swisstaxcalculator.estv.admin.ch/>
- Anonymous detailed calculation operation: `API_calculateDetailedTaxes`
- Municipality resolution: `API_searchLocation`; exact BFS and canton are matched before calculation.
- Native-default detail: `API_calculateTaxBudget`.
- Current client contract: `tests/reference/estv-2026/contract.json`, bound to the publicly served client bundle SHA-256 `3ff4786e1bc412fca341e986dfafbc03b6df69e303caec54d6fc6c7f23aff587`.
- The source page, tax-year availability and API-version responses are retained separately. The API version string is not treated as the 2026 tax-data vintage.

No credentials, authorization headers, cookies, session tokens, captcha workarounds or login bypass were used or retained. Redirects are blocked. Metadata records source/final URL, UTC retrieval time, method, content type, HTTP status, exact request and response SHA-256, and explicit `authentication: none` / `outgoing_cookies: false`.

## Frozen input mapping

Every case uses tax year 2026, gross employed income (`RevenueType1=1`), primary age 35, fortune 0 and the exact SPEC income/household/church selection. Single/married are official relationship enums 1/2. Church is official enum 4 none, 1 reformed or 2 Roman Catholic. Married cases explicitly use a same-age, same-confession partner with income/type 0. Each child is sent as `{ "Age": 10 }`.

`Budget: []` deliberately invokes ESTV's native defaults; it does **not** mean zero deductions. Each `*-budget.response.json` preserves the returned native budget, and each detailed response preserves gross-to-net contributions, taxable-income fields and deduction lines.

Child age 10, married-partner details and native-default comparability are documented proposals, not owner-approved assumptions. Therefore every CSV `comparability` and `official_gate` remains pending. Official capture is not direct shipped-frontend parity, engine parity, quarantine configuration, CI, rights approval or release approval.

## Validation and replay

Run from the repository root:

```sh
python3 -m unittest discover -s scripts/reference -v
python3 scripts/reference/estv_collector.py --offline
```

The validator checks all 29 CSV rows against SPEC and raw results; exact public location correspondence; request mapping; response arithmetic; finite components; zero wealth components; signed tax credits; all request/response hashes; sanitized metadata; all 87 status codes; and the complete checksum manifest.

A separate anonymous replay at `2026-10-17T12:09:01.924189+00:00` used the exact Zürich request. It returned HTTP 200 and exactly matched the captured 6,243 response bytes, SHA-256 `0d49b4e47aa9ed8fe63a79d10750db0c570ef48b8f66f50b14b43bd1a0f55131`, with `TotalNetTax=16346`. Its sidecars are `replay-independent.{request,response,meta}.json`. This establishes replay consistency for that request only, not stability of every future response.

## Explicit unresolved status

- `captured_cases`: 29; `cantons`: 26.
- Case HTTP status counts: `200: 87`.
- Committed HTTP captures including source/year/version/two replays: `200: 92`.
- Official frontend comparison: `pending_not_executed`.
- Input/deduction comparability: `owner_pending`.
- Engine/frontend/release fields remain empty; no local-engine output is labelled official.
