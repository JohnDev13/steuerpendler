"""Tests for dated first-board stop to 2026 Gemeinde evidence."""
import csv
import hashlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))
import dated_board_stop_gemeinde as projection


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path, value):
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
    return digest(path)


def topology():
    rings = [
        [[0, 0], [1000, 0], [0, 1000], [-1000, 0], [0, -1000]],
        [[1500, 1500], [1000, 0], [0, 1000], [-1000, 0], [0, -1000]],
        [[2000, 2000], [1000, 0], [0, 1000], [-1000, 0], [0, -1000]],
    ]
    return {"type": "Topology", "arcs": rings, "objects": {"gemeinden": {
        "type": "GeometryCollection", "geometries": [
            {"type": "Polygon", "id": "1", "arcs": [[0]]},
            {"type": "Polygon", "id": "2", "arcs": [[1]]},
            {"type": "Polygon", "id": "3", "arcs": [[2]]},
        ]}}}


def write_index(path, stop_ids):
    database = sqlite3.connect(path)
    database.executescript("""
        CREATE TABLE ride_connections (
          connection_id INTEGER PRIMARY KEY, from_stop_id TEXT NOT NULL);
        CREATE TABLE first_board_events (
          event_id INTEGER PRIMARY KEY,
          connection_id INTEGER NOT NULL UNIQUE REFERENCES ride_connections(connection_id));
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
    """)
    for connection_id, stop_id in enumerate(stop_ids, 1):
        database.execute("INSERT INTO ride_connections VALUES (?, ?)", (connection_id, stop_id))
        database.execute("INSERT INTO first_board_events VALUES (?, ?)", (connection_id, connection_id))
    database.executemany("INSERT INTO metadata VALUES (?, ?)", [
        ("schema_id", "steuerpendler.dated-ride-connections.v1"),
        ("schema_version", "1"), ("service_date", "2026-10-27"),
        ("count.candidate_first_board_events", str(len(stop_ids))),
    ])
    database.commit()
    database.close()
    return digest(path)


