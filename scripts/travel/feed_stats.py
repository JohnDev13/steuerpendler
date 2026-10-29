"""Throwaway: for trip-pair type 2 rules active on the day, compare min_transfer_time with the scheduled gap."""
import collections, datetime as dt, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import matrix as m

path, day = Path(sys.argv[1]), dt.date.fromisoformat(sys.argv[2])
with zipfile.ZipFile(path) as z:
    today = m.active_services(z, day); known = {r["service_id"] for r in m._rows(z, "calendar.txt")} | {r["service_id"] for r in m._rows(z, "calendar_dates.txt")}
    active = {r["trip_id"] for r in m._rows(z, "trips.txt") if r["service_id"] in today}
    rules = []
    for r in m._rows(z, "transfers.txt"):
        if r.get("from_trip_id") and r["from_trip_id"] in active and r.get("to_trip_id") in active and r.get("transfer_type") in ("1", "2", "3"):
            svc = r.get("service_id") or ""
            if svc and svc in known and svc not in today:
                continue
            rules.append(r)
    need = {(r["from_trip_id"], r["from_stop_id"]) for r in rules} | {(r["to_trip_id"], r["to_stop_id"]) for r in rules}
    trips = {t for t, _ in need}
    times = {}
    for r in m._rows(z, "stop_times.txt"):
        if r["trip_id"] in trips and (r["trip_id"], r["stop_id"]) in need:
            times[(r["trip_id"], r["stop_id"])] = (m.gtfs_seconds(r["arrival_time"] or r["departure_time"]), m.gtfs_seconds(r["departure_time"] or r["arrival_time"]))
c = collections.Counter(); d = collections.Counter(); ex = []
for r in rules:
    a = times.get((r["from_trip_id"], r["from_stop_id"])); b = times.get((r["to_trip_id"], r["to_stop_id"]))
    if not a or not b: c["missing call"] += 1; continue
    gap = b[1] - a[0]; t = r["transfer_type"]
    if t == "3": c["type3 gap<=0" if gap <= 0 else "type3 gap>0"] += 1; continue
    need_s = 0 if t == "1" else int(r.get("min_transfer_time") or 0)
    if gap < 0: c[f"type{t} B departs before A arrives"] += 1
    elif gap < need_s: c[f"type{t} gap < rule (connection impossible)"] += 1; d[(need_s - gap) // 60] += 1; ex.append((r["from_stop_id"], r["to_stop_id"], gap, need_s))
    elif gap == need_s: c[f"type{t} gap == rule"] += 1
    else: c[f"type{t} gap > rule"] += 1
    if t == "2":
        c["type2 rule<120" if need_s < 120 else "type2 rule>=120"] += 1
line = f"rules {len(rules)} :: {dict(c)} :: impossible by minutes {sorted(d.items())} :: examples {ex[:5]}"
print(line); print("::notice title=gap::" + line[:3900])
