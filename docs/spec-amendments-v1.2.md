# Scope clarification v1.2 — 17 October 2026

Canonical specification: `SPEC.md` v1.2, especially §19.
Previous complete specification: `docs/source/SPEC-v1.1-2026-10-17.md`.

## Owner correction

Only workplace/commute destinations are narrowed to German-speaking cantonal capitals. ALL 2,110 Swiss Gemeinden remain potential residences and tax candidates, across all 26 cantons, including non-capitals and neighbouring cantons. The earlier capital-only residential direction was incorrect and is not part of this release.

Canonical workplace registry: `src/destinations.ts`. Names/BFS/canton identities are checked against the authentic 2026 municipality file. The initial 19 destinations include Bern and Chur (bilingual/multilingual cantons are not excluded) and Herisau as the AR government seat. This is a selected workplace list, not a claim that all included cantons are officially monolingual.

## Aarau example

- Destination: Aarau, BFS 4001.
- Origins/residences: every municipality; do not filter by canton or capital status.
- Transit limit: 20 minutes.
- Station-access pedestrian-route limit: 15 minutes.
- With count-walk off, both limits apply independently; with it on, access also counts within the transit budget.
- This is an actual timetable/access catchment, not a circle drawn around Aarau.

Existing route modes, exact first-boarding/transfer semantics, origin-centre definitions and official accuracy/approval gates are unchanged. This example is a requested scenario, not evidence that its real routing/tax outputs have passed acceptance.

## Implementation and drift controls

- Workplace search has a dedicated 19-destination subset.
- Tax calculation, filters, map and residential search receive the complete municipality authority, not that subset.
- Residential lookup supports Lenzburg, Olten and Genève while the workplace stays Aarau; browser regression coverage exercises that distinction.
- Map navigation preserves the full geographic coverage and selected workplace.
- Release manifests pin the workplace-registry source alongside existing data/build/spec inputs.
- Tax files and municipality authority are not replaced by a capital-only tax snapshot. A capital-to-capital timetable sample cannot stand in for all-origin routing.

## Unchanged blockers

The existing off-grid tax gate remains failed; real all-origin→capital timetable and station-access data remain incomplete. Official checks, approvals and production launch are not granted by scope correction, navigation tests or GitHub access. The preview continues to withhold unverified tax amounts/rankings.
