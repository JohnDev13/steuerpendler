"""Fill tests/travel/sbb-reference-2026.csv from the public Swiss timetable API (SPEC 11.2).

    python3 scripts/travel/fetch_reference.py --date 2026-10-27 [--csv tests/travel/sbb-reference-2026.csv]

Source: https://transport.opendata.ch (the SBB/search.ch timetable). For every pair it requests
scheduled connections from the origin's main stop to the workplace station with departures between
06:30 and 08:30 and keeps the shortest scheduled door-to-door duration. Values are written exactly as
returned, with the resolved station names in `note` so a reviewer can check them on sbb.ch.
Never edit sbb_minutes by hand. Standard library only; needs network access (run it in Actions).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://transport.opendata.ch/v1/connections"
WINDOW = ("06:30", "08:30")
QUERY_TIMES = ("06:30", "06:50", "07:10", "07:30", "07:50", "08:10", "08:30")
# Workplace station as SBB names it; everything else uses the Gemeinde name.
STATION_NAMES = {"Zürich": "Zürich HB", "Basel": "Basel SBB",
                 # Ingenbohl's railway station is Brunnen.
                 "Ingenbohl": "Brunnen",
                 # Maur has no rail station of that name; a bare "Maur" resolves to St-Maurice.
                 "Maur": "Maur, Dorf"}


def same_place(query: str, resolved: str) -> bool:
    """The API's fuzzy match must still name the queried place (guards against Maur -> St-Maurice)."""
    norm = lambda text: re.sub(r"[^a-z]", "", text.lower().replace("ü", "u").replace("é", "e").replace("è", "e"))
    head = norm(re.split(r"[ ,(]", query)[0])
    return norm(resolved).startswith(head)


def station_query(name: str) -> str:
    """'Kilchberg (ZH)' -> 'Kilchberg ZH' (SBB naming of disambiguated places)."""
    return STATION_NAMES.get(name, re.sub(r"\s*\((\w+)\)", r" \1", name))


def fetch(origin: str, destination: str, day: dt.date, at: str) -> list[dict]:
    params = urllib.parse.urlencode({"from": origin, "to": destination, "date": day.isoformat(), "time": at,
                                     "limit": 6, "direct": 0})
    request = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": "steuerpendler-reference/1"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response).get("connections") or []
        except Exception:  # noqa: BLE001 - retried, then raised
            if attempt == 3:
                raise
            time.sleep(2 + 3 * attempt)
    return []


def fastest(origin: str, destination: str, day: dt.date) -> dict | None:
    best = None
    seen = set()
    for at in QUERY_TIMES:
        for connection in fetch(origin, destination, day, at):
            departure = connection["from"].get("departureTimestamp")
            arrival = connection["to"].get("arrivalTimestamp")
            if departure is None or arrival is None or (departure, arrival) in seen:
                continue
            seen.add((departure, arrival))
            if not same_place(origin, connection["from"]["station"]["name"]) \
                    or not same_place(destination, connection["to"]["station"]["name"]):
                continue
            # The window is checked in Swiss local time, taken from the ISO string.
            local = dt.datetime.fromisoformat(connection["from"]["departure"]).replace(tzinfo=None)
            if not (WINDOW[0] <= local.strftime("%H:%M") <= WINDOW[1]):
                continue
            minutes = round((arrival - departure) / 60)
            if best is None or minutes < best["minutes"]:
                best = {"minutes": minutes, "departure": local.strftime("%H:%M"),
                        "from": connection["from"]["station"]["name"], "to": connection["to"]["station"]["name"],
                        "transfers": connection.get("transfers")}
        time.sleep(0.4)
    return best


def boarding_stop(matrix_dir: Path, origin: int, workplace: int) -> str:
    path = matrix_dir / "to" / f"{workplace}.json"
    if not path.exists():
        return ""
    for row in json.loads(path.read_text(encoding="utf-8"))["rows"]:
        if row[0] == origin:
            return row[3]
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=dt.date.fromisoformat, required=True)
    parser.add_argument("--csv", type=Path, default=ROOT / "tests/travel/sbb-reference-2026.csv")
    parser.add_argument("--matrix", type=Path, default=ROOT / "site/data/travel/matrix",
                        help="also query SBB from the stop the matrix boards at (SPEC T3: actual boarding stops)")
    args = parser.parse_args(argv)
    with args.csv.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    for column in ("same_stop", "sbb_same_stop_minutes"):
        if column not in fields:
            fields.insert(fields.index("sbb_departure") + 1 if column == "same_stop" else fields.index("same_stop") + 1, column)
    retrieved = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    failures = 0
    for row in rows:
        origin, destination = station_query(row["from"]), station_query(row["to"])
        try:
            best = fastest(origin, destination, args.date)
        except Exception as error:  # noqa: BLE001
            best, failures = None, failures + 1
            print(f"{row['pair']:>2} {origin} -> {destination}: request failed: {error}", file=sys.stderr)
        if best is None:
            row.update(sbb_minutes="", sbb_departure="", retrieved=retrieved,
                       note=f"no connection 06:30-08:30 returned for {origin} -> {destination}")
        else:
            row.update(sbb_minutes=str(best["minutes"]), sbb_departure=best["departure"], retrieved=retrieved,
                       note=f"transport.opendata.ch {args.date}: {best['from']} -> {best['to']}, "
                            f"{best['transfers']} changes")
        row.update(same_stop="", sbb_same_stop_minutes="")
        board = boarding_stop(args.matrix, int(row["from_bfs"]), int(row["to_bfs"]))
        if board:
            try:
                same = fastest(board, destination, args.date)
            except Exception as error:  # noqa: BLE001
                same, failures = None, failures + 1
                print(f"{row['pair']:>2} {board} -> {destination}: request failed: {error}", file=sys.stderr)
            row.update(same_stop=board, sbb_same_stop_minutes=str(same["minutes"]) if same else "")
            if same:
                row["note"] += f"; same stop: {same['from']} -> {same['to']} {same['departure']}"
        print(f"{row['pair']:>2} {row['from']} -> {row['to']}: {row['sbb_minutes'] or '-'} min "
              f"({row['sbb_departure'] or '-'}); from {board or '-'}: {row['sbb_same_stop_minutes'] or '-'}. {row['note']}")
    with args.csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
