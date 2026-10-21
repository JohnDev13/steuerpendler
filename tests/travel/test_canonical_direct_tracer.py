"""Tests for the bounded Aarau direct Route tracer."""
import gzip
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))
import canonical_direct_tracer as tracer


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_feed(path, trips=None):
    trips = trips or [
        ("R1", "S1", "trip-a"),
        ("R2", "S2", "trip-b"),
        ("R3", "S3", "trip-c"),
        ("R4", "S4", "trip-d"),
    ]
    text = "route_id,service_id,trip_id\n" + "".join(
        f"{route},{service},{trip}\n" for route, service, trip in trips
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("trips.txt", text)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def journey(trip="trip-a", board=23400, arrival=24001, destination="A1", sequence=1):
    services = {"trip-a": "S1", "trip-b": "S2", "trip-c": "S3", "trip-d": "S4"}
    return {
        "arrival_seconds": arrival,
        "boarding_seconds": board,
        "boarding_stop_id": "O1",
        "boarding_stop_sequence": sequence,
        "destination_stop_id": destination,
        "destination_stop_sequence": sequence + 10,
        "service_id": services[trip],
        "transit_seconds": arrival - board,
        "trip_id": trip,
    }


def source(rows, feed_hash):
    return {
        "boarding_window_inclusive": ["06:30:00", "08:30:00"],
        "cap_seconds_inclusive": 1800,
        "destination_children": {"P1": ["A1", "A2"]},
        "direct_only": True,
        "journey_count": len(rows),
        "journeys": rows,
        "service_day": "2026-10-27",
        "source_sha256": feed_hash,
    }


class CanonicalDirectTracerTests(unittest.TestCase):
    def run_trace(self, directory, rows, *, trips=None, name="routes.gz", **kwargs):
        source_path = directory / "source.json"
        feed_path = directory / "feed.zip"
        feed_hash = write_feed(feed_path, trips)
        source_hash = write_json(source_path, source(rows, feed_hash))
        output = directory / name
        report = directory / f"{name}.report.json"
        max_input_rows = kwargs.pop("max_input_rows", 20)
        max_output_rows = kwargs.pop("max_output_rows", 20)
        result = tracer.trace_direct_routes(
            source_path, feed_path, output, report,
            expected_source_sha256=source_hash,
            expected_gtfs_sha256=feed_hash,
            max_input_rows=max_input_rows,
            max_output_rows=max_output_rows,
            **kwargs,
        )
        return output, report, result

    def records(self, path):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream]

    def test_selects_exact_second_minimum_before_ceiling_and_emits_schema_shape(self):
        rows = [journey(arrival=24060, destination="A2"), journey(arrival=24001, destination="A1")]
        with tempfile.TemporaryDirectory() as tmp:
            output, _, result = self.run_trace(pathlib.Path(tmp), rows)
            records = self.records(output)
        route = records[1]
        self.assertEqual(result["route_count"], 1)
        self.assertEqual(route["kind"], "route")
        self.assertEqual(route["status"], "best_found_unproven")
        self.assertEqual(route["unresolvedReasons"], ["transfer_search_missing"])
        self.assertEqual(route["destinationBfs"], 4001)
        self.assertEqual(route["itinerary"]["arrivalSeconds"], 24001)
        self.assertEqual(route["itinerary"]["elapsedSeconds"], 601)
        self.assertEqual(route["itinerary"]["minutes"], 11)
        self.assertEqual(route["itinerary"]["transfers"], [])
        self.assertEqual(route["itinerary"]["legs"][0]["routeId"], "R1")
        self.assertEqual(route["origin"]["tripInstanceId"], "trip-a")
        self.assertEqual(records[0]["kind"], "manifest")
        self.assertEqual(records[-1]["coverage"], "PARTIAL_DIRECT_ONLY")

    def test_inclusive_window_and_cap_boundaries(self):
        rows = [
            journey(trip="trip-a", board=23400, arrival=25200),
            journey(trip="trip-b", board=30600, arrival=32400),
            journey(trip="trip-c", board=23399, arrival=24000),
            journey(trip="trip-d", board=25000, arrival=26801),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output, _, _ = self.run_trace(pathlib.Path(tmp), rows)
            routes = [r for r in self.records(output) if r["kind"] == "route"]
        self.assertEqual([r["origin"]["tripId"] for r in routes], ["trip-a", "trip-b"])
        self.assertEqual([r["itinerary"]["elapsedSeconds"] for r in routes], [1800, 1800])

    def test_wrong_hash_or_malformed_input_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            source_path = directory / "source.json"
            feed_path = directory / "feed.zip"
            feed_hash = write_feed(feed_path)
            write_json(source_path, source([journey()], feed_hash))
            output = directory / "out.gz"
            with self.assertRaisesRegex(tracer.TracerError, "source SHA-256 mismatch"):
                tracer.trace_direct_routes(source_path, feed_path, output, directory / "report.json",
                    expected_source_sha256="0" * 64, expected_gtfs_sha256=feed_hash,
                    max_input_rows=20, max_output_rows=20)
            self.assertFalse(output.exists())

    def test_duplicate_trip_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(tracer.TracerError, "duplicate trip_id"):
                self.run_trace(pathlib.Path(tmp), [journey()], trips=[("R1", "S1", "trip-a"), ("R1", "S1", "trip-a")])

    def test_missing_terminal_route_service_and_metadata_mismatch_are_rejected(self):
        cases = [
            (journey(destination="UNKNOWN"), None, "unknown destination terminal"),
            (journey(), [("", "S1", "trip-a")], "missing route_id"),
            (journey(), [("R1", "", "trip-a")], "missing service_id"),
            (journey(), [("R1", "OTHER", "trip-a")], "service_id mismatch"),
            (journey(), [("R1", "S1", "other")], "missing trip metadata"),
        ]
        for row, trips, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(tracer.TracerError, message):
                    self.run_trace(pathlib.Path(tmp), [row], trips=trips)

    def test_output_and_report_are_byte_deterministic_and_never_claim_proven_status(self):
        rows = [journey(arrival=24001), journey(trip="trip-b", board=25000, arrival=25100)]
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            first, first_report, _ = self.run_trace(directory, rows, name="first.gz")
            second, second_report, _ = self.run_trace(directory, rows, name="second.gz")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_report.read_bytes(), second_report.read_bytes())
            text = gzip.decompress(first.read_bytes()).decode("utf-8")
        self.assertNotIn("fastest_proven", text)
        self.assertNotIn("unreachable_proven", text)
        self.assertNotIn("output_sha256", text)

    def test_bounds_fail_closed_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(tracer.TracerError, "max_input_rows"):
                self.run_trace(pathlib.Path(tmp), [journey(), journey(destination="A2")], max_input_rows=1)

    def test_nonchronological_trip_sequence_is_rejected(self):
        row = journey()
        row["destination_stop_sequence"] = row["boarding_stop_sequence"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(tracer.TracerError, "stop sequence"):
                self.run_trace(pathlib.Path(tmp), [row])

    def test_result_must_name_the_same_feed_as_the_pinned_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed = directory / "feed.zip"
            actual_feed_hash = write_feed(feed)
            source_path = directory / "source.json"
            payload = source([journey()], "0" * 64)
            source_hash = write_json(source_path, payload)
            output = directory / "result.gz"
            with self.assertRaisesRegex(tracer.TracerError, "source GTFS SHA-256 mismatch"):
                tracer.trace_direct_routes(source_path, feed, output, directory / "report.json",
                    expected_source_sha256=source_hash, expected_gtfs_sha256=actual_feed_hash,
                    max_input_rows=20, max_output_rows=20)
            self.assertFalse(output.exists())

    def test_input_output_alias_is_rejected_without_damaging_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed = directory / "feed.zip"
            feed_hash = write_feed(feed)
            source_path = directory / "source.json"
            source_hash = write_json(source_path, source([journey()], feed_hash))
            with self.assertRaisesRegex(tracer.TracerError, "output/report path aliases input"):
                tracer.trace_direct_routes(source_path, feed, source_path, directory / "report.json",
                    expected_source_sha256=source_hash, expected_gtfs_sha256=feed_hash,
                    max_input_rows=20, max_output_rows=20)
            self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), source_hash)


if __name__ == "__main__":
    unittest.main()
