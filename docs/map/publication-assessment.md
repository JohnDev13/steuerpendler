# Map publication assessment — swiss-maps 4.7.0 / BFS 2026

**Decision: the map can be published in the user-authorized public, genuinely non-commercial GitHub Pages testing preview, with attribution and preserved notices. Do not exclude it solely because commercial permission is unresolved.** This is an evidence-based publication recommendation, not legal advice, an official approval, or permission for a commercial launch.

Checked against live public sources on **2026-10-17 (UTC)**. No repository files changed; no deployment, commit, or remote write performed.

## 1. Actual input and authoritative provenance

Read `docs/map/README.md`, `docs/map/source-manifest.json`, `scripts/map/build.mjs`, and installed `node_modules/swiss-maps/README.md` in `/home/hermes/projects/steuerpendler`.

The project builds `site/data/map/switzerland-2026.json` from the package's **2026 municipalities, cantons and lakes shapefiles**, jointly simplified and quantized, not its ready-made TopoJSON. The manifest pins `swiss-maps@4.7.0` archive SHA-256 `5302805c536eef70e2001a8893ec66615a3e9e4ccf15eafe4a2215b50d39435e` and individual inputs; the build checks individual hashes and retains BFS/GEOSTAT provenance.

The **version-tagged upstream Makefile** identifies the precise official 2026 download, not merely a similarly named dataset:

- https://raw.githubusercontent.com/interactivethings/swiss-maps/v4.7.0/Makefile — HTTP 200. Its `downloads/2026.zip` rule fetches the official ZIP below, and its 2026 extraction rules use `Communes_G1_20260101`, `Cantons_G1_20260101` and `Lacs_G1_20260101`.
- https://data.geo.admin.ch/ch.bfs.historisierte-administrative_grenzen_g1/historisierte-administrative_grenzen_g1_2026-01-01/historisierte-administrative_grenzen_g1_2026-01-01_2056.shp.zip — HTTP 200. Downloaded and inspected in memory: those layers are present; no separate licence/readme document is included.
- Official item metadata: https://data.geo.admin.ch/api/stac/v0.9/collections/ch.bfs.historisierte-administrative_grenzen_g1/items/historisierte-administrative_grenzen_g1_2026-01-01 — HTTP 200. Actual fields: `"title":"Historized boundaries G1 20260101"`, `"datetime":"2026-01-01T00:00:00Z"`; its shapefile asset points to that same ZIP with EPSG 2056.

## 2. Current official terms — non-commercial use expressly allowed

**Federal STAC collection**, HTTP 200:

https://data.geo.admin.ch/api/stac/v0.9/collections/ch.bfs.historisierte-administrative_grenzen_g1

Actual fields identify **Federal Statistical Office FSO** with roles **producer, licensor**; title **Generalized administrative boundaries G1**; temporal extent through **2026-01-01**; collection updated **2026-08-06**. Its description says the dataset is suited to thematic maps visualizing municipal, district and cantonal statistics. The record has `"license":"proprietary"` **and an explicit `rel=license` link** to:

https://opendata.swiss/en/terms-of-use#terms_by_ask

The linked official terms page was retrieved successfully. Under **“Open use. Must provide the source. Use for commercial purposes requires permission of the data owner.”**, its actual text is:

> You may use this dataset for non-commercial purposes.
>
> You may use this dataset for commercial purposes, but you must seek prior permission from the data owner.
>
> You must provide the source (author, title and link to the dataset).

Thus `proprietary` is not a blanket ban: the linked conditions expressly permit the proposed non-commercial use. They do not restrict that permission to private/offline testing.

### Official metadata discrepancy — commercial clearance not asserted

The collection links this official geocat record, also retrieved HTTP 200:

https://www.geocat.ch/geonetwork/srv/api/records/8bf05e6c-72d6-40c0-a3c0-3641bf260a81/formatters/xml

Its title is **Generalized administrative boundaries G1**. Its actual `resourceConstraints` say:

> Opendata OPEN BY: Open use. Must provide the source.

The corresponding German anchor says **“Opendata OPEN BY: Freie Nutzung. Quellenangabe ist Pflicht.”** and links to https://opendata.swiss/en/terms-of-use#terms_by, whose text also permits commercial use. This conflicts with STAC's more restrictive `terms_by_ask` link. **Do not silently resolve this discrepancy in favour of unrestricted commercial rights.** Both records agree on non-commercial use with attribution, which is sufficient for this preview decision.

The STAC-linked BFS 2026 variable-list page was also accessible and displayed **“Open use - Must provide the source”**:
https://www.bfs.admin.ch/bfs/en/home/services/geostat/swiss-federal-statistics-geodata/spatial-divisions/generalized-boundaries-local-regional-authorities.assetdetail.36390120.html
That is a documentation asset, so it is corroboration, not independently proof of the geometry licence.

## 3. Package terms and public redistribution assessment

Installed `swiss-maps@4.7.0/README.md`, lines 79–83, says exactly:

> The code in this repository is licensed under BSD-3-Clause.
>
> The geodata is published under a non-commercial license and needs to be attributed with the source "Bundesamt für Statistik (BFS), GEOSTAT".

The same README explicitly documents loading its TopoJSON into a **web application**, including public unpkg CDN fetching. Its wording does not impose authentication, private hosting, or a no-publication condition. Even taking this package notice conservatively rather than declaring it outdated, the requested genuinely non-commercial public test fits its stated use restriction and attribution condition.

**Redistribution precision:** the quoted current official terms say “use” rather than expressly spelling out every derivative/redistribution right. This recommendation interprets their **open non-commercial use**, the official thematic-map purpose and the package's explicit web-application distribution instructions together as supporting serving the derived map and downloadable TopoJSON for this non-commercial preview. It is not a fabricated verbatim redistribution grant or a declaration that all future downstream uses are unrestricted.

## 4. Conditions before publication

1. Display a visible map/footer credit, not only JSON metadata. Suggested wording: **“Quelle: Bundesamt für Statistik (BFS), GEOSTAT — Generalisierte administrative Grenzen G1, Stand 01.01.2026; via swiss-maps 4.7.0; für diese Darstellung vereinfacht.”** Link the dataset title to the official collection above and link the conservative `terms_by_ask` conditions. This supplies author, title and dataset link while retaining the package's exact requested author credit.
2. Keep the unmodified upstream README and BSD-3-Clause notice available with distributed package-derived materials. Do not label the geodata MIT/BSD merely because code or unrelated tax data has that licence; do not replace BFS/GEOSTAT with a generic swisstopo-only credit.
3. Keep this preview genuinely non-commercial: no payments, advertising, affiliate monetization, sales or lead-generation use. A free site can still have a commercial purpose; this decision assumes the user's stated non-commercial testing purpose is accurate. Public access and lack of authentication do not themselves make it commercial.
4. Preserve the source manifest and this evidence. The repository's existing “unresolved” wording was not edited by this review. Before commercial deployment, obtain clarification/permission from BFS about the STAC/geocat conflict and the intended use; this report does not close that separate gate.

**Access limitations:** the package README's older BFS `/administrative-boundaries/…` URL returned HTTP 404; guessed map-layer legend endpoints also returned 404. The actual version-tagged download, official STAC collection/item, linked geocat XML and linked terms page all succeeded. No login or access-control bypass was used.