def stop_csv(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type", "parent_station"])
    writer.writerows(rows)
    return stream.getvalue()


def write_feed(path, rows, *, duplicate_member=False):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("stops.txt", stop_csv(rows))
        if duplicate_member:
            archive.writestr("stops.txt", stop_csv(rows))
    return digest(path)


class ProjectionTests(unittest.TestCase):
    def fixture(self, directory, board_stops=("A", "B", "C", "D"), feed_rows=None):
        index = directory / "index.sqlite"
        index_hash = write_index(index, board_stops)
        if feed_rows is None:
            feed_rows = [
                ("A", "Assigned", 1, 1, 0, "P"),
                ("B", "Overlap", 2, 2, 0, "P"),
                ("C", "Boundary", 3, 3, 0, "P"),
                ("D", "Outside", 4, 4, 0, "P"),
                ("P", "Parent", 9, 9, 1, ""),
            ]
        feed = directory / "feed.zip"
        feed_hash = write_feed(feed, feed_rows)
        map_path = directory / "map.json"
        map_hash = write_json(map_path, topology())
        gemeinden = directory / "gemeinden.json"
        gemeinden_hash = write_json(gemeinden, {
            "gemeinden": {"1": ["One"], "2": ["Two"], "3": ["Three"]}})
        return index, feed, map_path, gemeinden, (
            index_hash, feed_hash, map_hash, gemeinden_hash)

    def build(self, directory, **kwargs):
        inputs = self.fixture(directory, **kwargs)
        output = directory / "projection.sqlite"
        points = {1: (500, 500), 2: (2200, 2200), 3: (10, 500),
                  4: (5000, 5000), 9: (500, 500)}
        with patch.object(projection, "wgs84_to_lv95",
                          side_effect=lambda lon, lat: points[int(lon)]):
            report = projection.build_projection(
                *inputs[:4], output,
                expected_index_sha256=inputs[4][0],
                expected_gtfs_sha256=inputs[4][1],
                expected_map_sha256=inputs[4][2],
                expected_gemeinden_sha256=inputs[4][3],
                expected_first_board_events=len(kwargs.get("board_stops", ("A", "B", "C", "D"))),
                expected_municipality_count=3)
        return output, report, inputs

    def test_status_partition_schema_lineage_and_no_parent_fanout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output, report, _ = self.build(pathlib.Path(tmp))
            database = sqlite3.connect(output)
            rows = database.execute("""
                SELECT stop_id, parent_station_id, stop_name, location_type,
                       bfs, evidence_status, candidate_bfs_json
                FROM board_stop_gemeinde ORDER BY stop_id
            """).fetchall()
            metadata = dict(database.execute("SELECT key, value FROM metadata"))
            database.close()
        self.assertEqual(rows, [
            ("A", "P", "Assigned", 0, 1, "assigned", "[1]"),
            ("B", "P", "Overlap", 0, None, "ambiguous", "[2,3]"),
            ("C", "P", "Boundary", 0, 1, "boundary_quarantined", "[1]"),
            ("D", "P", "Outside", 0, None, "unassigned", "[]"),
        ])
        self.assertNotIn("P", [row[0] for row in rows])
        self.assertEqual(report["counts"], {
            "first_board_events": 4, "unique_board_stop_ids": 4,
            "assigned": 1, "ambiguous": 1,
            "boundary_quarantined": 1, "unassigned": 1,
        })
        self.assertEqual(sum(report["counts"][key] for key in
            ("assigned", "ambiguous", "boundary_quarantined", "unassigned")), 4)
        self.assertEqual(metadata["schema_id"], "steuerpendler.dated-board-stop-gemeinde")
        self.assertEqual(metadata["unknown_not_negative"], "true")
        self.assertEqual(metadata["residential_access_proven"], "false")
        self.assertEqual(metadata["source_index_sha256"], report["source_index_sha256"])

    def test_output_and_manifest_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            first, _, inputs = self.build(directory)
            first_bytes = first.read_bytes()
            first_manifest = pathlib.Path(f"{first}.manifest.json").read_bytes()
            second = directory / "second.sqlite"
            points = {1: (500, 500), 2: (2200, 2200), 3: (10, 500), 4: (5000, 5000), 9: (500, 500)}
            with patch.object(projection, "wgs84_to_lv95", side_effect=lambda lon, lat: points[int(lon)]):
                projection.build_projection(*inputs[:4], second,
                    expected_index_sha256=inputs[4][0], expected_gtfs_sha256=inputs[4][1],
                    expected_map_sha256=inputs[4][2], expected_gemeinden_sha256=inputs[4][3],
                    expected_first_board_events=4, expected_municipality_count=3)
            second_bytes = second.read_bytes()
            second_manifest = pathlib.Path(f"{second}.manifest.json").read_bytes()
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(first_manifest, second_manifest)

    def test_duplicate_stops_member_and_stop_id_are_rejected(self):
        for duplicate_member in (False, True):
            with self.subTest(duplicate_member=duplicate_member), tempfile.TemporaryDirectory() as tmp:
                directory = pathlib.Path(tmp)
                rows = [("A", "A", 1, 1, 0, ""), ("A", "Again", 1, 1, 0, "")]
                inputs = self.fixture(directory, board_stops=("A",), feed_rows=rows)
                if duplicate_member:
                    inputs[1].unlink()
                    feed_hash = write_feed(inputs[1], rows[:1], duplicate_member=True)
                    inputs = (*inputs[:4], (inputs[4][0], feed_hash, *inputs[4][2:]))
                with self.assertRaisesRegex(projection.ProjectionError,
                        "duplicate stops.txt member" if duplicate_member else "duplicate stop_id"):
                    projection.build_projection(*inputs[:4], directory / "out.sqlite",
                        expected_index_sha256=inputs[4][0], expected_gtfs_sha256=inputs[4][1],
                        expected_map_sha256=inputs[4][2], expected_gemeinden_sha256=inputs[4][3],
                        expected_first_board_events=1, expected_municipality_count=3)

    def test_bad_coordinates_and_missing_board_stop_are_rejected(self):
        cases = [
            ([("A", "A", "nan", 1, 0, "")], "invalid coordinates"),
            ([("OTHER", "Other", 1, 1, 0, "")], "first-board stop absent"),
        ]
        for rows, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                directory = pathlib.Path(tmp)
                inputs = self.fixture(directory, board_stops=("A",), feed_rows=rows)
                with self.assertRaisesRegex(projection.ProjectionError, message):
                    projection.build_projection(*inputs[:4], directory / "out.sqlite",
                        expected_index_sha256=inputs[4][0], expected_gtfs_sha256=inputs[4][1],
                        expected_map_sha256=inputs[4][2], expected_gemeinden_sha256=inputs[4][3],
                        expected_first_board_events=1, expected_municipality_count=3)

    def test_hash_drift_and_publication_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            inputs = self.fixture(directory, board_stops=("A",),
                feed_rows=[("A", "A", 1, 1, 0, "")])
            output = directory / "out.sqlite"
            manifest = pathlib.Path(f"{output}.manifest.json")
            output.write_bytes(b"old database")
            manifest.write_bytes(b"old manifest")
            with self.assertRaisesRegex(projection.ProjectionError, "source index SHA-256 mismatch"):
                projection.build_projection(*inputs[:4], output,
                    expected_index_sha256="0" * 64, expected_gtfs_sha256=inputs[4][1],
                    expected_map_sha256=inputs[4][2], expected_gemeinden_sha256=inputs[4][3],
                    expected_first_board_events=1, expected_municipality_count=3)
            self.assertEqual(output.read_bytes(), b"old database")
            self.assertEqual(manifest.read_bytes(), b"old manifest")

            points = {1: (500, 500)}
            original_replace = projection.os.replace
            calls = 0
            def fail_second(source, target):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("publication failure")
                return original_replace(source, target)
            with patch.object(projection, "wgs84_to_lv95", side_effect=lambda lon, lat: points[int(lon)]), \
                 patch.object(projection.os, "replace", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "publication failure"):
                    projection.build_projection(*inputs[:4], output,
                        expected_index_sha256=inputs[4][0], expected_gtfs_sha256=inputs[4][1],
                        expected_map_sha256=inputs[4][2], expected_gemeinden_sha256=inputs[4][3],
                        expected_first_board_events=1, expected_municipality_count=3)
            self.assertEqual(output.read_bytes(), b"old database")
            self.assertEqual(manifest.read_bytes(), b"old manifest")


if __name__ == "__main__":
    unittest.main()
