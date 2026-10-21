"""Synthetic tests for the bounded direct-only GTFS positive screen."""
import datetime as dt
import hashlib
import pathlib
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))
import gtfs_direct_cap as direct


DAY = dt.date(2026, 10, 27)
PARENTS = {"P_RAIL", "P_BUS"}


def feed_bytes(path):
    tables = {
        "stops.txt": """stop_id,stop_name,location_type,parent_station,stop_lat,stop_lon
P_RAIL,Aarau rail,1,,47,8
P_BUS,Aarau bus,1,,47,8
OP,Origin parent,1,,47,8
OTHER,Other parent,1,,47,8
T1,Aarau platform,0,P_RAIL,47,8
T2,Aarau bus platform,0,P_BUS,47,8
O1,Origin one,0,OP,47,8
O2,Origin two,0,OP,47,8
M,Intermediate,0,OTHER,47,8
RANDOM,Random city stop,0,OTHER,47,8
""",
        "calendar.txt": """service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
BASE,0,1,0,0,0,0,0,20261001,20261031
REMOVE,0,1,0,0,0,0,0,20261001,20261031
ADD,0,0,0,0,0,0,0,20261001,20261031
""",
        "calendar_dates.txt": """service_id,date,exception_type
REMOVE,20261027,2
ADD,20261027,1
UNRELATED,20261026,1
""",
        "trips.txt": """route_id,service_id,trip_id
R,BASE,lower
R,ADD,upper
R,BASE,exact-1800
R,BASE,over-1800
R,REMOVE,removed
R,BASE,pickup-blocked
R,BASE,drop-blocked
R,BASE,pickup-demand
R,BASE,drop-demand
R,BASE,frequency-template
""",
        "frequencies.txt": """trip_id,start_time,end_time,headway_secs,exact_times
frequency-template,12:00:00,13:00:00,600,0
""",
        "stop_times.txt": """trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type,timepoint
lower,06:30:00,06:30:00,O1,1,0,0,1
lower,06:40:00,06:40:00,M,2,0,0,1
lower,06:50:00,06:50:00,T1,3,0,0,1
upper,08:30:00,08:30:00,O2,1,0,0,1
upper,08:40:00,08:40:00,T2,2,0,0,1
exact-1800,07:00:00,07:00:00,O1,1,0,0,1
exact-1800,07:30:00,07:30:00,T1,2,0,0,1
over-1800,07:00:00,07:00:00,O1,1,0,0,1
over-1800,07:30:01,07:30:01,T1,2,0,0,1
removed,07:00:00,07:00:00,O1,1,0,0,1
removed,07:10:00,07:10:00,T1,2,0,0,1
pickup-blocked,07:00:00,07:00:00,O1,1,1,0,1
pickup-blocked,07:10:00,07:10:00,T1,2,0,0,1
drop-blocked,07:00:00,07:00:00,O1,1,0,0,1
drop-blocked,07:10:00,07:10:00,T1,2,0,1,1
pickup-demand,07:00:00,07:00:00,O1,1,2,0,1
pickup-demand,07:10:00,07:10:00,T1,2,0,0,1
drop-demand,07:00:00,07:00:00,O1,1,0,0,1
drop-demand,07:10:00,07:10:00,T1,2,0,3,1
frequency-template,12:00:00,12:00:00,O1,1,0,0,1
frequency-template,12:10:00,12:10:00,T1,2,0,0,1
""",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name in sorted(tables):
            archive.writestr(name, tables[name])
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mutate_feed(path, table_name, old, new):
    with zipfile.ZipFile(path) as archive:
        tables = {name: archive.read(name).decode('utf-8')
                  for name in archive.namelist()}
    assert old in tables[table_name]
    tables[table_name] = tables[table_name].replace(old, new, 1)
    with zipfile.ZipFile(path, 'w') as archive:
        for name in sorted(tables):
            archive.writestr(name, tables[name])
    return hashlib.sha256(path.read_bytes()).hexdigest()

class DirectCapTests(unittest.TestCase):
    def run_fixture(self, directory, name="result.json"):
        feed = directory / "feed.zip"
        expected = feed_bytes(feed)
        result = directory / name
        summary = direct.screen_direct_journeys(
            feed, DAY, PARENTS, result, expected_sha256=expected, sample_limit=2
        )
        return feed, result, summary

    def test_inclusive_window_exact_seconds_intermediate_stops_and_service_exceptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary = self.run_fixture(pathlib.Path(tmp))
        journeys = summary["journeys"]
        by_trip = {}
        for row in journeys:
            by_trip.setdefault(row["trip_id"], []).append(row)
        self.assertEqual(set(by_trip), {"lower", "upper", "exact-1800"})
        lower = next(row for row in by_trip["lower"] if row["boarding_stop_id"] == "O1")
        self.assertEqual(lower["boarding_time"], "06:30:00")
        self.assertEqual(by_trip["upper"][0]["boarding_time"], "08:30:00")
        self.assertEqual(by_trip["exact-1800"][0]["transit_seconds"], 1800)
        self.assertNotIn("over-1800", by_trip)
        self.assertEqual(by_trip["upper"][0]["service_provenance"], "exception_added")
        self.assertEqual(lower["service_provenance"], "base_calendar")
        self.assertLess(lower["boarding_stop_sequence"], lower["destination_stop_sequence"])

    def test_pickup_dropoff_fail_closed_and_frequency_template_is_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary = self.run_fixture(pathlib.Path(tmp))
        self.assertEqual(summary["excluded_counts"]["pickup_type_1"], 1)
        self.assertEqual(summary["excluded_counts"]["drop_off_type_1"], 1)
        self.assertEqual(summary["unresolved_counts"]["pickup_or_drop_off_type_2_or_3"], 2)
        self.assertEqual(summary["unresolved_counts"]["frequency_exact_times_0_trips"], 1)
        self.assertEqual(summary["unresolved_frequency_trips"][0]["trip_id"], "frequency-template")
        self.assertEqual(summary["status"], "DIRECT_POSITIVES_WITH_UNRESOLVED_CLASSES")

    def test_malformed_scoped_required_value_is_unresolved_and_not_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            original = directory / "original.zip"
            feed_bytes(original)
            changed = directory / "malformed.zip"
            with zipfile.ZipFile(original) as source, zipfile.ZipFile(changed, "w") as target:
                for name in source.namelist():
                    value = source.read(name)
                    if name == "stop_times.txt":
                        value = value.replace(b"exact-1800,07:00:00,07:00:00,O1,1",
                                              b"exact-1800,07:00:00,bad,O1,1")
                    target.writestr(name, value)
            result = directory / "result.json"
            payload = direct.screen_direct_journeys(
                changed, DAY, PARENTS, result,
                expected_sha256=hashlib.sha256(changed.read_bytes()).hexdigest(),
            )
        self.assertEqual(payload["unresolved_counts"]["malformed_scoped_stop_time_rows"], 1)
        self.assertNotIn("exact-1800", {row["trip_id"] for row in payload["journeys"]})

    def test_destination_children_are_observed_from_stops_not_derived(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary = self.run_fixture(pathlib.Path(tmp))
        self.assertEqual(summary["destination_children"], {
            "P_BUS": ["T2"], "P_RAIL": ["T1"]
        })
        self.assertNotIn("RANDOM", str(summary["destination_children"]))
        self.assertTrue(all(row["destination_stop_id"] in {"T1", "T2"}
                            for row in summary["journeys"]))

    def test_output_is_deterministic_and_hash_mismatch_fails_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, first, _ = self.run_fixture(directory, "first.json")
            expected = hashlib.sha256(feed.read_bytes()).hexdigest()
            second = directory / "second.json"
            direct.screen_direct_journeys(feed, DAY, PARENTS, second,
                                          expected_sha256=expected, sample_limit=2)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            rejected = directory / "rejected.json"
            with self.assertRaisesRegex(direct.DirectCapError, "SHA-256 mismatch"):
                direct.screen_direct_journeys(feed, DAY, PARENTS, rejected,
                                              expected_sha256="0" * 64)
            self.assertFalse(rejected.exists())


    def test_corrupt_intermediate_row_invalidates_the_whole_trip(self):
        cases = (
            ("lower,06:40:00,06:40:00,M,2", "lower,bad,06:40:00,M,2", "malformed_scoped_stop_time_rows"),
            ("lower,06:40:00,06:40:00,M,2", "lower,06:55:00,06:55:00,M,2", "nonmonotonic_trip_time"),
        )
        for old, new, reason in cases:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                directory = pathlib.Path(tmp)
                feed = directory / "feed.zip"
                feed_bytes(feed)
                expected = mutate_feed(feed, "stop_times.txt", old, new)
                payload = direct.screen_direct_journeys(
                    feed, DAY, PARENTS, directory / "out.json", expected_sha256=expected
                )
                self.assertNotIn("lower", {row["trip_id"] for row in payload["journeys"]})
                self.assertGreater(payload["unresolved_counts"][reason], 0)

    def test_destination_parent_must_be_an_actual_parent_station(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed = directory / "feed.zip"
            feed_bytes(feed)
            expected = mutate_feed(feed, "stops.txt", "P_RAIL,Aarau rail,1,", "P_RAIL,Aarau rail,0,")
            with self.assertRaisesRegex(direct.DirectCapError, "destination parent"):
                direct.screen_direct_journeys(
                    feed, DAY, PARENTS, directory / "out.json", expected_sha256=expected
                )

if __name__ == "__main__":
    unittest.main()
