# Steuerpendler — instructions for coding agents

Read `docs/STATUS.md` first, then the SPEC sections your task touches.

Rules:
- Never manufacture ESTV/SBB reference values or timetable data. Evidence is a frozen capture plus a test.
- No backend, cookies, analytics or user accounts.
- One branch per task, PRs against `main` only, never into another PR's branch. Do not push `main`.
- Follow test-first RED/GREEN for new functions. CI must be green before merge.
- Record every vendor modification in `vendor/swisstaxcalculator/STEUERPENDLER-PATCHES.md`; data value
  fixes go in `vendor/swisstaxcalculator/data/corrections/<year>.json` with their evidence.
- Data schema changes update `SPEC.md` in the same PR. Status changes update `docs/STATUS.md`.
- Never relax a numeric gate. If a gate cannot pass by construction (the spec contradicts itself), stop and
  raise it with the owner the same day instead of building around it.
- Do not commit per-PR evidence reports, logs or regenerated JSON reports; tests and CI logs are the evidence.
- Prefer finishing the user-facing outcome (e.g. "every Gemeinde within 30 min of Zürich, ±3 min vs SBB")
  over another bounded probe.
- The original prototype is unavailable: never claim pixel fidelity.
