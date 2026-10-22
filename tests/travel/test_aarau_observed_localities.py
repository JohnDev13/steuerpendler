"""Synthetic tests for the bounded Aarau observed-locality derivation."""
import gzip
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))
import aarau_observed_localities as observed


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
    return digest(path)


def route(event, *, seconds=61, stop="O1", trip="T1", board=23400):
    return {
        "destinationBfs": 4001,
        "itinerary": {"elapsedSeconds": seconds, "minutes": (seconds + 59) // 60,
                      "legs": [{"boardStopId": stop, "boardSeconds": board,
                                "tripId": trip, "tripInstanceId": trip}]},
        "kind": "route", "origin": {"boardSeconds": board, "stopId": stop,
        "stopSequence": 1, "tripId": trip, "tripInstanceId": trip},
        "schemaVersion": 1, "status": "best_found_unproven",
        "unresolvedReasons": ["transfer_search_missing"],
    }


def write_routes(path, rows, gtfs_hash):
    records = [{"kind": "manifest", "schemaVersion": 1, "coverage": "PARTIAL_DIRECT_ONLY",
                "destinationBfs": 4001, "referenceDate": "2026-10-27",
                "boardingWindowInclusiveSeconds": [23400, 30600],
                "capSecondsInclusive": 1800, "gtfsSha256": gtfs_hash}, *rows,
               {"kind": "summary", "schemaVersion": 1, "coverage": "PARTIAL_DIRECT_ONLY",
                "routeCount": len(rows), "uniqueObservedEvents": len(rows),
                "statusCounts": {"best_found_unproven": len(rows)}}]
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as stream:
            for record in records:
                stream.write((json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return digest(path)


def write_feed(path, stops=(("O1", 1, 1), ("O2", 2, 2), ("O3", 0.01, 5))):
    text = "stop_id,stop_lat,stop_lon\n" + "".join(f"{sid},{lat},{lon}\n" for sid, lat, lon in stops)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("stops.txt", text)
    return digest(path)


def topology():
    # Delta-encoded squares: O1 is safely in BFS 1; O2 is in overlapping BFS 2/3;
    # O3 is only 10 m inside BFS 1 after the coordinate transform is patched.
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


class ObservedLocalitiesTests(unittest.TestCase):
    def fixture(self, directory, rows):
        gtfs = directory / "feed.zip"
        gtfs_hash = write_feed(gtfs)
        routes = directory / "routes.ndjson.gz"
        route_hash = write_routes(routes, rows, gtfs_hash)
        map_path = directory / "map.json"
        map_hash = write_json(map_path, topology())
        gemeinden = directory / "gemeinden.json"
        gemeinden_hash = write_json(gemeinden, {"gemeinden": {"1": ["A"], "2": ["B"], "3": ["C"]}})
        return routes, gtfs, map_path, gemeinden, (route_hash, gtfs_hash, map_hash, gemeinden_hash)

    def derive(self, directory, rows, name="out.json"):
        routes, gtfs, map_path, gemeinden, hashes = self.fixture(directory, rows)
        output = directory / name
        transform = lambda lon, lat: {"O1": (500, 500), "O2": (2200, 2200),
                                     "O3": (10, 500)}[{1: "O1", 2: "O2", 5: "O3"}[int(lon)]]
        with patch.object(observed, "wgs84_to_lv95", side_effect=transform):
            result = observed.derive_localities(routes, gtfs, map_path, gemeinden, output,
                expected_route_sha256=hashes[0], expected_gtfs_sha256=hashes[1],
                expected_map_sha256=hashes[2], expected_gemeinden_sha256=hashes[3],
                expected_municipality_count=3)
        return output, result, (routes, gtfs, map_path, gemeinden, hashes)

    def test_minimum_exact_seconds_ceil_lineage_counts_and_schema(self):
        rows = [route("e2", seconds=120, trip="T2"), route("e1", seconds=61, trip="T1")]
        with tempfile.TemporaryDirectory() as tmp:
            output, result, inputs = self.derive(pathlib.Path(tmp), rows)
            payload = json.loads(output.read_bytes())
        self.assertEqual(set(payload), {"status", "destinationBfs", "serviceDay", "routeSha256",
            "mapSha256", "gtfsSha256", "gemeindenSha256", "accessModel", "unknownNotNegative", "counts", "rows"})
        self.assertEqual(payload["gemeindenSha256"], inputs[-1][3])
        self.assertEqual(payload["status"], "indicative_positive_direct_only")
        self.assertEqual(payload["accessModel"], "unmeasured_external_access_zero")
        self.assertTrue(payload["unknownNotNegative"])
        self.assertEqual(payload["rows"], [{"bfs": 1, "seconds": 61, "minutes": 2,
            "boardingStopId": "O1", "tripId": "T1", "firstBoardSeconds": 23400,
            "observedEvents": 2}])
        self.assertEqual(result["rows"], 1)

    def test_ambiguous_and_near_boundary_stops_are_unknown_not_negative(self):
        rows = [route("a", stop="O2"), route("b", stop="O3", trip="T2")]
        with tempfile.TemporaryDirectory() as tmp:
            output, _, _ = self.derive(pathlib.Path(tmp), rows)
            payload = json.loads(output.read_bytes())
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["counts"]["ambiguousStops"], 1)
        self.assertEqual(payload["counts"]["boundaryQuarantinedStops"], 1)

    def test_duplicate_event_is_rejected(self):
        one = route("a")
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            with self.assertRaisesRegex(observed.DerivationError, "duplicate route event"):
                self.derive(directory, [one, dict(one)])
            self.assertFalse((directory / "out.json").exists())

    def test_broken_source_fact_lineage_is_rejected(self):
        broken = route("a")
        broken["itinerary"]["legs"][0]["boardStopId"] = "OTHER"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(observed.DerivationError, "source-fact lineage"):
                self.derive(pathlib.Path(tmp), [broken])

    def test_hash_tampering_and_alias_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            routes, gtfs, map_path, gemeinden, hashes = self.fixture(directory, [route("a")])
            routes.write_bytes(routes.read_bytes() + b"x")
            with self.assertRaisesRegex(observed.DerivationError, "Route SHA-256 mismatch"):
                observed.derive_localities(routes, gtfs, map_path, gemeinden, directory / "out.json",
                    expected_route_sha256=hashes[0], expected_gtfs_sha256=hashes[1],
                    expected_map_sha256=hashes[2], expected_gemeinden_sha256=hashes[3],
                    expected_municipality_count=3)
            with self.assertRaisesRegex(observed.DerivationError, "aliases input"):
                observed.derive_localities(routes, gtfs, map_path, gemeinden, map_path,
                    expected_route_sha256="x", expected_gtfs_sha256="x", expected_map_sha256="x",
                    expected_gemeinden_sha256="x", expected_municipality_count=3)

    def test_output_bytes_are_deterministic_and_rows_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            first, _, _ = self.derive(directory, [route("a")], "first.json")
            second, _, _ = self.derive(directory, [route("a")], "second.json")
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
