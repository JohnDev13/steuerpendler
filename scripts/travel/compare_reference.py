"""Compare the generated matrix with SBB reference journeys (SPEC 11.2, tolerance 3 minutes).

    python3 scripts/travel/compare_reference.py [--matrix site/data/travel/matrix] [--reference tests/travel/sbb-reference-2026.csv]

sbb_minutes: fastest SBB journey (first boarding 06:30-08:30) from the origin's main stop. The matrix
takes the fastest stop anywhere in the Gemeinde, so it may be faster; it must never be more than 3 min
slower. When it boards elsewhere, same_stop/sbb_same_stop_minutes hold SBB's time from that same stop,
and the matrix must be within 3 minutes of it. Filled by scripts/travel/fetch_reference.py, never by
hand. Empty cells stay "pending". Exit code 1 on any failure or unchecked faster stop.
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
            same = (row.get("sbb_same_stop_minutes") or "").strip()
            same = int(same) if same else None
            if data is None:
                status = "not_a_computed_workplace"
            elif sbb is None:
                status = "pending"
            elif ours is None:
                # Complete scan: absence is consistent only if SBB also needs more than the cap.
                status = "failed_missing" if sbb <= 30 else "consistent_beyond_cap"
            elif ours > sbb + TOLERANCE_MINUTES:
                status = "failed"  # slower than SBB from the main stop: a route is missing
            elif same is not None:
                # The matrix may board at a faster stop elsewhere in the Gemeinde; judge it there.
                status = "passed" if abs(ours - same) <= TOLERANCE_MINUTES else "failed"
            elif abs(ours - sbb) <= TOLERANCE_MINUTES:
                status = "passed"
            else:
                status = "pending_same_stop"
            results.append({"pair": int(row["pair"]), "from": row["from"], "to": row["to"], "sbb": sbb, "same_stop": row.get("same_stop") or "",
                            "sbb_same_stop": same, "ours": ours, "status": status})
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=ROOT / "site/data/travel/matrix")
    parser.add_argument("--reference", type=Path, default=ROOT / "tests/travel/sbb-reference-2026.csv")
    parser.add_argument("--require-complete", action="store_true",
                        help="also fail while any pair of a computed workplace is still pending")
    args = parser.parse_args(argv)
    results = compare(args.matrix, args.reference)
    for r in results:
        via = f" (SBB from {r['same_stop']}: {r['sbb_same_stop']})" if r["same_stop"] else ""
        print(f"{r['pair']:>2} {r['from']} -> {r['to']}: SBB {r['sbb']}{via} ours {r['ours']} {r['status']}")
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(json.dumps(counts, sort_keys=True))
    blocking = ("failed", "pending_same_stop") + (("pending",) if args.require_complete else ())
    return 1 if any(r["status"].startswith(blocking) for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
