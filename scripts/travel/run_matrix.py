"""Build site/data/travel/matrix/ from one GTFS zip.

    python3 scripts/travel/run_matrix.py --gtfs GTFS_FP2026_20261021.zip --date 2026-10-27 \
        --feed-url https://... [--out site/data/travel/matrix]

Writes meta.json and to/<workplace BFS>.json. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matrix  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def workplaces() -> list[int]:
    source = (ROOT / "src/destinations.ts").read_text(encoding="utf-8")
    found = [int(value) for value in re.findall(r"\{bfs:(\d+),", source)]
    if len(found) != 19:
        raise matrix.MatrixError(f"expected 19 workplaces in src/destinations.ts, found {len(found)}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gtfs", type=Path, required=True)
    parser.add_argument("--date", type=dt.date.fromisoformat, required=True)
    parser.add_argument("--feed-url", default="")
    parser.add_argument("--map", type=Path, default=ROOT / "site/data/map/switzerland-2026.json")
    parser.add_argument("--gemeinden", type=Path, default=ROOT / "site/data/gemeinden-2026.json")
    parser.add_argument("--out", type=Path, default=ROOT / "site/data/travel/matrix")
    args = parser.parse_args(argv)
    if args.date.weekday() != 1:
        raise matrix.MatrixError(f"{args.date} is not a Tuesday (SPEC 8 reference day)")

    topology = json.loads(args.map.read_text(encoding="utf-8"))
    gemeinden = json.loads(args.gemeinden.read_text(encoding="utf-8"))["gemeinden"]
    municipalities = {int(key) for key in gemeinden}
    names = {int(key): value[0] for key, value in gemeinden.items()}
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = ""
    meta, files = matrix.build(args.gtfs, topology, workplaces(), municipalities, args.date, args.feed_url, revision, names)

    (args.out / "to").mkdir(parents=True, exist_ok=True)
    for old in (args.out / "to").glob("*.json"):
        old.unlink()
    for workplace, content in files.items():
        (args.out / "to" / f"{workplace}.json").write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (args.out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for workplace, info in meta["workplaces"].items():
        print(f"{workplace}: {info['station']} rows={info['rows']}")
    missing = [w for w, info in meta["workplaces"].items() if not info["rows"]]
    if missing:
        print(f"no station found for workplaces {missing}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
