# Spec v1.3 amendment register — Aarau direct-positive test preview

Review date: 2026-10-22 UTC. Owner direction: publish honestly labelled indicative tax-first Aarau/20 results now; the selected 2026-10-27 service day and external residence→entrance access assumption of zero (unmeasured) are accepted. No entrance→platform penalty. This is not an independent holiday, SBB or ESTV approval.

## Byte-preserved lineage

- Source: `docs/source/SPEC-v1.2-2026-10-22.md`, SHA-256 `6d56314689f5a0fceab3688715f899be9d67898e30ec9a4ad53be537b663b20f` (identical to baseline Git `27d95e8b8cfa73b39ed3220a413e2392e8dd6d9f:SPEC.md`).
- Amended `SPEC.md` v1.3 SHA-256 `ef672ee26ed4c4370211a42ba07087cc49bd648a9b35b1c31a99e1400c3d70bc` before release-manifest regeneration. Page `pages/methode.html` SHA-256 `bb00395982778c8f63ea085e34facbe34c3bf200c86ee6593a9b132403d9ae29`.
- Source route diagnostic SHA-256 `5f9c6c8648f87ff88cf0c1dc4f158d471a6e55f57ed28cd53e649940d1d4b89e`, derived site preview JSON SHA-256 `311420191be00d7f8b6d96f81f1e8295f801a26e34deb6d49ad5ec2e7f78b988`, frozen GTFS ZIP SHA-256 `d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e`; municipality map `d118a3e8b47c8d76d4fa2587911aa088573d09a934ea484f2f1a60d573aafe14`; Gemeinde authority `0cc01b0d5f9fab1a0069394a9b89441ca4264ea0ba7e114e89157c2f748a5928`. The outside-Git diagnostic is partial `best_found_unproven`, not the final all-19 canonical file.
- From 1,754 direct observations and 212 boarding children, 24 boundary children were quarantined, 188 assigned, 59 positive stop-localities ≤30 minutes, 36 ≤20 minutes. A polygon stop does not prove residence access; unknown origins are not negative. Quarantined VS is not ranked.

## Amendment map and supersession

- §6.5b makes the partial Aarau-specific source-backed projection an explicit **temporary** exception to §6.5a's eventual full-route-only derivation; full Route v1, 19 destinations, all 2,110 residential candidates, transfer feasibility and proven fastest search remain required.
- §20 supersedes §18–19's blanket preview withholding **only** for indicative tax and observed direct-stop-positive Aarau rows. It does not change failed numerical gates, independent references, VS quarantine, production gates, or `availability.travel=false` and `approvals.estv/sbb=false`.
- `pages/methode.html` now describes the real preview instead of the old planned 60-minute one-stop approach; revised source attribution and hash/version drift language distinguish source date, publication and independent certification.
- `scripts/release/build.mjs` binds the new JSON and amended SPEC bytes to release wrappers. Rebuild both wrappers and Vite output after this amendment; changed release ID is not tax/route validation. Browser verification must exercise exact 20-minute Aarau, a non-Aarau workplace, unlisted municipality and error paths under `/steuerpendler/`.

## Terms and unresolved gates

Official opentransportdata.swiss [Terms of Use](https://opentransportdata.swiss/en/terms-of-use/) fetched 2026-10-22 (119743 raw HTML bytes, SHA-256 `f7897e4bcabd2916f5d2ae518cb9bee5391ec12dcc51429e99154883921d8f8a`). §§1, 5.1, 5.2 and 5.3 allow processing/publication of open data while requiring source citation, updates at the raw-data frequency, and processed analysis under the data user's name. This dated, frozen historical service-day preview cites the source and is identified as a project analysis, **not** a current timetable. Whether §5.2 requires refreshing this frozen historical derivative has not received legal clearance. Map non-commercial test assessment remains in `docs/map/publication-assessment.md`; production/commercial rights, tax-content rights and T9 references remain open. Do not present this register as a licence opinion or a waiver.

If any source digest, direct projection, legal terms, SPEC §6.5a/b/§7.1/§8/§20, or tax assumptions change, compare and update this register and the published Methode page; repeat release byte, unit, browser and live-host checks. Preserve baseline reference rows and original approvals rather than retroactively rewriting them.
