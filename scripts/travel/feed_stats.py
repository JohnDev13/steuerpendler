"""Throwaway: summarise frequencies.txt and specific transfers.txt rows of a GTFS feed (one line per fact)."""
import collections, datetime as dt, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import matrix as m

path, day = Path(sys.argv[1]), dt.date.fromisoformat(sys.argv[2])
out = []
def say(*a): out.append(" ".join(str(x) for x in a))
with zipfile.ZipFile(path) as z:
    today = m.active_services(z, day)
    trip_route, trip_service, route_type, route_name = {}, {}, {}, {}
    for r in m._rows(z, "routes.txt"):
        route_type[r["route_id"]] = r["route_type"]; route_name[r["route_id"]] = (r.get("agency_id"), r.get("route_short_name"))
    for r in m._rows(z, "trips.txt"):
        trip_route[r["trip_id"]] = r["route_id"]; trip_service[r["trip_id"]] = r["service_id"]
    active = {t for t, s in trip_service.items() if s in today}
    # frequencies
    freq = list(m._rows(z, "frequencies.txt"))
    say("FREQ rows", len(freq), "trips", len({r["trip_id"] for r in freq}))
    say("FREQ exact_times", dict(collections.Counter(r.get("exact_times") or "0" for r in freq)))
    act = [r for r in freq if r["trip_id"] in active]
    say("FREQ active rows", len(act), "trips", len({r["trip_id"] for r in act}))
    win = [r for r in act if m.gtfs_seconds(r["start_time"]) <= 9 * 3600 and m.gtfs_seconds(r["end_time"]) >= 6 * 3600]
    say("FREQ active rows overlapping 06-09", len(win), "trips", len({r["trip_id"] for r in win}))
    say("FREQ route types", dict(collections.Counter(route_type.get(trip_route.get(r["trip_id"]), "?") for r in win)))
    say("FREQ routes sample", collections.Counter(route_name.get(trip_route.get(r["trip_id"])) for r in win).most_common(15))
    say("FREQ headways", collections.Counter(r["headway_secs"] for r in win).most_common(8))
    # transfers
    n = 0; cls = collections.Counter(); kinds = collections.Counter(); samestop = collections.Counter()
    stop_level = {}; specific = []
    for r in m._rows(z, "transfers.txt"):
        n += 1
        key = "".join(k[0] if r.get(k) else "-" for k in ("from_trip_id", "to_trip_id", "from_route_id", "to_route_id"))
        t = r.get("transfer_type") or "0"
        cls[key] += 1; kinds[(key, t)] += 1
        if key == "----":
            if t == "2" and r.get("min_transfer_time"): stop_level[(r["from_stop_id"], r["to_stop_id"])] = int(r["min_transfer_time"])
        else:
            samestop[(key, r["from_stop_id"] == r["to_stop_id"])] += 1
            specific.append(r)
    say("TR rows", n); say("TR classes ft tt fr tr", dict(cls)); say("TR class,type", dict(kinds)); say("TR specific same-stop", dict(samestop))
    cmp = collections.Counter(); act_cnt = collections.Counter(); deltas = collections.Counter()
    for r in specific:
        t = r.get("transfer_type") or "0"
        a = r.get("from_trip_id"); b = r.get("to_trip_id")
        live = (not a or a in active) and (not b or b in active)
        act_cnt[(t, live)] += 1
        if t == "2" and r.get("min_transfer_time") and live:
            base = stop_level.get((r["from_stop_id"], r["to_stop_id"]), m.CHANGE_SECONDS)
            v = int(r["min_transfer_time"]); cmp["shorter" if v < base else "equal" if v == base else "longer"] += 1
            deltas[(v - base) // 60] += 1
    say("TR specific (type,active today)", dict(act_cnt))
    say("TR specific type2 vs stop-level/default", dict(cmp))
    say("TR specific type2 delta minutes", sorted(deltas.items())[:30])
    say("TR sample", [dict((k, v) for k, v in r.items() if v) for r in specific[:3]])
    say("TR stop-level type2 rows", len(stop_level), "min/median/max", min(stop_level.values()), sorted(stop_level.values())[len(stop_level)//2], max(stop_level.values()))
print("\n".join(out))
tr = [l for l in out if l.startswith("TR")]
chunk = ""
for line in tr:
    if len(chunk) + len(line) > 3800:
        print("::notice title=tr::" + chunk); chunk = ""
    chunk += line[:1800] + " || "
print("::notice title=tr::" + chunk)
