#!/usr/bin/env python3
"""Project exact dated first-board child stops onto 2026 Gemeinde polygons.

The resulting SQLite artifact is stop-level geographic evidence.  It does not
prove residential access, routes, travel times, or negative reachability.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import pathlib
import resource
import shutil
import sqlite3
import tempfile
import time
import zipfile

from aarau_nomination_probe import _decode_topology, point_in_multipolygon, wgs84_to_lv95

EXPECTED_INDEX_SHA256 = "fc98b4195f0275dca6e0443c1fdcb63158f9127b30f5f13583ed285f9b6600fb"
EXPECTED_GTFS_SHA256 = "d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e"
EXPECTED_MAP_SHA256 = "d118a3e8b47c8d76d4fa2587911aa088573d09a934ea484f2f1a60d573aafe14"
EXPECTED_GEMEINDEN_SHA256 = "0cc01b0d5f9fab1a0069394a9b89441ca4264ea0ba7e114e89157c2f748a5928"
EXPECTED_FIRST_BOARD_EVENTS = 373_344
EXPECTED_MUNICIPALITIES = 2_110
SERVICE_DATE = "2026-10-27"
BOUNDARY_QUARANTINE_METRES = 100.0
MAX_INDEX_BYTES = 200_000_000
MAX_GTFS_BYTES = 500_000_000
MAX_STOPS_BYTES = 100_000_000
MAX_MAP_BYTES = 2_000_000
MAX_GEMEINDEN_BYTES = 2_000_000
SCHEMA_ID = "steuerpendler.dated-board-stop-gemeinde"
SCHEMA_VERSION = 1
GENERATOR_VERSION = "1"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]


class ProjectionError(ValueError):
    """An input cannot safely support the projection artifact."""


def _sha256(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _temporary_path(parent, suffix):
    descriptor, name = tempfile.mkstemp(prefix=".dated-board-stop-", suffix=suffix, dir=parent)
    os.close(descriptor)
    return pathlib.Path(name)


def _snapshot(path, expected_hash, limit, label, directory):
    snapshot = _temporary_path(directory, ".snapshot")
    digest = hashlib.sha256()
    copied = 0
    try:
        with pathlib.Path(path).open("rb") as source, snapshot.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                copied += len(chunk)
                if copied > limit:
                    raise ProjectionError(f"{label} exceeds byte limit")
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        actual = digest.hexdigest()
        if actual != expected_hash:
            raise ProjectionError(f"{label} SHA-256 mismatch")
        return snapshot, copied
    except BaseException:
        snapshot.unlink(missing_ok=True)
        raise


def _hashed_json(path, expected_hash, limit, label):
    try:
        raw = pathlib.Path(path).read_bytes()
    except OSError as exc:
        raise ProjectionError(f"unreadable {label}: {exc}") from exc
    if len(raw) > limit:
        raise ProjectionError(f"{label} exceeds byte limit")
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ProjectionError(f"{label} SHA-256 mismatch")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectionError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectionError(f"invalid {label} JSON root")
    return value, len(raw)


def _bbox(multipolygon):
    points = [point for polygon in multipolygon for ring in polygon for point in ring]
    if not points:
        raise ProjectionError("empty Gemeinde polygon")
    return (min(point[0] for point in points), min(point[1] for point in points),
            max(point[0] for point in points), max(point[1] for point in points))


def _point_segment_distance(point, start, end):
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    fraction = max(0.0, min(1.0,
        ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + fraction * dx),
                      py - (y1 + fraction * dy))


def _boundary_distance(point, multipolygon):
    segments = ((start, end) for polygon in multipolygon for ring in polygon
                for start, end in zip(ring, ring[1:]))
    try:
        return min(_point_segment_distance(point, start, end)
                   for start, end in segments)
    except ValueError as exc:
        raise ProjectionError("Gemeinde polygon has no boundary segments") from exc


def _load_authorities(map_path, gemeinden_path, expected_map_hash,
                      expected_gemeinden_hash, expected_count):
    authority, gemeinden_bytes = _hashed_json(
        gemeinden_path, expected_gemeinden_hash, MAX_GEMEINDEN_BYTES, "Gemeinden")
    gemeinden = authority.get("gemeinden")
    if not isinstance(gemeinden, dict) or len(gemeinden) != expected_count:
        raise ProjectionError("Gemeinden authority count mismatch")
    wanted = set(gemeinden)
    if any(not isinstance(key, str) or not key.isdigit() for key in wanted):
        raise ProjectionError("invalid Gemeinde BFS ID")

    topology, map_bytes = _hashed_json(
        map_path, expected_map_hash, MAX_MAP_BYTES, "Map")
    try:
        geometries = topology["objects"]["gemeinden"]["geometries"]
        wanted_geometries = [str(item["id"]) for item in geometries
                             if str(item["id"]) in wanted]
        polygons = _decode_topology(topology, wanted)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ProjectionError(f"invalid Map topology: {exc}") from exc
    if len(wanted_geometries) != len(set(wanted_geometries)):
        raise ProjectionError("duplicate Gemeinde geometry")
    if set(polygons) != wanted or set(wanted_geometries) != wanted:
        raise ProjectionError("Map does not contain the exact Gemeinde authority")
    boxes = {bfs: _bbox(shape) for bfs, shape in polygons.items()}
    return polygons, boxes, map_bytes, gemeinden_bytes


def _create_database(path):
    database = sqlite3.connect(path)
    database.execute("PRAGMA page_size = 4096")
    database.execute("PRAGMA journal_mode = DELETE")
    database.execute("PRAGMA synchronous = FULL")
    database.execute("PRAGMA temp_store = FILE")
    database.execute("PRAGMA cache_size = -65536")
    database.execute("PRAGMA application_id = 1398035024")
    database.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    database.executescript("""
        CREATE TABLE board_stop_gemeinde (
            stop_id TEXT PRIMARY KEY,
            parent_station_id TEXT,
            stop_name TEXT NOT NULL,
            location_type INTEGER NOT NULL,
            stop_lat REAL NOT NULL,
            stop_lon REAL NOT NULL,
            lv95_east REAL NOT NULL,
            lv95_north REAL NOT NULL,
            first_board_event_count INTEGER NOT NULL CHECK (first_board_event_count > 0),
            bfs INTEGER,
            candidate_bfs_json TEXT NOT NULL,
            boundary_distance_metres REAL,
            evidence_status TEXT NOT NULL CHECK (evidence_status IN
                ('assigned', 'ambiguous', 'boundary_quarantined', 'unassigned')),
            CHECK ((evidence_status IN ('assigned', 'boundary_quarantined')) = (bfs IS NOT NULL))
        ) WITHOUT ROWID;
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TEMP TABLE wanted_stops (
            stop_id TEXT PRIMARY KEY,
            event_count INTEGER NOT NULL
        ) WITHOUT ROWID;
        CREATE TEMP TABLE seen_gtfs_stops (
            stop_id TEXT PRIMARY KEY
        ) WITHOUT ROWID;
        CREATE TEMP TABLE selected_stops (
            stop_id TEXT PRIMARY KEY,
            parent_station_id TEXT,
            stop_name TEXT NOT NULL,
            location_type INTEGER NOT NULL,
            stop_lat REAL NOT NULL,
            stop_lon REAL NOT NULL,
            lv95_east REAL NOT NULL,
            lv95_north REAL NOT NULL
        ) WITHOUT ROWID;
    """)
    return database


def _validate_index(snapshot, database, expected_events):
    source = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
    try:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ProjectionError("source index integrity check failed")
        tables = {row[0] for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"ride_connections", "first_board_events", "metadata"} <= tables:
            raise ProjectionError("source index schema mismatch")
        metadata = dict(source.execute("SELECT key, value FROM metadata"))
        if metadata.get("schema_id") != "steuerpendler.dated-ride-connections.v1":
            raise ProjectionError("source index schema_id mismatch")
        if metadata.get("schema_version") != "1":
            raise ProjectionError("source index schema_version mismatch")
        if metadata.get("service_date") != SERVICE_DATE:
            raise ProjectionError("source index service_date mismatch")
        event_count = source.execute("SELECT COUNT(*) FROM first_board_events").fetchone()[0]
        if event_count != expected_events:
            raise ProjectionError(
                f"first-board event count mismatch: expected {expected_events}, got {event_count}")
        declared = metadata.get("count.candidate_first_board_events")
        if declared is None or int(declared) != event_count:
            raise ProjectionError("source index declared first-board count mismatch")
        rows = source.execute("""
            SELECT c.from_stop_id, COUNT(*)
            FROM first_board_events AS b
            JOIN ride_connections AS c ON c.connection_id = b.connection_id
            GROUP BY c.from_stop_id ORDER BY c.from_stop_id
        """)
        database.executemany("INSERT INTO wanted_stops VALUES (?, ?)", rows)
        unique_count = database.execute("SELECT COUNT(*) FROM wanted_stops").fetchone()[0]
        if not unique_count:
            raise ProjectionError("source index has no first-board stops")
        return event_count, unique_count
    except (sqlite3.Error, ValueError) as exc:
        if isinstance(exc, ProjectionError):
            raise
        raise ProjectionError(f"invalid source index: {exc}") from exc
    finally:
        source.close()


def _stream_stops(snapshot, database):
    try:
        with zipfile.ZipFile(snapshot) as archive:
            members = [item for item in archive.infolist() if item.filename == "stops.txt"]
            if len(members) != 1:
                raise ProjectionError("duplicate stops.txt member" if members else "GTFS missing stops.txt")
            if members[0].file_size > MAX_STOPS_BYTES:
                raise ProjectionError("GTFS stops.txt exceeds byte limit")
            with archive.open(members[0]) as raw, io.TextIOWrapper(
                    raw, encoding="utf-8-sig", newline="") as text:
                reader = csv.DictReader(text)
                required = {"stop_id", "stop_name", "stop_lat", "stop_lon",
                            "location_type", "parent_station"}
                if not required <= set(reader.fieldnames or ()):
                    raise ProjectionError("invalid GTFS stops.txt columns")
                for row_number, row in enumerate(reader, 2):
                    stop_id = row["stop_id"]
                    if not stop_id:
                        raise ProjectionError(f"empty stop_id at stops.txt row {row_number}")
                    try:
                        database.execute("INSERT INTO seen_gtfs_stops VALUES (?)", (stop_id,))
                    except sqlite3.IntegrityError as exc:
                        raise ProjectionError(f"duplicate stop_id in stops.txt: {stop_id}") from exc
                    try:
                        lat = float(row["stop_lat"])
                        lon = float(row["stop_lon"])
                        location_type = int(row["location_type"] or 0)
                    except (TypeError, ValueError) as exc:
                        raise ProjectionError(f"invalid coordinates for stop_id {stop_id}") from exc
                    if (not math.isfinite(lat) or not math.isfinite(lon)
                            or not -90 <= lat <= 90 or not -180 <= lon <= 180):
                        raise ProjectionError(f"invalid coordinates for stop_id {stop_id}")
                    wanted = database.execute(
                        "SELECT 1 FROM wanted_stops WHERE stop_id=?", (stop_id,)).fetchone()
                    if wanted is None:
                        continue
                    east, north = wgs84_to_lv95(lon, lat)
                    if not math.isfinite(east) or not math.isfinite(north):
                        raise ProjectionError(f"invalid projected coordinates for stop_id {stop_id}")
                    database.execute("INSERT INTO selected_stops VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                        stop_id, row["parent_station"] or None, row["stop_name"], location_type,
                        lat, lon, east, north))
    except (OSError, UnicodeError, csv.Error, zipfile.BadZipFile) as exc:
        raise ProjectionError(f"unreadable GTFS stops.txt: {exc}") from exc
    missing = database.execute("""
        SELECT w.stop_id FROM wanted_stops AS w
        LEFT JOIN selected_stops AS s ON s.stop_id=w.stop_id
        WHERE s.stop_id IS NULL ORDER BY w.stop_id LIMIT 1
    """).fetchone()
    if missing:
        raise ProjectionError(f"first-board stop absent from GTFS stops.txt: {missing[0]}")


def _assign_stops(database, polygons, boxes):
    counts = {status: 0 for status in
              ("assigned", "ambiguous", "boundary_quarantined", "unassigned")}
    rows = database.execute("""
        SELECT s.stop_id, s.parent_station_id, s.stop_name, s.location_type,
               s.stop_lat, s.stop_lon, s.lv95_east, s.lv95_north, w.event_count
        FROM selected_stops AS s JOIN wanted_stops AS w USING (stop_id)
        ORDER BY s.stop_id
    """)
    for row in rows:
        point = (row[6], row[7])
        matches = sorted((bfs for bfs, shape in polygons.items()
            if boxes[bfs][0] <= point[0] <= boxes[bfs][2]
            and boxes[bfs][1] <= point[1] <= boxes[bfs][3]
            and point_in_multipolygon(point, shape)), key=int)
        bfs = None
        boundary_distance = None
        if not matches:
            status = "unassigned"
        elif len(matches) > 1:
            status = "ambiguous"
        else:
            bfs = int(matches[0])
            boundary_distance = _boundary_distance(point, polygons[matches[0]])
            status = ("boundary_quarantined"
                      if boundary_distance <= BOUNDARY_QUARANTINE_METRES else "assigned")
        counts[status] += 1
        database.execute("""
            INSERT INTO board_stop_gemeinde VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (*row, bfs, json.dumps([int(item) for item in matches], separators=(",", ":")),
              boundary_distance, status))
    return counts


