"""Gemeinde -> workplace public-transport matrix from a Swiss GTFS feed.

One module, standard library only, so it runs unchanged on a GitHub runner.

Metric (SPEC 8, owner decisions of 21/22 Oct 2026): for every residential Gemeinde and each of the
19 workplaces, the shortest time from first boarding a vehicle at a stop inside the Gemeinde to
arrival at the workplace station complex, over all first boardings in [06:30, 08:30] on the service
date, with any number of changes, capped at 30 minutes. External access to the first stop is
assumed zero and labelled unmeasured. Times are exact seconds from the timetable.

Algorithm: reverse profile Connection Scan (Dibbelt, Pajor, Strasser, Wagner 2013), one scan per
destination over the connections departing in [06:30, 09:00].

Changes between vehicles (GTFS precedence: trip-pair rule > stop-pair rule > default):
- transfers.txt rows with from_trip_id/to_trip_id set the change time for that trip pair at that stop
  pair: type 1 guaranteed (0 s), type 2 min_transfer_time, type 3 forbidden, type 4 stay seated
  (no change counted). The Swiss feed adds a service_id per rule; rules not valid on the day are dropped;
- otherwise transfers.txt stop-pair rows: type 2 minimum change time, type 3 forbidden;
- otherwise CHANGE_SECONDS (120 s) at the same stop or between stops of the same parent station;
- short walks between other stops within WALK_RADIUS_M, at WALK_SPEED_MPS with WALK_DETOUR.
Route-specific rule rows fail the build (not present in the Swiss feed).

Headway-based trips (frequencies.txt) are expanded into one trip per departure from start_time.

Every connection departing in the window is scanned, so a Gemeinde without a result has no journey of at
most 30 minutes from a stop inside it under this model (access walk to the first stop: 0 s, unmeasured).
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

WINDOW_START = 6 * 3600 + 30 * 60
WINDOW_END = 8 * 3600 + 30 * 60
CAP_SECONDS = 30 * 60
CHANGE_SECONDS = 120
WALK_RADIUS_M = 400.0
WALK_SPEED_MPS = 1.2
WALK_DETOUR = 1.3
TARGET_COMPLEX_RADIUS_M = 300.0
INF = float("inf")
SCHEMA = "steuerpendler.travel-matrix.v1"
RAIL_ROUTE_TYPES = {2} | set(range(100, 118))


class MatrixError(RuntimeError):
    pass


# ---------------------------------------------------------------------------------------------
# Geometry: LV95 projection and the shipped TopoJSON municipality map
# ---------------------------------------------------------------------------------------------

def wgs84_to_lv95(lon: float, lat: float) -> tuple[float, float]:
    """swisstopo approximate formulas (about 1 m accuracy)."""
    lat_aux = (lat * 3600 - 169028.66) / 10000
    lon_aux = (lon * 3600 - 26782.5) / 10000
    east = (2600072.37 + 211455.93 * lon_aux - 10938.51 * lon_aux * lat_aux
            - 0.36 * lon_aux * lat_aux ** 2 - 44.54 * lon_aux ** 3)
    north = (1200147.07 + 308807.95 * lat_aux + 3745.25 * lon_aux ** 2 + 76.63 * lat_aux ** 2
             - 194.56 * lon_aux ** 2 * lat_aux + 119.79 * lat_aux ** 3)
    return east, north


def decode_municipalities(topology: dict, object_name: str = "gemeinden") -> dict[int, list[list[list[tuple[float, float]]]]]:
    """Return {bfs: multipolygon} with rings as lists of LV95 points."""
    scale_x, scale_y = topology["transform"]["scale"]
    shift_x, shift_y = topology["transform"]["translate"]
    arcs = []
    for arc in topology["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * scale_x + shift_x, y * scale_y + shift_y))
        arcs.append(points)

    def ring(indexes):
        points: list[tuple[float, float]] = []
        for index in indexes:
            part = arcs[index] if index >= 0 else arcs[~index][::-1]
            points.extend(part if not points else part[1:])
        return points

    result = {}
    for geometry in topology["objects"][object_name]["geometries"]:
        if "id" not in geometry or not geometry.get("arcs"):
            continue
        polygons = geometry["arcs"] if geometry["type"] == "MultiPolygon" else [geometry["arcs"]]
        result[int(geometry["id"])] = [[ring(r) for r in polygon] for polygon in polygons]
    return result


def _in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class MunicipalityIndex:
    """Point-in-polygon lookup with a bounding-box grid."""

    def __init__(self, polygons: dict[int, list], cell: float = 5000.0):
        self.polygons = polygons
        self.cell = cell
        self.grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        self.bbox = {}
        for bfs, multipolygon in polygons.items():
            xs = [p[0] for polygon in multipolygon for p in polygon[0]]
            ys = [p[1] for polygon in multipolygon for p in polygon[0]]
            box = (min(xs), min(ys), max(xs), max(ys))
            self.bbox[bfs] = box
            for gx in range(int(box[0] // cell), int(box[2] // cell) + 1):
                for gy in range(int(box[1] // cell), int(box[3] // cell) + 1):
                    self.grid[(gx, gy)].append(bfs)

    def locate(self, x: float, y: float) -> int | None:
        for bfs in self.grid.get((int(x // self.cell), int(y // self.cell)), ()):
            x0, y0, x1, y1 = self.bbox[bfs]
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            for polygon in self.polygons[bfs]:
                if _in_ring(x, y, polygon[0]) and not any(_in_ring(x, y, hole) for hole in polygon[1:]):
                    return bfs
        return None


# ---------------------------------------------------------------------------------------------
# GTFS
# ---------------------------------------------------------------------------------------------

def gtfs_seconds(value: str) -> int:
    hours, minutes, seconds = value.strip().split(":")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds)


def _rows(archive: zipfile.ZipFile, name: str):
    if name not in archive.namelist():
        return
    with archive.open(name) as handle:
        yield from csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig", newline=""))


def active_services(archive: zipfile.ZipFile, day: dt.date) -> set[str]:
    weekday = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
    stamp = day.strftime("%Y%m%d")
    services = {row["service_id"] for row in _rows(archive, "calendar.txt")
                if row["start_date"] <= stamp <= row["end_date"] and row[weekday] == "1"}
    for row in _rows(archive, "calendar_dates.txt"):
        if row["date"] != stamp:
            continue
        if row["exception_type"] == "1":
            services.add(row["service_id"])
        elif row["exception_type"] == "2":
            services.discard(row["service_id"])
    return services


def known_services(archive: zipfile.ZipFile) -> set[str]:
    return ({row["service_id"] for row in _rows(archive, "calendar.txt")}
            | {row["service_id"] for row in _rows(archive, "calendar_dates.txt")})


@dataclass
class Stop:
    stop_id: str
    name: str
    x: float
    y: float
    parent: str


@dataclass
class Feed:
    stops: dict[str, Stop]
    connections: list[tuple]  # (dep, arr, from_stop, to_stop, trip, can_board, can_alight)
    trip_route_type: dict[str, int]
    trip_last_stop: dict[str, str]
    trip_first_stop: dict[str, str]
    min_change: dict[tuple[str, str], int]
    forbidden: set[tuple[str, str]]
    in_seat: dict[str, list[str]]
    notes: dict = field(default_factory=dict)
    # (from_trip, from_stop) -> [(to_stop, to_trip, required seconds or None if forbidden)]
    trip_rules: dict = field(default_factory=dict)


def load_feed(path: Path, day: dt.date, horizon_end: int = WINDOW_END + CAP_SECONDS) -> Feed:
    with zipfile.ZipFile(path) as archive:
        today = active_services(archive, day)
        yesterday = active_services(archive, day - dt.timedelta(days=1))

        route_type = {row["route_id"]: int(row["route_type"]) for row in _rows(archive, "routes.txt")}
        trip_offset: dict[str, int] = {}
        trip_route_type: dict[str, int] = {}
        for row in _rows(archive, "trips.txt"):
            # Trips of the previous service day still running after midnight appear with times >= 24:00.
            if row["service_id"] in today:
                trip_offset[row["trip_id"]] = 0
            elif row["service_id"] in yesterday:
                trip_offset[row["trip_id"]] = -86400
            else:
                continue
            trip_route_type[row["trip_id"]] = route_type.get(row["route_id"], 3)

        # Headway-based trips (frequencies.txt): stop_times are a template; one copy runs every headway_secs
        # from start_time (inclusive) to end_time (exclusive). exact_times 0 and 1 expand the same way.
        frequencies: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
        for row in _rows(archive, "frequencies.txt"):
            if row["trip_id"] in trip_offset:
                frequencies[row["trip_id"]].append((gtfs_seconds(row["start_time"]), gtfs_seconds(row["end_time"]),
                                                    int(row["headway_secs"])))

        stops: dict[str, Stop] = {}
        for row in _rows(archive, "stops.txt"):
            try:
                x, y = wgs84_to_lv95(float(row["stop_lon"]), float(row["stop_lat"]))
            except (KeyError, ValueError):
                continue
            stops[row["stop_id"]] = Stop(row["stop_id"], row.get("stop_name", ""), x, y,
                                         row.get("parent_station") or row["stop_id"])

        calls: dict[str, list[tuple]] = defaultdict(list)
        templates: dict[str, list[tuple]] = defaultdict(list)
        lo, hi = WINDOW_START - 3600, horizon_end + 3600
        for row in _rows(archive, "stop_times.txt"):
            offset = trip_offset.get(row["trip_id"])
            if offset is None:
                continue
            arr = gtfs_seconds(row["arrival_time"] or row["departure_time"]) + offset
            dep = gtfs_seconds(row["departure_time"] or row["arrival_time"]) + offset
            call = (int(row["stop_sequence"]), arr, dep, row["stop_id"],
                    row.get("pickup_type") or "0", row.get("drop_off_type") or "0")
            if row["trip_id"] in frequencies:
                templates[row["trip_id"]].append(call)
                continue
            if dep < lo or arr > hi:
                continue
            calls[row["trip_id"]].append(call)
        expanded = 0
        for trip, template in templates.items():
            template.sort()
            first = template[0][2]
            for start, end, headway in frequencies[trip]:
                for departure in range(start + trip_offset[trip], end + trip_offset[trip], max(headway, 1)):
                    shift = departure - first
                    copy = [(seq, arr + shift, dep + shift, stop, pick, drop) for seq, arr, dep, stop, pick, drop in template]
                    copy = [c for c in copy if not (c[2] < lo or c[1] > hi)]
                    if len(copy) < 2:
                        continue
                    name = f"{trip}@{departure}"
                    calls[name] = copy
                    trip_route_type[name] = trip_route_type[trip]
                    expanded += 1

        connections = []
        trip_last_stop, trip_first_stop = {}, {}
        for trip, rows in calls.items():
            rows.sort()
            trip_first_stop[trip] = rows[0][3]
            trip_last_stop[trip] = rows[-1][3]
            for a, b in zip(rows, rows[1:]):
                if a[2] < WINDOW_START or a[2] > horizon_end:
                    continue
                if a[3] not in stops or b[3] not in stops:
                    continue
                connections.append((a[2], b[1], a[3], b[3], trip, a[4] != "1", b[5] != "1"))

        min_change: dict[tuple[str, str], int] = {}
        forbidden: set[tuple[str, str]] = set()
        in_seat: dict[str, list[str]] = defaultdict(list)
        trip_rules: dict[tuple[str, str], list[tuple]] = defaultdict(list)
        services = known_services(archive)
        counts = defaultdict(int)
        for row in _rows(archive, "transfers.txt"):
            kind = row.get("transfer_type") or "0"
            from_trip, to_trip = row.get("from_trip_id") or "", row.get("to_trip_id") or ""
            route_only = (row.get("from_route_id") or row.get("to_route_id")) and not (from_trip and to_trip)
            if route_only or bool(from_trip) != bool(to_trip):
                # Not present in the Swiss feed; fail closed rather than silently ignore a rule class.
                raise MatrixError(f"transfers.txt rule class not modelled: {dict(row)}")
            service = row.get("service_id") or ""
            if service and service in services and service not in today:
                counts["tripRulesOtherDays"] += 1
                continue
            if service and service not in services:
                counts["tripRulesUnknownServiceApplied"] += 1
            if kind == "4":
                if from_trip and to_trip:
                    in_seat[from_trip].append(to_trip)
                continue
            if from_trip:
                if from_trip not in trip_offset or to_trip not in trip_offset:
                    continue
                if kind == "0":
                    continue  # recommended: same as the stop-level rule
                required = None if kind == "3" else 0 if kind == "1" else int(row.get("min_transfer_time") or CHANGE_SECONDS)
                trip_rules[(from_trip, row["from_stop_id"])].append((row["to_stop_id"], to_trip, required))
                counts["tripRulesApplied"] += 1
                continue
            pair = (row["from_stop_id"], row["to_stop_id"])
            if kind == "3":
                forbidden.add(pair)
            elif kind == "2" and row.get("min_transfer_time"):
                min_change[pair] = int(row["min_transfer_time"])
            elif kind in ("0", "1"):
                min_change.setdefault(pair, 0 if kind == "1" else CHANGE_SECONDS)

    notes = {"frequencyTrips": len(frequencies), "frequencyTripCopies": expanded, **dict(sorted(counts.items()))}
    return Feed(stops, connections, trip_route_type, trip_last_stop, trip_first_stop, min_change, forbidden,
                dict(in_seat), notes, dict(trip_rules))


def footpaths(feed: Feed) -> dict[str, list[tuple[str, int]]]:
    """Change options from an alighting stop: [(boarding stop, seconds)], including the stop itself."""
    used = {c[3] for c in feed.connections if c[6]} | {c[2] for c in feed.connections if c[5]}
    by_parent = defaultdict(list)
    cell = WALK_RADIUS_M
    grid = defaultdict(list)
    for stop_id in used:
        stop = feed.stops[stop_id]
        by_parent[stop.parent].append(stop_id)
        grid[(int(stop.x // cell), int(stop.y // cell))].append(stop_id)

    paths: dict[str, list[tuple[str, int]]] = {}
    for stop_id in used:
        stop = feed.stops[stop_id]
        best: dict[str, int] = {}
        gx, gy = int(stop.x // cell), int(stop.y // cell)
        for nx in (gx - 1, gx, gx + 1):
            for ny in (gy - 1, gy, gy + 1):
                for other_id in grid.get((nx, ny), ()):
                    other = feed.stops[other_id]
                    distance = math.hypot(other.x - stop.x, other.y - stop.y)
                    if other_id == stop_id or other.parent == stop.parent:
                        seconds = CHANGE_SECONDS
                    elif distance <= WALK_RADIUS_M:
                        seconds = max(CHANGE_SECONDS, math.ceil(distance * WALK_DETOUR / WALK_SPEED_MPS))
                    else:
                        continue
                    best[other_id] = seconds
        for other_id in by_parent[stop.parent]:
            best.setdefault(other_id, CHANGE_SECONDS)
        for other_id in list(best):
            pair = (stop_id, other_id)
            if pair in feed.forbidden:
                del best[other_id]
            elif pair in feed.min_change:
                best[other_id] = feed.min_change[pair]
        paths[stop_id] = sorted(best.items())
    return paths


# ---------------------------------------------------------------------------------------------
# Reverse profile Connection Scan
# ---------------------------------------------------------------------------------------------

class Profile:
    """Pareto set of (departure, arrival) at a stop, appended in decreasing departure order."""

    __slots__ = ("neg_dep", "arr", "transfers")

    def __init__(self):
        self.neg_dep: list[int] = []
        self.arr: list[float] = []
        self.transfers: list[int] = []

    def earliest(self, ready: float) -> tuple[float, int]:
        index = bisect.bisect_right(self.neg_dep, -ready) - 1
        if index < 0:
            return INF, 0
        return self.arr[index], self.transfers[index]

    def add(self, dep: int, arr: float, transfers: int) -> None:
        if self.arr and arr >= self.arr[-1]:
            return
        if self.neg_dep and -dep == self.neg_dep[-1]:
            self.arr[-1], self.transfers[-1] = arr, transfers
        else:
            self.neg_dep.append(-dep)
            self.arr.append(arr)
            self.transfers.append(transfers)


@dataclass
class StopResult:
    seconds: int
    first_board: int
    transfers: int


def scan(feed: Feed, targets: set[str], paths: dict[str, list[tuple[str, int]]],
         ordered: list[tuple] | None = None, changes: bool = True, stats: dict | None = None) -> dict[str, StopResult]:
    """changes=False: direct rides only (stay-seated continuations still count as one ride)."""
    connections = ordered if ordered is not None else sorted(feed.connections, key=lambda c: (-c[0], -c[1]))
    trip_best: dict[str, tuple[float, int]] = {}
    profiles: dict[str, Profile] = defaultdict(Profile)
    # Stops that trip-specific rules lead to keep every boarding (not only the Pareto set), so a rule that
    # rules out the best departure can fall back to the next allowed one exactly.
    rule_stops = {to_stop for rules in feed.trip_rules.values() for to_stop, _, _ in rules} if changes else set()
    boardings: dict[str, list[tuple[int, float, int, str]]] = defaultdict(list)

    for dep, arr, origin, stop, trip, can_board, can_alight in connections:
        best, transfers = trip_best.get(trip, (INF, 0))
        if can_alight and stop in targets and arr < best:
            best, transfers = arr, 0
        if stop == feed.trip_last_stop.get(trip):
            for following in feed.in_seat.get(trip, ()):
                start = feed.trip_first_stop.get(following)
                if start is None or feed.stops[start].parent != feed.stops[stop].parent:
                    continue
                candidate, more = trip_best.get(following, (INF, 0))
                if candidate < best:
                    best, transfers = candidate, more
        if can_alight:
            rules = feed.trip_rules.get((trip, stop)) if changes else None
            by_stop: dict[str, dict[str, int | None]] = defaultdict(dict)
            for to_stop, to_trip, required in rules or ():
                by_stop[to_stop][to_trip] = required
            for other, seconds in paths.get(stop, ()):
                if other in by_stop:
                    continue
                profile = profiles.get(other)
                if profile is None:
                    continue
                candidate, more = profile.earliest(arr + seconds)
                if candidate < best:
                    best, transfers = candidate, more + 1
            generic = dict(paths.get(stop, ()))
            for other, specific in by_stop.items():
                default = generic.get(other)  # None: no change possible without a rule
                for b_dep, b_best, b_more, b_trip in boardings.get(other, ()):
                    required = specific[b_trip] if b_trip in specific else default
                    allowed = required is not None and b_dep >= arr + required
                    if stats is not None and b_trip in specific:
                        by_default = default is not None and b_dep >= arr + default
                        if allowed != by_default:
                            key = "ruleAllowed" if allowed else "ruleRejected"
                            stats[key] = stats.get(key, 0) + 1
                    if not allowed:
                        continue
                    if b_best < best:
                        best, transfers = b_best, b_more + 1
        if best == INF:
            continue
        if best < trip_best.get(trip, (INF, 0))[0]:
            trip_best[trip] = (best, transfers)
        if can_board:
            profiles[origin].add(dep, best, transfers)
            if origin in rule_stops:
                boardings[origin].append((dep, best, transfers, trip))

    results: dict[str, StopResult] = {}
    for stop_id, profile in profiles.items():
        for neg_dep, arrival, transfers in zip(profile.neg_dep, profile.arr, profile.transfers):
            first = -neg_dep
            if not WINDOW_START <= first <= WINDOW_END:
                continue
            seconds = int(arrival - first)
            if seconds <= CAP_SECONDS and (stop_id not in results or seconds < results[stop_id].seconds):
                results[stop_id] = StopResult(seconds, first, transfers)
    return results


# ---------------------------------------------------------------------------------------------
# Workplace targets and Gemeinde aggregation
# ---------------------------------------------------------------------------------------------

def stop_municipalities(feed: Feed, index: MunicipalityIndex) -> dict[str, int]:
    result = {}
    for stop_id, stop in feed.stops.items():
        bfs = index.locate(stop.x, stop.y)
        if bfs is not None:
            result[stop_id] = bfs
    return result


def station_matches(gemeinde: str, station: str) -> bool:
    """'Altdorf (UR)' ~ 'Altdorf UR', 'Zürich' ~ 'Zürich HB'; 'Stans' is not 'Stansstad'."""
    base = re.sub(r"\s*\((\w+)\)", r" \1", gemeinde).strip()
    return station == base or station.startswith(base + " ") or station.startswith(base + ",")


def workplace_targets(feed: Feed, assignment: dict[str, int], workplace: int,
                      gemeinde_name: str | None = None) -> tuple[set[str], str | None]:
    """Main rail station of the workplace and every stop within TARGET_COMPLEX_RADIUS_M of it, so
    bus/tram stops of the station complex count as arrival. The main station is the rail station named
    like the Gemeinde with the most rail calls in the window (merged Gemeinden such as Glarus also
    contain busier neighbouring stations); without a matching name, the busiest rail station."""
    departures = defaultdict(int)
    for _, _, origin, stop, trip, can_board, can_alight in feed.connections:
        if feed.trip_route_type.get(trip, 3) not in RAIL_ROUTE_TYPES:
            continue
        if can_board and assignment.get(origin) == workplace:
            departures[feed.stops[origin].parent] += 1
        if can_alight and assignment.get(stop) == workplace:
            departures[feed.stops[stop].parent] += 1
    if not departures:
        return set(), None
    candidates = sorted(departures)
    if gemeinde_name:
        child_names = {}
        for stop in feed.stops.values():
            child_names.setdefault(stop.parent, stop.name)
        named = [key for key in candidates
                 if station_matches(gemeinde_name, feed.stops[key].name if key in feed.stops else child_names.get(key, ""))]
        candidates = named or candidates
    parent = max(candidates, key=lambda key: departures[key])
    members = [s for s in feed.stops.values() if s.parent == parent or s.stop_id == parent]
    cx = sum(s.x for s in members) / len(members)
    cy = sum(s.y for s in members) / len(members)
    targets = {s.stop_id for s in feed.stops.values()
               if s.parent == parent or math.hypot(s.x - cx, s.y - cy) <= TARGET_COMPLEX_RADIUS_M}
    name = (feed.stops.get(parent) or members[0]).name
    return targets, name


def municipality_rows(feed: Feed, assignment: dict[str, int], results: dict[str, StopResult],
                      workplace: int, municipalities: set[int]) -> list[list]:
    best: dict[int, tuple] = {}
    for stop_id, result in results.items():
        bfs = assignment.get(stop_id)
        if bfs is None or bfs not in municipalities:
            continue
        key = (result.seconds, result.transfers, result.first_board, stop_id)
        if bfs not in best or key < best[bfs][0]:
            best[bfs] = (key, result, stop_id)
    rows = [[bfs, r.seconds, r.transfers, feed.stops[s].name, r.first_board] for bfs, (_, r, s) in best.items()]
    if workplace in municipalities:
        rows = [row for row in rows if row[0] != workplace]
        rows.append([workplace, 0, 0, "", 0])
    rows.sort(key=lambda row: (row[1], row[0]))
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(gtfs: Path, topology: dict, workplaces: list[int], municipalities: set[int], day: dt.date,
          feed_url: str = "", revision: str = "", names: dict[int, str] | None = None) -> tuple[dict, dict[int, dict]]:
    feed = load_feed(gtfs, day)
    index = MunicipalityIndex(decode_municipalities(topology))
    assignment = stop_municipalities(feed, index)
    paths = footpaths(feed)
    ordered = sorted(feed.connections, key=lambda c: (-c[0], -c[1]))
    files: dict[int, dict] = {}
    summary = {}
    for workplace in workplaces:
        targets, name = workplace_targets(feed, assignment, workplace, (names or {}).get(workplace))
        if not targets:
            summary[str(workplace)] = {"station": None, "rows": 0}
            continue
        decisions: dict[str, int] = {}
        results = scan(feed, targets, paths, ordered, stats=decisions)
        rows = municipality_rows(feed, assignment, results, workplace, municipalities)
        # A separate no-change scan retains direct rides even when a transfer wins all-routes.
        direct_results = scan(feed, targets, {}, ordered, changes=False)
        direct_rows = municipality_rows(feed, assignment, direct_results, workplace, municipalities)
        all_by_bfs = {row[0]: row for row in rows}
        if any(row[2] != 0 or row[0] not in all_by_bfs or row[1] < all_by_bfs[row[0]][1]
               for row in direct_rows):
            raise MatrixError(f"direct-only route is inconsistent with all-routes for {workplace}")
        files[workplace] = {"schema": SCHEMA, "to": workplace, "station": name, "serviceDate": day.isoformat(),
                            "rows": rows, "directRows": direct_rows}
        summary[str(workplace)] = {"station": name, "targetStops": len(targets), "rows": len(rows),
                                    "directRows": len(direct_rows), "tripRuleDecisions": decisions}
    meta = {
        "schema": SCHEMA,
        "serviceDate": day.isoformat(),
        "firstBoardWindow": ["06:30:00", "08:30:00"],
        "capSeconds": CAP_SECONDS,
        "rowFormat": ["homeBfs", "transitSeconds", "transfers", "firstBoardStopName", "firstBoardSeconds"],
        "absence": "no_journey_within_cap_under_model",
        "model": {
            "access": "unmeasured_zero",
            "origins": "every GTFS stop inside the Gemeinde polygon (simplified BFS 2026 boundaries)",
            "changeSeconds": CHANGE_SECONDS,
            "walkRadiusMeters": WALK_RADIUS_M,
            "walkSpeedMetersPerSecond": WALK_SPEED_MPS,
            "walkDetourFactor": WALK_DETOUR,
            "targetComplexRadiusMeters": TARGET_COMPLEX_RADIUS_M,
            **feed.notes,
        },
        "feed": {"url": feed_url, "sha256": sha256(gtfs), "bytes": Path(gtfs).stat().st_size},
        "codeRevision": revision,
        "connections": len(feed.connections),
        "workplaces": summary,
    }
    return meta, files
