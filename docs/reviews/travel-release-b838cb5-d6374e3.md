# Travel-release review `b838cb5..d6374e3` — REQUEST CHANGES

## Scope

Reviewed commits `2f52980`, `22cc273`, `d93e594`, and `d6374e3` on `feat/verified-comparison`. The range adds structural travel-release validation, invokes it before manifest publication, tracks the validator as an input, and regenerates the two release wrappers.

## Checks

- `git diff --check b838cb5..d6374e3`: passed.
- `node --test scripts/release/build.test.mjs scripts/release/travel.test.mjs`: **7/7 passed**, 0 failed.
- Committed release audit (`/home/hermes/.hermes/cache/scratch/review-travel-release-verify.mjs`): both wrappers are byte-identical; all 10 inventoried data files and 8 of 9 inputs match committed `HEAD`; municipality authority remains **2,110 Gemeinden / 26 cantons**; workplace list remains **19** destinations.
- Release boundaries remain fail-closed: `availability.travel=false`; `content`, `estv`, `geodataLicense`, `golden`, and `sbb` approvals are all false.

## Blocking finding

`d6374e3` is not reproducible from its committed tree. Its wrappers declare `SPEC.md` as 68,505 bytes / SHA-256 `286a4b7dd138ca040a52fca19c79a565b3f3d8b830226c24a7b7e29c7ac58ed4`, while committed `HEAD:SPEC.md` is 60,805 bytes / `b63c1249507fca42005ec1f54eb3f97604912855b13f659e33aba906e32bce03`. The declared value matches the unrelated dirty working-tree amendment, so the committed release ID incorporates an uncommitted input. Regenerate the wrappers only after deliberately reconciling and committing the intended SPEC authority; do not blanket-stage the dirty parent.

## Limitations and pending gates

The validator explicitly proves structure only. It does not establish authentic GTFS/OSM/STATPOP provenance, exact-minimum routing, the separate access-walk/filter semantics, Aarau's 20-minute transit plus maximum 15-minute access-walk case, independent SBB acceptance, remote CI, CDN coherence, deployment, or publication. No travel payload is present in this release, so the positive tests use synthetic in-memory fixtures and are not route evidence.

Cloudflare production, paid compute, operator/legal/data-rights, financial release, content, ESTV, geodata, golden, and SBB approvals remain pending. No capability is approved for production by this review.
