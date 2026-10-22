#!/usr/bin/env python3
"""Derive a bounded, indicative Aarau direct-positive Gemeinde preview."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import pathlib
import tempfile
import zipfile

from aarau_nomination_probe import _decode_topology, point_in_multipolygon, wgs84_to_lv95

EXPECTED_ROUTE_SHA256 = "5f9c6c8648f87ff88cf0c1dc4f158d471a6e55f57ed28cd53e649940d1d4b89e"
EXPECTED_GTFS_SHA256 = "d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e"
EXPECTED_MAP_SHA256 = "d118a3e8b47c8d76d4fa2587911aa088573d09a934ea484f2f1a60d573aafe14"
EXPECTED_GEMEINDEN_SHA256 = "0cc01b0d5f9fab1a0069394a9b89441ca4264ea0ba7e114e89157c2f748a5928"
DESTINATION_BFS = 4001
SERVICE_DAY = "2026-10-27"
WINDOW = [23400, 30600]
CAP_SECONDS = 1800
MAX_ROUTE_COMPRESSED_BYTES = 4_000_000
MAX_ROUTE_DECOMPRESSED_BYTES = 8_000_000
MAX_MAP_BYTES = 2_000_000
MAX_GTFS_BYTES = 500_000_000
BOUNDARY_QUARANTINE_METRES = 100.0
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]


class DerivationError(ValueError):
    """An input cannot safely support this derived preview."""


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _bounded_hashed_bytes(path, limit, label, expected_hash):
    try:
        with pathlib.Path(path).open("rb") as source:
            data = source.read(limit + 1)
    except OSError as exc:
        raise DerivationError(f"unreadable {label}: {exc}") from exc
    if len(data) > limit:
        raise DerivationError(f"{label} exceeds byte limit")
    if _sha256(data) != expected_hash:
        raise DerivationError(f"{label} SHA-256 mismatch")
    return data


def _require_int(value, label):
    if type(value) is not int:
        raise DerivationError(f"invalid {label}")
    return value


def _load_routes(path, expected_hash, expected_gtfs_hash):
    compressed = _bounded_hashed_bytes(
        path, MAX_ROUTE_COMPRESSED_BYTES, "Route", expected_hash)
    records = []
    total = 0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
            while True:
                line = stream.readline(MAX_ROUTE_DECOMPRESSED_BYTES - total + 1)
                if not line:
                    break
                total += len(line)
                if total > MAX_ROUTE_DECOMPRESSED_BYTES:
                    raise DerivationError("Route decompressed bytes exceed limit")
                if not line.strip():
                    raise DerivationError("Route contains an empty record")
                records.append(json.loads(line.decode("utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DerivationError(f"invalid Route gzip: {exc}") from exc
    if len(records) < 2 or not all(isinstance(record, dict) for record in records):
        raise DerivationError("Route manifest/footer missing")
    manifest, summary = records[0], records[-1]
    routes = records[1:-1]
    expected_manifest = {
        "kind": "manifest", "schemaVersion": 1, "coverage": "PARTIAL_DIRECT_ONLY",
        "destinationBfs": DESTINATION_BFS, "referenceDate": SERVICE_DAY,
        "boardingWindowInclusiveSeconds": WINDOW, "capSecondsInclusive": CAP_SECONDS,
        "gtfsSha256": expected_gtfs_hash,
    }
    for key, value in expected_manifest.items():
        if manifest.get(key) != value:
            raise DerivationError(f"Route manifest {key} mismatch")
    if summary.get("kind") != "summary" or summary.get("schemaVersion") != 1:
        raise DerivationError("Route footer mismatch")
    if summary.get("coverage") != "PARTIAL_DIRECT_ONLY":
        raise DerivationError("Route footer coverage mismatch")
    if summary.get("routeCount") != len(routes) or summary.get("uniqueObservedEvents") != len(routes):
        raise DerivationError("Route footer count mismatch")
    if summary.get("statusCounts") != {"best_found_unproven": len(routes)}:
        raise DerivationError("Route footer status count mismatch")

    events = []
    seen = set()
    for index, record in enumerate(routes):
        if record.get("kind") != "route" or record.get("schemaVersion") != 1:
            raise DerivationError(f"route {index}: invalid record kind/schema")
        if record.get("status") != "best_found_unproven" or record.get("destinationBfs") != DESTINATION_BFS:
            raise DerivationError(f"route {index}: invalid status/destination")
        origin = record.get("origin")
        itinerary = record.get("itinerary")
        if not isinstance(origin, dict) or not isinstance(itinerary, dict):
            raise DerivationError(f"route {index}: missing lineage")
        stop = origin.get("stopId")
        trip = origin.get("tripId")
        trip_instance = origin.get("tripInstanceId")
        if (not isinstance(stop, str) or not stop or not isinstance(trip, str) or not trip
                or not isinstance(trip_instance, str) or not trip_instance):
            raise DerivationError(f"route {index}: invalid origin lineage")
        board = _require_int(origin.get("boardSeconds"), f"route {index} boardSeconds")
        sequence = _require_int(origin.get("stopSequence"), f"route {index} stopSequence")
        seconds = _require_int(itinerary.get("elapsedSeconds"), f"route {index} elapsedSeconds")
        if not WINDOW[0] <= board <= WINDOW[1] or not 0 <= seconds <= CAP_SECONDS:
            raise DerivationError(f"route {index}: out of bounds")
        if itinerary.get("minutes") != (seconds + 59) // 60:
            raise DerivationError(f"route {index}: minute rounding mismatch")
        legs = itinerary.get("legs")
        if not isinstance(legs, list) or not legs or not isinstance(legs[0], dict):
            raise DerivationError(f"route {index}: missing source leg")
        leg = legs[0]
        if (leg.get("boardStopId"), leg.get("boardSeconds"), leg.get("tripId"),
                leg.get("tripInstanceId")) != (stop, board, trip, trip_instance):
            raise DerivationError(f"route {index}: source-fact lineage mismatch")
        event_id = (trip_instance, stop, sequence, board)
        if event_id in seen:
            raise DerivationError(f"duplicate route event: {event_id}")
        seen.add(event_id)
        events.append({"stop": stop, "trip": trip, "board": board,
                       "seconds": seconds, "event_id": event_id})
    return events


def _load_json_authority(path, expected_hash, label, limit=MAX_MAP_BYTES):
    raw = _bounded_hashed_bytes(path, limit, label, expected_hash)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DerivationError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise DerivationError(f"invalid {label} JSON root")
    return value


def _snapshot_stop_coordinates(path, expected_hash, wanted):
    coordinates = {}
    scratch = os.environ.get("TMPDIR")
    try:
        with tempfile.TemporaryFile(dir=scratch) as snapshot, pathlib.Path(path).open("rb") as source:
            digest = hashlib.sha256()
            copied = 0
            while chunk := source.read(1024 * 1024):
                copied += len(chunk)
                if copied > MAX_GTFS_BYTES:
                    raise DerivationError("GTFS exceeds snapshot byte limit")
                digest.update(chunk)
                snapshot.write(chunk)
            if digest.hexdigest() != expected_hash:
                raise DerivationError("GTFS SHA-256 mismatch")
            snapshot.seek(0)
            with zipfile.ZipFile(snapshot) as archive:
                if "stops.txt" not in archive.namelist():
                    raise DerivationError("GTFS missing stops.txt")
                if archive.getinfo("stops.txt").file_size > MAX_GTFS_BYTES:
                    raise DerivationError("GTFS stops.txt exceeds byte limit")
                with archive.open("stops.txt") as raw, io.TextIOWrapper(
                        raw, encoding="utf-8-sig", newline="") as text:
                    reader = csv.DictReader(text)
                    required = {"stop_id", "stop_lon", "stop_lat"}
                    if not required <= set(reader.fieldnames or ()):
                        raise DerivationError("invalid GTFS stops.txt columns")
                    for row in reader:
                        stop = row["stop_id"]
                        if stop not in wanted:
                            continue
                        if stop in coordinates:
                            raise DerivationError(f"duplicate observed stop in stops.txt: {stop}")
                        try:
                            point = wgs84_to_lv95(float(row["stop_lon"]), float(row["stop_lat"]))
                        except (TypeError, ValueError) as exc:
                            raise DerivationError(f"invalid coordinates for observed stop: {stop}") from exc
                        if not all(math.isfinite(value) for value in point):
                            raise DerivationError(f"non-finite coordinates for observed stop: {stop}")
                        coordinates[stop] = point
    except (OSError, UnicodeError, csv.Error, zipfile.BadZipFile) as exc:
        raise DerivationError(f"unreadable GTFS stops.txt: {exc}") from exc
    missing = sorted(wanted - set(coordinates))
    if missing:
        raise DerivationError(f"observed stop absent from GTFS stops.txt: {missing[0]}")
    return coordinates


def _bbox(multipolygon):
    points = [point for polygon in multipolygon for ring in polygon for point in ring]
    return (min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))


def _point_segment_distance(point, start, end):
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _boundary_distance(point, multipolygon):
    return min(_point_segment_distance(point, a, b)
               for polygon in multipolygon for ring in polygon for a, b in zip(ring, ring[1:]))


def _assign(coordinates, polygons):
    boxes = {bfs: _bbox(shape) for bfs, shape in polygons.items()}
    assignments = {}
    counts = {"ambiguousStops": 0, "boundaryQuarantinedStops": 0, "unassignedStops": 0}
    for stop, point in coordinates.items():
        matches = [bfs for bfs, shape in polygons.items()
                   if boxes[bfs][0] <= point[0] <= boxes[bfs][2]
                   and boxes[bfs][1] <= point[1] <= boxes[bfs][3]
                   and point_in_multipolygon(point, shape)]
        if len(matches) > 1:
            counts["ambiguousStops"] += 1
        elif not matches:
            counts["unassignedStops"] += 1
        elif _boundary_distance(point, polygons[matches[0]]) <= BOUNDARY_QUARANTINE_METRES:
            counts["boundaryQuarantinedStops"] += 1
        else:
            assignments[stop] = matches[0]
    return assignments, counts


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def derive_localities(route_path, gtfs_path, map_path, gemeinden_path, output_path, *,
                      expected_route_sha256, expected_gtfs_sha256, expected_map_sha256,
                      expected_gemeinden_sha256, expected_municipality_count=2110):
    """Write the deterministic indicative-positive locality JSON."""
    paths = [pathlib.Path(value) for value in
             (route_path, gtfs_path, map_path, gemeinden_path, output_path)]
    route_path, gtfs_path, map_path, gemeinden_path, output_path = paths
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise DerivationError("output aliases input")
    try:
        output_path.resolve().relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        raise DerivationError("output must be outside the Git worktree")

    events = _load_routes(route_path, expected_route_sha256, expected_gtfs_sha256)
    authority = _load_json_authority(
        gemeinden_path, expected_gemeinden_sha256, "Gemeinden")
    gemeinden = authority.get("gemeinden")
    if not isinstance(gemeinden, dict) or len(gemeinden) != expected_municipality_count:
        raise DerivationError("Gemeinden authority count mismatch")
    wanted = set(gemeinden)
    if any(not key.isdigit() for key in wanted):
        raise DerivationError("invalid Gemeinde BFS ID")
    topology = _load_json_authority(map_path, expected_map_sha256, "Map")
    try:
        polygons = _decode_topology(topology, wanted)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise DerivationError(f"invalid Map topology: {exc}") from exc
    if set(polygons) != wanted:
        raise DerivationError("Map does not contain the exact Gemeinde authority")

    observed_stops = {event["stop"] for event in events}
    coordinates = _snapshot_stop_coordinates(gtfs_path, expected_gtfs_sha256, observed_stops)
    assignments, assignment_counts = _assign(coordinates, polygons)
    if len(assignments) + sum(assignment_counts.values()) != len(observed_stops):
        raise DerivationError("stop assignment counts do not partition source stops")
    grouped = {}
    for event in events:
        bfs = assignments.get(event["stop"])
        if bfs is None:
            continue
        group = grouped.setdefault(bfs, {"count": 0, "best": None})
        group["count"] += 1
        candidate = (event["seconds"], event["event_id"], event)
        if group["best"] is None or candidate[:2] < group["best"][:2]:
            group["best"] = candidate
    rows = []
    for bfs in sorted(grouped, key=int):
        event = grouped[bfs]["best"][2]
        rows.append({"bfs": int(bfs), "seconds": event["seconds"],
                     "minutes": (event["seconds"] + 59) // 60,
                     "boardingStopId": event["stop"], "tripId": event["trip"],
                     "firstBoardSeconds": event["board"],
                     "observedEvents": grouped[bfs]["count"]})
    counts = {
        "sourceEvents": len(events), "sourceStops": len(observed_stops),
        "assignedStops": len(assignments), "assignedMunicipalities": len(rows),
        "ambiguousStops": assignment_counts["ambiguousStops"],
        "boundaryQuarantinedStops": assignment_counts["boundaryQuarantinedStops"],
        "unassignedStops": assignment_counts["unassignedStops"],
        "municipalityAuthority": len(wanted), "capSecondsInclusive": CAP_SECONDS,
        "boardingWindowInclusiveSeconds": WINDOW,
        "mapCoordinatesSimplified": True,
        "mapBoundaryQuarantineMetres": int(BOUNDARY_QUARANTINE_METRES),
    }
    payload = {
        "status": "indicative_positive_direct_only", "destinationBfs": DESTINATION_BFS,
        "serviceDay": SERVICE_DAY, "routeSha256": expected_route_sha256,
        "mapSha256": expected_map_sha256, "gtfsSha256": expected_gtfs_sha256,
        "gemeindenSha256": expected_gemeinden_sha256,
        "accessModel": "unmeasured_external_access_zero", "unknownNotNegative": True,
        "counts": counts, "rows": rows,
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True).encode("utf-8") + b"\n"
    _atomic_write(output_path, data)
    return {"rows": len(rows), "bytes": len(data), "sha256": _sha256(data), **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", required=True)
    parser.add_argument("--gtfs", required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument("--gemeinden", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = derive_localities(
        args.route, args.gtfs, args.map, args.gemeinden, args.output,
        expected_route_sha256=EXPECTED_ROUTE_SHA256,
        expected_gtfs_sha256=EXPECTED_GTFS_SHA256,
        expected_map_sha256=EXPECTED_MAP_SHA256,
        expected_gemeinden_sha256=EXPECTED_GEMEINDEN_SHA256)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
