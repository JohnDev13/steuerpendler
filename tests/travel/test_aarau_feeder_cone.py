"""Synthetic tests for the bounded Aarau feeder candidate cone."""
import datetime as dt
import gzip
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))
import aarau_feeder_cone as cone

DAY = dt.date(2026, 10, 27)


def write_fixture(directory):
    feed = directory / "feed.zip"
    tables = {
        "stops.txt": """stop_id,stop_name,location_type,parent_station
P1,Origin parent,1,
P2,Hub parent,1,
O630,Origin lower,0,P1
O830,Origin upper,0,P1
H1,Positive hub,0,P2
H2,Not a positive hub,0,P2
H3,Over-limit positive hub,0,P2
M,Intermediate,0,P1
""",
        "calendar.txt": """service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
BASE,0,1,0,0,0,0,0,20261001,20261031
REM,0,1,0,0,0,0,0,20261001,20261031
ADD,0,0,0,0,0,0,0,20261001,20261031
""",
        "calendar_dates.txt": """service_id,date,exception_type
REM,20261027,2
ADD,20261027,1
""",
        "trips.txt": """route_id,service_id,trip_id
R,BASE,lower
R,ADD,upper
R,BASE,over
R,BASE,late-hub
R,BASE,pickup-blocked
R,BASE,drop-blocked
R,REM,removed
R,BASE,unused-hub
R,BASE,freq
R,BASE,malformed
""",
        "frequencies.txt": """trip_id,start_time,end_time,headway_secs,exact_times
freq,06:00:00,09:00:00,600,0
""",
        "stop_times.txt": """trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type,timepoint
lower,06:30:00,06:30:00,O630,1,0,0,1
lower,06:35:00,06:35:00,M,2,0,0,1
lower,06:40:00,06:40:00,H1,3,0,0,1
upper,08:30:00,08:30:00,O830,4,0,0,1
upper,08:35:00,08:35:00,H1,9,0,0,1
over,06:59:59,06:59:59,O630,1,0,0,1
over,07:00:00,07:00:00,H3,2,0,0,1
late-hub,06:30:00,06:30:00,O630,1,0,0,1
late-hub,07:01:00,07:01:00,H1,2,0,0,1
pickup-blocked,06:30:00,06:30:00,O630,1,1,0,1
pickup-blocked,06:40:00,06:40:00,H1,2,0,0,1
drop-blocked,06:30:00,06:30:00,O630,1,0,0,1
drop-blocked,06:40:00,06:40:00,H1,2,0,1,1
removed,06:30:00,06:30:00,O630,1,0,0,1
removed,06:40:00,06:40:00,H1,2,0,0,1
unused-hub,06:30:00,06:30:00,O630,1,0,0,1
unused-hub,06:40:00,06:40:00,H2,2,0,0,1
freq,06:30:00,06:30:00,O630,1,0,0,1
freq,06:40:00,06:40:00,H1,2,0,0,1
malformed,06:30:00,06:30:00,O630,1,0,0,1
malformed,bad,06:35:00,M,2,0,0,1
malformed,06:40:00,06:40:00,H1,3,0,0,1
""",
    }
    with zipfile.ZipFile(feed, "w") as archive:
        for name in sorted(tables):
            archive.writestr(name, tables[name])
    direct = directory / "direct.json"
    direct.write_text(json.dumps({
        "service_day": DAY.isoformat(),
        "source_sha256": hashlib.sha256(feed.read_bytes()).hexdigest(),
        "journeys": [
            {"boarding_stop_id": "H1", "boarding_seconds": 25200,
             "boarding_time": "07:00:00", "arrival_seconds": 25200,
             "arrival_time": "07:00:00", "trip_id": "second-exact"},
            {"boarding_stop_id": "H3", "boarding_seconds": 25200,
             "boarding_time": "07:00:00", "arrival_seconds": 27000,
             "arrival_time": "07:30:00", "trip_id": "second-over"},
            {"boarding_stop_id": "H1", "boarding_seconds": 30900,
             "boarding_time": "08:35:00", "arrival_seconds": 32400,
             "arrival_time": "09:00:00", "trip_id": "second-upper"},
        ],
    }, sort_keys=True), encoding="utf-8")
    return feed, direct


