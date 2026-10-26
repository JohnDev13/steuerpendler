"""Compare the generated matrix with SBB reference journeys (SPEC 11.2, tolerance 3 minutes).

    python3 scripts/travel/compare_reference.py [--matrix site/data/travel/matrix] [--reference tests/travel/sbb-reference-2026.csv]

Fill sbb_minutes from https://www.sbb.ch for the matrix service date, fastest journey with first
boarding 06:30-08:30, from the main stop of the origin to the workplace station. Empty cells stay
"pending" and never count as passed. Exit code 1 if any filled pair deviates by more than 3 minutes.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOLERANCE_MINUTES = 3


def compare(matrix_dir: Path, reference: Path) -> list[dict]:
    results = []
    files: dict[int, dict | None] = {}
    with reference.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            to = int(row["to_bfs"])
            if to not in files:
                path = matrix_dir / "to" / f"{to}.json"
                files[to] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            data = files[to]
            ours = None
            if data is not None:
                match = next((r for r in data["rows"] if r[0] == int(row["from_bfs"])), None)
                ours = math.ceil(match[1] / 60) if match else None
            sbb = int(row["sbb_minutes"]) if row["sbb_minutes"].strip() else None
            if data is None:
                status = "not_a_computed_workplace"
            elif sbb is None:
                status = "pending"
            elif ours is None:
                status = "failed_missing" if sbb <= 30 else "unknown_unobserved"
            else:
                status = "passed" if abs(ours - sbb) <= TOLERANCE_MINUTES else "failed"
            results.append({"pair": int(row["pair"]), "from": row["from"], "to": row["to"], "sbb": sbb, "ours": ours, "status": status})
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=ROOT / "site/data/travel/matrix")
    parser.add_argument("--reference", type=Path, default=ROOT / "tests/travel/sbb-reference-2026.csv")
    args = parser.parse_args(argv)
    results = compare(args.matrix, args.reference)
    for r in results:
        print(f"{r['pair']:>2} {r['from']} -> {r['to']}: SBB {r['sbb']} ours {r['ours']} {r['status']}")
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(json.dumps(counts, sort_keys=True))
    return 1 if any(r["status"].startswith("failed") or r["status"] == "unknown_unobserved" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
