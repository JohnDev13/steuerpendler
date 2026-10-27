import csv
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "travel"))
import matrix  # noqa: E402

DAY = dt.date(2026, 10, 27)  # Tuesday


def t(clock: str) -> str:
    return clock


def write_feed(path: Path, stops, trips, transfers=(), calendar_dates=(), routes=None):
    """stops: [(id, name, lat, lon, parent)]; trips: {trip_id: (route_type, [(stop, arr, dep, pickup, drop)])}."""
    tables = {
        "stops.txt": [["stop_id", "stop_name", "stop_lat", "stop_lon", "parent_station"], *stops],
        "calendar.txt": [["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                          "start_date", "end_date"], ["S", "1", "1", "1", "1", "1", "0", "0", "20261201", "20261231"],
                         ["W", "1", "1", "1", "1", "1", "0", "0", "20260101", "20261231"]],
        "calendar_dates.txt": [["service_id", "date", "exception_type"], *calendar_dates],
        "routes.txt": [["route_id", "route_type"]],
        "trips.txt": [["route_id", "service_id", "trip_id"]],
        "stop_times.txt": [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence", "pickup_type", "drop_off_type"]],
        "transfers.txt": [["from_stop_id", "to_stop_id", "transfer_type", "min_transfer_time", "from_trip_id", "to_trip_id"], *transfers],
    }
    for trip_id, (route_type, calls, *service) in trips.items():
        tables["routes.txt"].append([f"r-{trip_id}", str(route_type)])
        tables["trips.txt"].append([f"r-{trip_id}", service[0] if service else "W", trip_id])
        for sequence, (stop, arr, dep, *flags) in enumerate(calls, 1):
            pickup, drop = (flags + ["0", "0"])[:2]
            tables["stop_times.txt"].append([trip_id, arr, dep, stop, str(sequence), pickup, drop])
    with zipfile.ZipFile(path, "w") as archive:
        for name, rows in tables.items():
            buffer = io.StringIO()
            csv.writer(buffer).writerows(rows)
            archive.writestr(name, buffer.getvalue())


# Stops along a line near Aarau, about 1.1 km apart; "T" is the target station.
BASE_LAT, BASE_LON = 47.39, 8.05
STOPS = [
    ("A", "Alpha", BASE_LAT, BASE_LON, ""),
    ("X", "Xenon", BASE_LAT + 0.01, BASE_LON, ""),
    ("X2", "Xenon Bus", BASE_LAT + 0.0102, BASE_LON, ""),  # ~22 m from X, different parent
    ("Y", "Ypsilon", BASE_LAT + 0.02, BASE_LON, ""),
    ("T", "Target", BASE_LAT + 0.03, BASE_LON, ""),
]


class MatrixScan(unittest.TestCase):
    def run_scan(self, trips, transfers=(), calendar_dates=(), stops=STOPS):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.zip"
            write_feed(path, stops, trips, transfers, calendar_dates)
            feed = matrix.load_feed(path, DAY)
            return feed, matrix.scan(feed, {"T"}, matrix.footpaths(feed))

    def test_direct_ride_measures_first_boarding_to_arrival(self):
        _, result = self.run_scan({"1": (2, [("A", "07:00:00", "07:00:00"), ("T", "07:12:00", "07:12:00")])})
        self.assertEqual((result["A"].seconds, result["A"].first_board, result["A"].transfers), (720, 25200, 0))

    def test_change_needs_default_change_time(self):
        trips = {
            "in": (2, [("A", "07:00:00", "07:00:00"), ("X", "07:05:00", "07:05:00")]),
            "too-early": (2, [("X", "07:06:00", "07:06:00"), ("T", "07:10:00", "07:10:00")]),
            "ok": (2, [("X", "07:07:00", "07:07:00"), ("T", "07:15:00", "07:15:00")]),
        }
        _, result = self.run_scan(trips)
        self.assertEqual(result["A"].seconds, 15 * 60)
        self.assertEqual(result["A"].transfers, 1)

    def test_transfers_txt_minimum_overrides_default_and_type_3_forbids(self):
        trips = {
            "in": (2, [("A", "07:00:00", "07:00:00"), ("X", "07:05:00", "07:05:00")]),
            "a": (2, [("X", "07:07:00", "07:07:00"), ("T", "07:10:00", "07:10:00")]),
            "b": (2, [("X", "07:10:00", "07:10:00"), ("T", "07:20:00", "07:20:00")]),
        }
        _, result = self.run_scan(trips, transfers=[["X", "X", "2", "240", "", ""]])
        self.assertEqual(result["A"].seconds, 20 * 60)
        _, result = self.run_scan(trips, transfers=[["X", "X", "3", "", "", ""]])
        self.assertNotIn("A", result)

    def test_stay_seated_continuation_counts_no_change(self):
        trips = {
            "first": (2, [("A", "07:00:00", "07:00:00"), ("X", "07:05:00", "07:05:00")]),
            "second": (2, [("X", "07:05:00", "07:05:00"), ("T", "07:09:00", "07:09:00")]),
        }
        _, result = self.run_scan(trips, transfers=[["", "", "4", "", "first", "second"]])
        self.assertEqual((result["A"].seconds, result["A"].transfers), (9 * 60, 0))
        _, result = self.run_scan(trips)
        self.assertNotIn("A", result)  # without the rule a 0-minute change is not possible

    def test_short_walk_to_a_nearby_stop(self):
        trips = {
            "rail": (2, [("A", "07:00:00", "07:00:00"), ("X", "07:05:00", "07:05:00")]),
            "bus": (3, [("X2", "07:08:00", "07:08:00"), ("T", "07:14:00", "07:14:00")]),
        }
        _, result = self.run_scan(trips)
        self.assertEqual((result["A"].seconds, result["A"].transfers), (14 * 60, 1))

    def test_pickup_and_drop_off_restrictions(self):
        no_pickup = {"1": (2, [("A", "07:00:00", "07:00:00", "1", "0"), ("T", "07:10:00", "07:10:00")])}
        self.assertNotIn("A", self.run_scan(no_pickup)[1])
        no_drop = {"1": (2, [("A", "07:00:00", "07:00:00"), ("T", "07:10:00", "07:10:00", "0", "1")])}
        self.assertNotIn("A", self.run_scan(no_drop)[1])

    def test_window_and_cap_are_inclusive(self):
        trips = {
            "before": (2, [("A", "06:29:00", "06:29:00"), ("T", "06:31:00", "06:31:00")]),
            "start": (2, [("Y", "06:30:00", "06:30:00"), ("T", "07:00:00", "07:00:00")]),
            "late": (2, [("X", "08:31:00", "08:31:00"), ("T", "08:35:00", "08:35:00")]),
            "long": (2, [("X2", "07:00:00", "07:00:00"), ("T", "07:30:01", "07:30:01")]),
        }
        _, result = self.run_scan(trips)
        self.assertNotIn("A", result)
        self.assertEqual(result["Y"].seconds, 1800)
        self.assertNotIn("X", result)
        self.assertNotIn("X2", result)

    def test_initial_wait_is_excluded_and_fastest_boarding_wins(self):
        trips = {
            "slow": (3, [("A", "06:40:00", "06:40:00"), ("T", "07:05:00", "07:05:00")]),
            "fast": (2, [("A", "07:50:00", "07:50:00"), ("T", "07:58:00", "07:58:00")]),
        }
        _, result = self.run_scan(trips)
        self.assertEqual((result["A"].seconds, result["A"].first_board), (8 * 60, 7 * 3600 + 50 * 60))

    def test_calendar_exceptions_remove_service(self):
        trips = {"1": (2, [("A", "07:00:00", "07:00:00"), ("T", "07:10:00", "07:10:00")])}
        _, result = self.run_scan(trips, calendar_dates=[["W", "20261027", "2"]])
        self.assertNotIn("A", result)
        trips = {"1": (2, [("A", "07:00:00", "07:00:00"), ("T", "07:10:00", "07:10:00")], "S")}
        _, result = self.run_scan(trips, calendar_dates=[["S", "20261027", "1"]])
        self.assertIn("A", result)


def square(cx, cy, half):
    return [[cx - half, cy - half], [cx + half, cy - half], [cx + half, cy + half], [cx - half, cy + half], [cx - half, cy - half]]


def topology_for(squares):
    """Absolute integer coordinates, transform scale 1: one arc per Gemeinde square."""
    arcs, geometries = [], []
    for bfs, points in squares.items():
        deltas, previous = [], (0, 0)
        for x, y in points:
            deltas.append([round(x) - previous[0], round(y) - previous[1]])
            previous = (round(x), round(y))
        geometries.append({"type": "Polygon", "id": bfs, "arcs": [[len(arcs)]]})
        arcs.append(deltas)
    return {"type": "Topology", "transform": {"scale": [1, 1], "translate": [0, 0]}, "arcs": arcs,
            "objects": {"gemeinden": {"type": "GeometryCollection", "geometries": geometries}}}


class MatrixBuild(unittest.TestCase):
    def test_build_assigns_stops_to_gemeinden_and_targets_the_main_station_complex(self):
        stops = STOPS + [("TB", "Target Bahnhof Bus", BASE_LAT + 0.0301, BASE_LON, "")]
        trips = {
            "rail1": (2, [("A", "07:00:00", "07:00:00"), ("X", "07:05:00", "07:05:00"), ("T", "07:12:00", "07:12:00")]),
            "rail2": (2, [("T", "07:30:00", "07:30:00"), ("Y", "07:40:00", "07:40:00")]),
            "bus": (3, [("Y", "07:45:00", "07:45:00"), ("TB", "08:00:00", "08:00:00")]),
        }
        projected = {sid: matrix.wgs84_to_lv95(lon, lat) for sid, _, lat, lon, _ in stops}
        squares = {
            100: square(*projected["A"], 300),
            200: square(*projected["X"], 300),
            300: square(*projected["Y"], 300),
            400: square(*projected["T"], 300),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.zip"
            write_feed(path, stops, trips)
            meta, files = matrix.build(path, topology_for(squares), [400], {100, 200, 300, 400, 500}, DAY, "https://example.invalid/feed.zip")
        rows = files[400]["rows"]
        self.assertEqual(files[400]["station"], "Target")
        self.assertEqual(rows[0], [400, 0, 0, "", 0])
        by_bfs = {row[0]: row for row in rows}
        self.assertEqual(by_bfs[200][1:4], [420, 0, "Xenon"])
        self.assertEqual(by_bfs[100][1:4], [720, 0, "Alpha"])
        self.assertEqual(by_bfs[300][1:4], [900, 0, "Ypsilon"])  # bus to a stop of the station complex
        self.assertNotIn(500, by_bfs)
        self.assertEqual([row[1] for row in rows], sorted(row[1] for row in rows))
        self.assertEqual(meta["absence"], "unknown_unobserved")
        self.assertEqual(meta["workplaces"]["400"]["rows"], 4)
        json.dumps(meta)

    def test_workplace_station_prefers_the_stop_named_like_the_gemeinde(self):
        # Glarus: the merged Gemeinde also contains Netstal, which has more rail calls than Glarus.
        stops = STOPS + [("N", "Nachbardorf", BASE_LAT + 0.038, BASE_LON, "")]
        trips = {
            "r1": (2, [("A", "07:00:00", "07:00:00"), ("T", "07:10:00", "07:10:00"), ("N", "07:14:00", "07:14:00")]),
            "r2": (2, [("Y", "07:20:00", "07:20:00"), ("N", "07:30:00", "07:30:00")]),
            "r3": (2, [("X", "07:40:00", "07:40:00"), ("N", "07:55:00", "07:55:00")]),
        }
        projected = {sid: matrix.wgs84_to_lv95(lon, lat) for sid, _, lat, lon, _ in stops}
        tx, ty = projected["T"]
        squares = {100: square(*projected["A"], 300), 200: square(*projected["X"], 300),
                   300: square(*projected["Y"], 300), 400: square(tx, ty + 450, 600)}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.zip"
            write_feed(path, stops, trips)
            _, unnamed = matrix.build(path, topology_for(squares), [400], {100, 200, 300, 400}, DAY)
            _, named = matrix.build(path, topology_for(squares), [400], {100, 200, 300, 400}, DAY,
                                    names={400: "Target"})
        self.assertEqual(unnamed[400]["station"], "Nachbardorf")
        self.assertEqual(named[400]["station"], "Target")
        self.assertEqual({row[0]: row[1] for row in named[400]["rows"]}[100], 600)

    def test_station_name_matching_handles_disambiguated_gemeinde_names(self):
        self.assertTrue(matrix.station_matches("Altdorf (UR)", "Altdorf UR"))
        self.assertTrue(matrix.station_matches("Zürich", "Zürich HB"))
        self.assertTrue(matrix.station_matches("Basel", "Basel SBB"))
        self.assertTrue(matrix.station_matches("Glarus", "Glarus"))
        self.assertFalse(matrix.station_matches("Glarus", "Netstal"))
        self.assertFalse(matrix.station_matches("Stans", "Stansstad"))

    def test_independent_direct_rows_keep_slower_direct_when_transfer_is_faster(self):
        trips = {
            "incoming": (2, [("A", "07:00:00", "07:00:00"), ("X", "07:05:00", "07:05:00")]),
            "connection": (2, [("X", "07:07:00", "07:07:00"), ("T", "07:10:00", "07:10:00")]),
            "direct": (2, [("A", "07:00:00", "07:00:00"), ("T", "07:20:00", "07:20:00")]),
        }
        projected = {sid: matrix.wgs84_to_lv95(lon, lat) for sid, _, lat, lon, _ in STOPS}
        squares = {100: square(*projected["A"], 300), 200: square(*projected["X"], 300),
                   400: square(*projected["T"], 300)}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.zip"
            write_feed(path, STOPS, trips)
            _, files = matrix.build(path, topology_for(squares), [400], {100, 200, 400}, DAY)
        all_rows = {row[0]: row for row in files[400]["rows"]}
        direct_rows = {row[0]: row for row in files[400]["directRows"]}
        self.assertEqual(all_rows[100][1:3], [600, 1])
        self.assertEqual(direct_rows[100][1:3], [1200, 0])
        self.assertEqual(direct_rows[400][1:3], [0, 0])

    def test_point_in_polygon_respects_holes(self):
        topology = topology_for({1: square(1000, 1000, 500)})
        index = matrix.MunicipalityIndex(matrix.decode_municipalities(topology))
        self.assertEqual(index.locate(1000, 1000), 1)
        self.assertIsNone(index.locate(2000, 1000))


if __name__ == "__main__":
    unittest.main()


CONTRACT = Path(__file__).resolve().parent / "fixtures" / "matrix-contract.json"


class MatrixContract(unittest.TestCase):
    """The committed fixture is what src/matrix-routes.test.ts validates; regenerate with
    UPDATE_MATRIX_CONTRACT=1 python3 -m unittest tests.travel.test_matrix"""

    def test_frontend_contract_fixture_is_current(self):
        stops = STOPS + [("TB", "Target Bahnhof Bus", BASE_LAT + 0.0301, BASE_LON, "")]
        trips = {
            "rail1": (2, [("A", "07:00:00", "07:00:00"), ("X", "07:05:00", "07:05:00"), ("T", "07:12:00", "07:12:00")]),
            "bus": (3, [("Y", "07:45:00", "07:45:00"), ("TB", "08:00:00", "08:00:00")]),
            "feeder": (3, [("X2", "07:20:00", "07:20:00"), ("Y", "07:30:00", "07:30:00")]),
        }
        projected = {sid: matrix.wgs84_to_lv95(lon, lat) for sid, _, lat, lon, _ in stops}
        squares = {261: square(*projected["T"], 300), 100: square(*projected["A"], 300),
                   200: square(*projected["X"], 300), 300: square(*projected["Y"], 300)}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.zip"
            write_feed(path, stops, trips)
            meta, files = matrix.build(path, topology_for(squares), [261], {100, 200, 300, 261}, DAY, "fixture")
        meta["feed"]["sha256"] = "0" * 64  # zip bytes carry timestamps
        meta["feed"]["bytes"] = 0
        content = json.dumps({"meta": meta, "to": files[261]}, ensure_ascii=False, indent=1) + "\n"
        if __import__("os").environ.get("UPDATE_MATRIX_CONTRACT"):
            CONTRACT.write_text(content, encoding="utf-8")
        self.assertEqual(CONTRACT.read_text(encoding="utf-8"), content)
        self.assertEqual([row[0] for row in files[261]["rows"]][0], 261)


class ReferenceComparison(unittest.TestCase):
    def test_statuses(self):
        import compare_reference
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "to").mkdir()
            (root / "to" / "261.json").write_text(json.dumps({"rows": [
                [261, 0, 0, "", 0], [198, 900, 0, "Uster", 1], [230, 1200, 0, "W", 1], [1322, 1500, 0, "Pfäffikon SZ", 1]]}))
            reference = root / "ref.csv"
            header = "pair,from,from_bfs,to,to_bfs,sbb_minutes,sbb_departure,same_stop,sbb_same_stop_minutes,retrieved,note\n"
            reference.write_text(header +
                                 "1,Uster,198,Zürich,261,17,,,,,\n2,Winterthur,230,Zürich,261,,,,,,\n"
                                 "3,Zug,1711,Zürich,261,25,,,,,\n4,Baden,4021,Zürich,261,35,,,,,\n"
                                 "5,Morges,5642,Lausanne,5586,10,,,,,\n6,Uster,198,Zürich,261,19,,,,,\n"
                                 # Faster stop elsewhere in the Gemeinde: judged against SBB from that stop.
                                 "7,Freienbach,1322,Zürich,261,32,,Pfäffikon SZ,26,,\n"
                                 "8,Freienbach,1322,Zürich,261,32,,Pfäffikon SZ,20,,\n"
                                 "9,Freienbach,1322,Zürich,261,32,,,,,\n"
                                 # Never slower than SBB from the main stop.
                                 "10,Winterthur,230,Zürich,261,15,,W,19,,\n")
            statuses = [r["status"] for r in compare_reference.compare(root, reference)]
        self.assertEqual(statuses, ["passed", "pending", "failed_missing", "consistent_beyond_cap",
                                    "not_a_computed_workplace", "pending_same_stop", "passed", "failed", "pending_same_stop",
                                    "failed"])

    def test_require_complete_fails_on_pending_pairs_of_computed_workplaces(self):
        import compare_reference
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "to").mkdir()
            (root / "to" / "261.json").write_text(json.dumps({"rows": [[261, 0, 0, "", 0], [198, 900, 0, "Uster", 1]]}))
            header = "pair,from,from_bfs,to,to_bfs,sbb_minutes,sbb_departure,same_stop,sbb_same_stop_minutes,retrieved,note\n"
            done, pending = root / "done.csv", root / "pending.csv"
            done.write_text(header + "1,Uster,198,Zürich,261,15,,Uster,15,,\n2,Morges,5642,Lausanne,5586,,,,,,\n")
            pending.write_text(header + "1,Uster,198,Zürich,261,,,,,,\n")
            args = ["--matrix", str(root), "--require-complete", "--reference"]
            self.assertEqual(compare_reference.main(args + [str(done)]), 0)
            self.assertEqual(compare_reference.main(args + [str(pending)]), 1)
            self.assertEqual(compare_reference.main(["--matrix", str(root), "--reference", str(pending)]), 0)

    def test_committed_matrix_passes_the_committed_reference(self):
        import compare_reference
        matrix_dir = Path(__file__).resolve().parents[2] / "site/data/travel/matrix"
        if not (matrix_dir / "meta.json").exists():
            self.skipTest("no committed matrix")
        reference = Path(__file__).resolve().parent / "sbb-reference-2026.csv"
        self.assertEqual(compare_reference.main(["--matrix", str(matrix_dir), "--reference", str(reference),
                                                 "--require-complete"]), 0)

    def test_committed_reference_keeps_all_30_spec_pairs(self):
        with (Path(__file__).resolve().parent / "sbb-reference-2026.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([int(r["pair"]) for r in rows], list(range(1, 31)))