class FeederConeTests(unittest.TestCase):
    def run_fixture(self, directory, name="out.json", sample_limit=10):
        feed, direct = write_fixture(directory)
        return cone.build_feeder_cone(
            feed, direct, DAY, directory / name,
            expected_feed_sha256=hashlib.sha256(feed.read_bytes()).hexdigest(),
            expected_direct_sha256=hashlib.sha256(direct.read_bytes()).hexdigest(),
            sample_limit=sample_limit,
        )

    def test_boundaries_permissions_hub_membership_and_service_exceptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.run_fixture(pathlib.Path(tmp))
        candidates = payload["sample_candidates"]
        self.assertEqual(payload["second_leg_hub_ids"], ["H1", "H3"])
        self.assertEqual({row["first_leg_trip_id"] for row in candidates}, {"lower", "upper"})
        lower = next(row for row in candidates if row["first_leg_trip_id"] == "lower")
        upper = next(row for row in candidates if row["first_leg_trip_id"] == "upper")
        self.assertEqual(lower["first_board_seconds"], 23400)
        self.assertEqual(lower["total_transit_seconds"], 1800)
        self.assertEqual(lower["first_board_stop_sequence"], 1)
        self.assertEqual(lower["hub_stop_sequence"], 3)
        self.assertEqual(lower["first_board_pickup_type"], "0")
        self.assertEqual(lower["hub_drop_off_type"], "0")
        self.assertEqual(upper["first_board_seconds"], 30600)
        self.assertEqual(upper["service_provenance"], "exception_added")
        self.assertNotIn("unused-hub", {row["first_leg_trip_id"] for row in candidates})

    def test_arrival_must_precede_departure_and_1801_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.run_fixture(pathlib.Path(tmp))
        trips = {row["first_leg_trip_id"] for row in payload["sample_candidates"]}
        self.assertNotIn("late-hub", trips)
        self.assertNotIn("over", trips)

    def test_frequency_and_malformed_trip_are_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.run_fixture(pathlib.Path(tmp))
        self.assertEqual(payload["unresolved_counts"]["frequency_exact_times_0_trips"], 1)
        self.assertEqual(payload["unresolved_counts"]["invalid_scoped_trips"], 1)
        self.assertEqual(payload["unresolved_counts"]["malformed_scoped_stop_time_rows"], 1)

    def test_deterministic_and_both_hash_mismatches_reject_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            first = self.run_fixture(directory, "first.json", sample_limit=2)
            feed = directory / "feed.zip"
            direct = directory / "direct.json"
            second_path = directory / "second.json"
            cone.build_feeder_cone(
                feed, direct, DAY, second_path,
                expected_feed_sha256=hashlib.sha256(feed.read_bytes()).hexdigest(),
                expected_direct_sha256=hashlib.sha256(direct.read_bytes()).hexdigest(),
                sample_limit=2,
            )
            self.assertEqual((directory / "first.json").read_bytes(), second_path.read_bytes())
            self.assertEqual(first["candidate_count"], 3)
            for keyword, feed_hash, direct_hash in (
                ("GTFS", "0" * 64, hashlib.sha256(direct.read_bytes()).hexdigest()),
                ("direct result", hashlib.sha256(feed.read_bytes()).hexdigest(), "0" * 64),
            ):
                rejected = directory / f"rejected-{keyword}.json"
                with self.assertRaisesRegex(cone.FeederConeError, "SHA-256 mismatch"):
                    cone.build_feeder_cone(feed, direct, DAY, rejected,
                        expected_feed_sha256=feed_hash,
                        expected_direct_sha256=direct_hash)
                self.assertFalse(rejected.exists())


    def test_same_trip_continuation_is_not_a_transfer_feeder(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            source = json.loads(direct.read_text())
            source['journeys'][0]['trip_id'] = 'lower'
            direct.write_text(json.dumps(source, sort_keys=True))
            result = cone.build_feeder_cone(
                feed, direct, DAY, directory / 'result.json',
                expected_feed_sha256=hashlib.sha256(feed.read_bytes()).hexdigest(),
                expected_direct_sha256=hashlib.sha256(direct.read_bytes()).hexdigest(),
            )
            self.assertEqual(result['candidate_count'], 1)
            self.assertTrue(all(item['first_leg_trip_id'] != item['second_leg_trip_id']
                                for item in result['sample_candidates']))

    def test_sample_limit_is_hard_bounded_before_any_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            for limit in (-1, 101, True, 1.5):
                output = directory / 'should-not-exist.json'
                with self.assertRaisesRegex(cone.FeederConeError, 'sample_limit'):
                    cone.build_feeder_cone(feed, direct, DAY, output, sample_limit=limit)
                self.assertFalse(output.exists())
            zero = cone.build_feeder_cone(feed, direct, DAY, directory / 'zero.json', sample_limit=0)
            self.assertEqual(zero['candidate_count'], 3)
            self.assertEqual(zero['sample_candidates'], [])

    def test_large_candidate_product_keeps_only_bounded_evidence_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            payload = json.loads(direct.read_text())
            payload['journeys'] = [
                {**row, 'trip_id': f"{row['trip_id']}-{index:04d}"}
                for index in range(1000) for row in payload['journeys']
            ]
            direct.write_text(json.dumps(payload, sort_keys=True))
            result_path = directory / 'bounded.json'
            result = cone.build_feeder_cone(
                feed, direct, DAY, result_path,
                expected_feed_sha256=hashlib.sha256(feed.read_bytes()).hexdigest(),
                expected_direct_sha256=hashlib.sha256(direct.read_bytes()).hexdigest(),
                sample_limit=2,
            )
            self.assertEqual(result['candidate_count'], 3000)
            self.assertEqual(len(result['sample_candidates']), 2)
            self.assertFalse('candidates' in result)
            self.assertLess(result_path.stat().st_size, 20_000)

    def test_candidate_stream_manifest_order_summary_and_repeat_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            expected_feed = hashlib.sha256(feed.read_bytes()).hexdigest()
            expected_direct = hashlib.sha256(direct.read_bytes()).hexdigest()
            streams = []
            for suffix in ("one", "two"):
                output = directory / f"candidates-{suffix}.ndjson.gz"
                cone.build_feeder_cone(
                    feed, direct, DAY, directory / f"report-{suffix}.json",
                    expected_feed_sha256=expected_feed,
                    expected_direct_sha256=expected_direct,
                    candidate_output_path=output,
                )
                streams.append(output.read_bytes())
            self.assertEqual(streams[0], streams[1])
            lines = [json.loads(line) for line in gzip.decompress(streams[0]).splitlines()]
            self.assertEqual(lines[0], {
                "direct_result_sha256": expected_direct,
                "kind": "manifest",
                "service_day": DAY.isoformat(),
                "source_sha256": expected_feed,
                "status": "necessary_only",
            })
            self.assertEqual([row["first_leg_trip_id"] for row in lines[1:-1]],
                             ["lower", "lower", "upper"])
            self.assertTrue(all(row["kind"] == "candidate" for row in lines[1:-1]))
            self.assertEqual(lines[-1], {"candidate_count": 3, "kind": "summary"})

    def test_candidate_count_cap_fails_without_partial_or_replaced_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            report = directory / "report.json"
            output = directory / "candidates.ndjson.gz"
            report.write_bytes(b"old report")
            output.write_bytes(b"old candidates")
            with mock.patch.object(cone, "MAX_CANDIDATE_OUTPUT_COUNT", 2):
                with self.assertRaisesRegex(cone.FeederConeError, "candidate output count"):
                    cone.build_feeder_cone(
                        feed, direct, DAY, report, candidate_output_path=output)
            self.assertEqual(report.read_bytes(), b"old report")
            self.assertEqual(output.read_bytes(), b"old candidates")
            self.assertEqual(list(directory.glob(".*.tmp")), [])

    def test_direct_json_byte_cap_is_checked_before_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            direct.write_bytes(b" " * (cone.MAX_DIRECT_RESULT_BYTES + 1))
            with mock.patch.object(cone.json, "loads", side_effect=AssertionError("parsed")):
                with self.assertRaisesRegex(cone.FeederConeError, "4 MiB"):
                    cone.build_feeder_cone(feed, direct, DAY, directory / "report.json")

    def test_feed_is_parsed_from_hashed_private_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            expected_feed = hashlib.sha256(feed.read_bytes()).hexdigest()
            original_zipfile = zipfile.ZipFile
            opened = False

            def rewrite_then_open(snapshot, *args, **kwargs):
                nonlocal opened
                if not opened:
                    opened = True
                    feed.write_bytes(b"rewritten after digest")
                return original_zipfile(snapshot, *args, **kwargs)

            with mock.patch.object(cone.zipfile, "ZipFile", side_effect=rewrite_then_open):
                payload = cone.build_feeder_cone(
                    feed, direct, DAY, directory / "report.json",
                    expected_feed_sha256=expected_feed,
                )
            self.assertTrue(opened)
            self.assertEqual(payload["source_sha256"], expected_feed)
            self.assertEqual(payload["candidate_count"], 3)

    def test_manifest_failure_cleans_new_candidate_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            output = directory / 'candidates.ndjson.gz'
            with mock.patch.object(cone._CandidateStream, '_write', side_effect=OSError('manifest write')):
                with self.assertRaisesRegex(OSError, 'manifest write'):
                    cone.build_feeder_cone(feed, direct, DAY, directory / 'report.json', candidate_output_path=output)
            self.assertFalse(output.exists())
            self.assertEqual(list(directory.glob('.*.tmp')), [])

    def test_candidate_publish_failure_preserves_existing_report_and_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            report = directory / 'report.json'
            output = directory / 'candidates.ndjson.gz'
            report.write_bytes(b'OLD REPORT')
            output.write_bytes(b'OLD STREAM')
            with mock.patch.object(cone._CandidateStream, 'publish', side_effect=OSError('publish failed')):
                with self.assertRaisesRegex(OSError, 'publish failed'):
                    cone.build_feeder_cone(feed, direct, DAY, report, candidate_output_path=output)
            self.assertEqual(report.read_bytes(), b'OLD REPORT')
            self.assertEqual(output.read_bytes(), b'OLD STREAM')
            self.assertEqual(list(directory.glob('.*.tmp')), [])

    def test_report_publish_failure_restores_previous_candidate_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            report = directory / 'report.json'
            output = directory / 'candidates.ndjson.gz'
            report.write_bytes(b'OLD REPORT')
            output.write_bytes(b'OLD STREAM')
            real_replace = os.replace
            def fail_report_only(source, target):
                if pathlib.Path(target) == report:
                    raise OSError('report publish failed')
                return real_replace(source, target)
            with mock.patch.object(cone.os, 'replace', side_effect=fail_report_only):
                with self.assertRaisesRegex(OSError, 'report publish failed'):
                    cone.build_feeder_cone(feed, direct, DAY, report, candidate_output_path=output)
            self.assertEqual(report.read_bytes(), b'OLD REPORT')
            self.assertEqual(output.read_bytes(), b'OLD STREAM')
            self.assertEqual(list(directory.glob('.*.tmp')), [])

    def test_interrupt_after_candidate_rename_restores_previous_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            report = directory / 'report.json'
            output = directory / 'candidates.ndjson.gz'
            report.write_bytes(b'OLD REPORT')
            output.write_bytes(b'OLD STREAM')
            real_publish = cone._CandidateStream.publish
            def publish_then_interrupt(stream):
                real_publish(stream)
                raise KeyboardInterrupt()
            with mock.patch.object(cone._CandidateStream, 'publish', publish_then_interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    cone.build_feeder_cone(feed, direct, DAY, report, candidate_output_path=output)
            self.assertEqual(report.read_bytes(), b'OLD REPORT')
            self.assertEqual(output.read_bytes(), b'OLD STREAM')
            self.assertEqual(list(directory.glob('.*.tmp')), [])

    def test_failed_rollback_retains_recovery_copy_for_manual_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            report = directory / 'report.json'
            output = directory / 'candidates.ndjson.gz'
            report.write_bytes(b'OLD REPORT')
            output.write_bytes(b'OLD STREAM')
            real_replace = os.replace
            output_replacements = 0
            def fail_publication_and_rollback(source, target):
                nonlocal output_replacements
                if pathlib.Path(target) == report:
                    raise OSError('report publish failed')
                if pathlib.Path(target) == output:
                    output_replacements += 1
                    if output_replacements == 2:
                        raise OSError('rollback failed')
                return real_replace(source, target)
            with mock.patch.object(cone.os, 'replace', side_effect=fail_publication_and_rollback):
                with self.assertRaisesRegex(cone.FeederConeError, 'backup retained'):
                    cone.build_feeder_cone(feed, direct, DAY, report, candidate_output_path=output)
            self.assertEqual(report.read_bytes(), b'OLD REPORT')
            backups = list(directory.glob(f'.{output.name}.*.tmp'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b'OLD STREAM')

    def test_owner_approved_day_is_not_described_as_unapproved(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            report = cone.build_feeder_cone(feed, direct, DAY, directory / 'report.json')
            self.assertTrue(any('owner approved' in value.lower() for value in report['limitations']))
            self.assertFalse(any('not an approved reference day' in value.lower() for value in report['limitations']))

    def test_candidate_stream_is_removed_on_mid_enumeration_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            report = directory / "report.json"
            output = directory / "candidates.ndjson.gz"
            with mock.patch.object(cone._CandidateStream, "write_candidate", side_effect=RuntimeError("mid-loop")):
                with self.assertRaisesRegex(RuntimeError, "mid-loop"):
                    cone.build_feeder_cone(feed, direct, DAY, report, candidate_output_path=output)
            self.assertFalse(output.exists())
            self.assertFalse(report.exists())
            self.assertEqual(list(directory.glob(".*.tmp")), [])

    def test_candidate_stream_is_removed_on_mid_enumeration_interrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            report = directory / "report.json"
            output = directory / "candidates.ndjson.gz"
            report.write_bytes(b"OLD REPORT")
            output.write_bytes(b"OLD STREAM")
            for interruption in (KeyboardInterrupt(), SystemExit(7)):
                with self.subTest(interruption=type(interruption).__name__):
                    with mock.patch.object(
                            cone._CandidateStream, "write_candidate",
                            side_effect=interruption):
                        with self.assertRaises(type(interruption)):
                            cone.build_feeder_cone(
                                feed, direct, DAY, report,
                                candidate_output_path=output)
                    self.assertEqual(report.read_bytes(), b"OLD REPORT")
                    self.assertEqual(output.read_bytes(), b"OLD STREAM")
                    self.assertEqual(list(directory.glob(".*.tmp")), [])

    def test_abort_unlinks_candidate_temp_when_raw_close_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            stream = cone._CandidateStream(
                directory / "candidates.ndjson.gz", {"kind": "manifest"})
            temporary_path = stream.temporary_path
            with mock.patch.object(
                    stream.raw, "close", side_effect=OSError("close failed")):
                with self.assertRaisesRegex(OSError, "close failed"):
                    stream.abort()
            self.assertFalse(temporary_path.exists())
            stream.raw.close()

    def test_interrupt_after_report_rename_restores_previous_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, direct = write_fixture(directory)
            report = directory / "report.json"
            output = directory / "candidates.ndjson.gz"
            report.write_bytes(b"OLD REPORT")
            output.write_bytes(b"OLD STREAM")
            real_replace = os.replace
            report_replacements = 0

            def replace_report_then_interrupt(source, target):
                nonlocal report_replacements
                real_replace(source, target)
                if pathlib.Path(target) == report:
                    report_replacements += 1
                    if report_replacements == 1:
                        raise KeyboardInterrupt()

            with mock.patch.object(
                    cone.os, "replace", side_effect=replace_report_then_interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    cone.build_feeder_cone(
                        feed, direct, DAY, report, candidate_output_path=output)
            self.assertEqual(report.read_bytes(), b"OLD REPORT")
            self.assertEqual(output.read_bytes(), b"OLD STREAM")
            self.assertEqual(list(directory.glob(".*.tmp")), [])

    def test_output_aliases_are_rejected_without_modifying_any_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            for alias_name in ("feed", "direct", "report"):
                feed, direct = write_fixture(directory)
                report = directory / "report.json"
                report.write_bytes(b"old report")
                alias = {"feed": feed, "direct": direct, "report": report}[alias_name]
                before = {path: path.read_bytes() for path in (feed, direct, report)}
                with self.assertRaisesRegex(cone.FeederConeError, "alias"):
                    cone.build_feeder_cone(
                        feed, direct, DAY, report, candidate_output_path=alias)
                self.assertEqual({path: path.read_bytes() for path in before}, before)

if __name__ == "__main__":
    unittest.main()
