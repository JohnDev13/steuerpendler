"""Synthetic first-boarding cone probes; no fixture is a real timetable or place."""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))

import aarau_boarding_cone_probe as probe
from aarau_boarding_cone_probe import BoardingConeError, probe_feed


class SyntheticGeometry:
    """Deterministic test geometry; real runs must use lazy-loaded pyproj."""

    def transform(self, source_crs, x, y):
        if source_crs != "EPSG:4326":
            raise ValueError("synthetic geometry only accepts EPSG:4326")
        return x, y

    def distance(self, origin_longitude, origin_latitude, longitude, latitude):
        return 111_000 * abs(latitude - origin_latitude) + 75_000 * abs(longitude - origin_longitude)


class BoardingConeProbeTests(unittest.TestCase):
    day = dt.date(2026, 10, 27)

    def write_feed(self, path, *, frequencies=""):
        tables = {
            "stops.txt": (
                "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station\n"
                "P,Fixture parent,47.0,8.0,1,\n"
                "NEAR,Fixture platform,47.0,8.0,0,P\n"
                "ORPHAN,Unparented fixture,47.0,8.0,0,\n"
                "FAR,Far platform,47.02,8.0,0,P\n"
            ),
            "calendar.txt": (
                "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                "BASE,0,1,0,0,0,0,0,20261001,20261031\n"
                "ADD,0,0,0,0,0,0,0,20261001,20261031\n"
                "REMOVE,0,1,0,0,0,0,0,20261001,20261031\n"
                "INACTIVE,0,0,0,0,0,0,0,20261001,20261031\n"
            ),
            "calendar_dates.txt": (
                "service_id,date,exception_type\n"
                "ADD,20261027,1\n"
                "REMOVE,20261027,2\n"
            ),
            "trips.txt": (
                "route_id,service_id,trip_id\n"
                "R,BASE,lower\nR,BASE,upper\nR,BASE,before\nR,BASE,after\n"
                "R,ADD,added\nR,REMOVE,removed\nR,INACTIVE,inactive\n"
                "R,BASE,prohibited\nR,BASE,far\nR,BASE,freq-zero\nR,BASE,freq-one\n"
                "R,BASE,freq-outside-template\nR,BASE,freq-prohibited\n"
            ),
            "stop_times.txt": (
                "trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type\n"
                "lower,06:30:00,06:30:00,NEAR,1,\n"
                "upper,08:30:00,08:30:00,NEAR,1,0\n"
                "before,06:29:59,06:29:59,NEAR,1,0\n"
                "after,08:30:01,08:30:01,NEAR,1,0\n"
                "added,07:00:01,07:00:01,NEAR,1,0\n"
                "removed,07:00:02,07:00:02,NEAR,1,0\n"
                "inactive,07:00:03,07:00:03,NEAR,1,0\n"
                "prohibited,07:00:04,07:00:04,NEAR,1,1\n"
                "far,07:00:05,07:00:05,FAR,1,0\n"
                "freq-zero,07:00:06,07:00:06,NEAR,1,0\n"
                "freq-one,07:00:07,07:00:07,NEAR,1,0\n"
                "freq-outside-template,05:00:00,05:00:00,NEAR,1,0\n"
                "freq-prohibited,05:01:00,05:01:00,NEAR,1,1\n"
            ),
            "frequencies.txt": frequencies or (
                "trip_id,start_time,end_time,headway_secs,exact_times\n"
                "freq-zero,07:00:00,08:00:00,600,0\n"
                "freq-one,07:00:00,08:00:00,600,1\n"
                "freq-outside-template,07:15:00,07:45:00,600,0\n"
                "freq-prohibited,07:15:00,07:45:00,600,0\n"
            ),
        }
        with zipfile.ZipFile(path, "w") as archive:
            for name, text in tables.items():
                archive.writestr(name, text)

    def test_inclusive_active_boardings_geodesic_screen_and_frequency_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = pathlib.Path(tmp) / "fixture.zip"
            result = pathlib.Path(tmp) / "result.json"
            self.write_feed(feed)
            summary = probe_feed(
                feed,
                self.day,
                [{"origin_id": "synthetic", "source_crs": "EPSG:4326", "x": 8.0, "y": 47.0}],
                result,
                radius_m=1080.0,
                geometry_provider=SyntheticGeometry(),
            )
            payload = json.loads(result.read_text())

        self.assertEqual({row["trip_id"] for row in payload["candidate_records"]},
                         {"lower", "upper", "added"})
        self.assertEqual(summary["exact_candidate_count"], 3)
        self.assertEqual(summary["excluded_pickup_type_1_count"], 2)
        self.assertEqual(summary["frequency_exact_times_0_candidate_count"], 2)
        self.assertEqual(summary["frequency_exact_times_1_candidate_count"], 1)
        self.assertEqual(summary["status"], "FREQUENCY_CANDIDATES_UNRESOLVED")
        self.assertEqual(summary["candidate_stop_ids"], ["NEAR"])
        self.assertEqual(summary["unparented_candidate_stop_ids"], ["ORPHAN"])
        self.assertEqual(payload["candidate_records"][0]["source_stop_id"], "NEAR")
        self.assertEqual(payload["candidate_records"][0]["parent_stop_id"], "P")
        self.assertLessEqual(payload["candidate_records"][0]["geodesic_distance_m"], 1080.0)
        self.assertGreater(summary["scanned_counts"]["stop_times"], 0)
        outside = next(row for row in payload["frequency_exact_times_0_records"]
                       if row["trip_id"] == "freq-outside-template")
        self.assertEqual(outside["record_type"], "template_only")
        self.assertEqual(outside["departure_time"], "05:00:00")
        self.assertNotIn("freq-prohibited", {
            row["trip_id"] for row in payload["frequency_exact_times_0_records"]
        })

    def test_unsupported_pickup_rule_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = pathlib.Path(tmp) / "fixture.zip"
            result = pathlib.Path(tmp) / "result.json"
            self.write_feed(feed)
            with zipfile.ZipFile(feed, "a") as archive:
                text = archive.read("stop_times.txt").decode().replace(
                    "added,07:00:01,07:00:01,NEAR,1,0",
                    "added,07:00:01,07:00:01,NEAR,1,2",
                )
                archive.writestr("stop_times.txt", text)
            with self.assertRaisesRegex(BoardingConeError, "unsupported pickup_type"):
                probe_feed(
                    feed,
                    self.day,
                    [{"origin_id": "synthetic", "source_crs": "EPSG:4326", "x": 8.0, "y": 47.0}],
                    result,
                    geometry_provider=SyntheticGeometry(),
                )
        self.assertFalse(result.exists())

    def test_real_geometry_fails_closed_when_pyproj_is_unavailable(self):
        real_import = __import__

        def missing_pyproj(name, *args, **kwargs):
            if name == "pyproj":
                raise ModuleNotFoundError("No module named 'pyproj'")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=missing_pyproj):
            with self.assertRaisesRegex(BoardingConeError, "pyproj is required"):
                probe._origin_points([
                    {"origin_id": "synthetic", "source_crs": "EPSG:4326", "x": 8.0, "y": 47.0}
                ])


if __name__ == "__main__":
    unittest.main()
