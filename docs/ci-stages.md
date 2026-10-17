# Verification stages — scope/navigation update, 17 October 2026

## Engineering checks

Local unit/build, real map rebuild/ID/geometry, release integrity, static content/browser, travel diagnostic units and production-build Playwright are executable. Local results are not GitHub CI or official tax/timetable acceptance. Scope/navigation browser coverage includes all 2,110 residential candidates, the separate 19-capital workplace subset, cross-canton residential lookup, separate transit/walk controls, zoom/pan/pinch/reset and preservation of selection/viewport.

## GitHub permissions and source checks

The v0.1 OAuth credential originally lacked `workflow`; the rejected upload remains historical deployment evidence. On 17 October 2026 the existing login was refreshed and both the `workflow` scope and an actual workflow-bearing branch push were verified.

Source CI restoration is reviewed separately in https://github.com/JohnDev13/steuerpendler/pull/11. It has read-only permissions, pinned action commits, a preview-engineering job and a separate hard-failing numerical-tax job. It does not suppress the existing accuracy failure. Uploading the workflow is not a successful run; inspect that PR's actual current run results and the latest deployment report. It remains a draft rather than merging a failed accuracy gate as an all-green pipeline.

## Data and release gates

All eight tax profile JSONs and the 2,110-ID municipality file remain byte-identical to the previously published full-coverage data. None is replaced by a capital-only dataset. Coverage is not numerical acceptance: the existing off-grid tax failure, all-origin→capital routing/access generation, official ESTV/SBB comparisons and owner production approvals remain independent, unresolved gates.

The owner-authorized non-commercial GitHub Pages test preview uses locally verified static files on `gh-pages`; source changes use PRs, never direct main pushes. This is not production-launch authorization. No synthetic data or sampled capital-to-capital routes are substituted for the missing all-origin timetable/access data.

Canonical scope: `SPEC.md` v1.2 §19 and `docs/spec-amendments-v1.2.md`. Older v0.1 reports describe the earlier credential and preview; do not reuse their authorization status as current fact.