def _write_manifest(path, payload):
    data = (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")
    temporary = _temporary_path(path.parent, ".manifest")
    try:
        with temporary.open("wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _backup(path):
    if not path.exists():
        return None
    backup = _temporary_path(path.parent, ".backup")
    shutil.copyfile(path, backup)
    with backup.open("rb") as stream:
        os.fsync(stream.fileno())
    return backup


def _publish_pair(database_temporary, output_path, manifest_temporary, manifest_path):
    database_backup = _backup(output_path)
    manifest_backup = _backup(manifest_path)
    database_published = False
    manifest_published = False
    try:
        os.replace(database_temporary, output_path)
        database_published = True
        os.replace(manifest_temporary, manifest_path)
        manifest_published = True
    except BaseException:
        if database_published:
            if database_backup is None:
                output_path.unlink(missing_ok=True)
            else:
                os.replace(database_backup, output_path)
                database_backup = None
        if manifest_published:
            if manifest_backup is None:
                manifest_path.unlink(missing_ok=True)
            else:
                os.replace(manifest_backup, manifest_path)
                manifest_backup = None
        raise
    finally:
        database_temporary.unlink(missing_ok=True)
        manifest_temporary.unlink(missing_ok=True)
        if database_backup is not None:
            database_backup.unlink(missing_ok=True)
        if manifest_backup is not None:
            manifest_backup.unlink(missing_ok=True)


def build_projection(index_path, gtfs_path, map_path, gemeinden_path, output_path, *,
                     expected_index_sha256, expected_gtfs_sha256,
                     expected_map_sha256, expected_gemeinden_sha256,
                     expected_first_board_events=EXPECTED_FIRST_BOARD_EVENTS,
                     expected_municipality_count=EXPECTED_MUNICIPALITIES):
    """Build and atomically publish a deterministic stop-evidence SQLite pair."""
    paths = [pathlib.Path(value) for value in
             (index_path, gtfs_path, map_path, gemeinden_path, output_path)]
    index_path, gtfs_path, map_path, gemeinden_path, output_path = paths
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ProjectionError("output aliases input")
    try:
        output_path.resolve().relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        raise ProjectionError("output must be outside the Git worktree")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = pathlib.Path(f"{output_path}.manifest.json")

    index_snapshot = gtfs_snapshot = database_path = manifest_temporary = None
    database = None
    try:
        index_snapshot, index_bytes = _snapshot(
            index_path, expected_index_sha256, MAX_INDEX_BYTES,
            "source index", output_path.parent)
        gtfs_snapshot, gtfs_bytes = _snapshot(
            gtfs_path, expected_gtfs_sha256, MAX_GTFS_BYTES,
            "GTFS", output_path.parent)
        polygons, boxes, map_bytes, gemeinden_bytes = _load_authorities(
            map_path, gemeinden_path, expected_map_sha256,
            expected_gemeinden_sha256, expected_municipality_count)
        database_path = _temporary_path(output_path.parent, ".sqlite")
        database = _create_database(database_path)
        event_count, unique_count = _validate_index(
            index_snapshot, database, expected_first_board_events)
        _stream_stops(gtfs_snapshot, database)
        status_counts = _assign_stops(database, polygons, boxes)
        counts = {
            "first_board_events": event_count,
            "unique_board_stop_ids": unique_count,
            **status_counts,
        }
        if sum(status_counts.values()) != unique_count:
            raise ProjectionError("evidence statuses do not partition first-board stops")
        metadata = {
            "boundary_quarantine_metres": str(int(BOUNDARY_QUARANTINE_METRES)),
            **{f"count.{key}": str(value) for key, value in counts.items()},
            "generator_version": GENERATOR_VERSION,
            "gemeinden_sha256": expected_gemeinden_sha256,
            "gtfs_sha256": expected_gtfs_sha256,
            "map_coordinates_simplified": "true",
            "map_sha256": expected_map_sha256,
            "residential_access_proven": "false",
            "schema_id": SCHEMA_ID,
            "schema_version": str(SCHEMA_VERSION),
            "service_date": SERVICE_DATE,
            "source_index_sha256": expected_index_sha256,
            "unknown_not_negative": "true",
        }
        database.executemany("INSERT INTO metadata VALUES (?, ?)", sorted(metadata.items()))
        database.commit()
        database.execute("VACUUM")
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ProjectionError("output SQLite integrity check failed")
        database.close()
        database = None
        output_sha256 = _sha256(database_path)
        output_bytes = database_path.stat().st_size
        manifest = {
            "counts": counts,
            "format": "sqlite3",
            "generator_version": GENERATOR_VERSION,
            "input_bytes": {"source_index": index_bytes, "gtfs": gtfs_bytes,
                            "map": map_bytes, "gemeinden": gemeinden_bytes},
            "inputs": {"source_index_sha256": expected_index_sha256,
                       "gtfs_sha256": expected_gtfs_sha256,
                       "map_sha256": expected_map_sha256,
                       "gemeinden_sha256": expected_gemeinden_sha256},
            "limitations": [
                "A stop in one polygon does not prove access from all residences.",
                "Unlisted Gemeinden and quarantined stops remain unknown, never negative.",
                "No walking, entrance-to-platform, route, or travel-time evidence is present.",
                "Parent stations are preserved as lineage and are not expanded into boarding rights.",
            ],
            "output_bytes": output_bytes,
            "output_sha256": output_sha256,
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "service_date": SERVICE_DATE,
        }
        manifest_temporary = _write_manifest(manifest_path, manifest)
        _publish_pair(database_path, output_path, manifest_temporary, manifest_path)
        database_path = manifest_temporary = None
        return {**manifest, "source_index_sha256": expected_index_sha256}
    except (sqlite3.Error, OSError) as exc:
        if isinstance(exc, ProjectionError):
            raise
        raise
    finally:
        if database is not None:
            database.close()
        for path in (index_snapshot, gtfs_snapshot, database_path, manifest_temporary):
            if path is not None:
                path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    parser.add_argument("--gtfs", required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument("--gemeinden", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-index-sha256", default=EXPECTED_INDEX_SHA256)
    parser.add_argument("--expected-gtfs-sha256", default=EXPECTED_GTFS_SHA256)
    parser.add_argument("--expected-map-sha256", default=EXPECTED_MAP_SHA256)
    parser.add_argument("--expected-gemeinden-sha256", default=EXPECTED_GEMEINDEN_SHA256)
    parser.add_argument("--expected-first-board-events", type=int,
                        default=EXPECTED_FIRST_BOARD_EVENTS)
    args = parser.parse_args()
    started = time.monotonic()
    report = build_projection(
        args.index, args.gtfs, args.map, args.gemeinden, args.output,
        expected_index_sha256=args.expected_index_sha256,
        expected_gtfs_sha256=args.expected_gtfs_sha256,
        expected_map_sha256=args.expected_map_sha256,
        expected_gemeinden_sha256=args.expected_gemeinden_sha256,
        expected_first_board_events=args.expected_first_board_events)
    report["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["wall_seconds"] = time.monotonic() - started
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
