import datetime as dt
import unittest

from scripts.travel.aarau_nomination_probe import (
    active_services,
    assign_stops,
    population_centre,
    rank_stations,
)


class AarauNominationProbeTest(unittest.TestCase):
    def test_calendar_exceptions_and_parent_ranking(self):
        day = dt.date(2026, 11, 17)
        calendar = [
            {"service_id": "base", "start_date": "20260101", "end_date": "20261231", "tuesday": "1"},
            {"service_id": "removed", "start_date": "20260101", "end_date": "20261231", "tuesday": "1"},
        ]
        exceptions = [
            {"service_id": "removed", "date": "20261117", "exception_type": "2"},
            {"service_id": "added", "date": "20261117", "exception_type": "1"},
        ]
        services = active_services(day, calendar, exceptions)
        self.assertEqual(services, {"base", "added"})
        stops = {
            "a1": {"parent_station": "P-A"}, "a2": {"parent_station": "P-A"},
            "b": {"parent_station": ""}, "P-A": {"parent_station": ""},
        }
        trips = {"t1": "base", "t2": "added", "t3": "removed"}
        rows = [
            {"trip_id": "t1", "stop_id": "a1", "stop_sequence": "1", "departure_time": "06:00:00"},
            {"trip_id": "t1", "stop_id": "a1", "stop_sequence": "1", "departure_time": "06:00:00"},
            {"trip_id": "t2", "stop_id": "a2", "stop_sequence": "4", "departure_time": "09:00:00"},
            {"trip_id": "t2", "stop_id": "b", "stop_sequence": "5", "departure_time": "07:00:00"},
            {"trip_id": "t3", "stop_id": "b", "stop_sequence": "2", "departure_time": "07:00:00"},
            {"trip_id": "t1", "stop_id": "b", "stop_sequence": "8", "departure_time": "09:00:01"},
        ]
        self.assertEqual(rank_stations(stops, trips, rows, services, {"a1", "a2", "b"}), [("P-A", 2), ("b", 1)])
        with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
            rank_stations(stops, trips, rows + [{"trip_id":"t1","stop_id":"b","stop_sequence":"1","departure_time":"06:00:00"}], services, {"a1", "a2", "b"})

    def test_population_weighted_centre_missing_and_fallback(self):
        polygon = [[(0, 0), (300, 0), (300, 200), (0, 200), (0, 0)]]
        cells = [
            {"E_KOORD": "0", "N_KOORD": "0", "BBTOT": "10"},
            {"E_KOORD": "100", "N_KOORD": "0", "BBTOT": "30"},
            {"E_KOORD": "400", "N_KOORD": "0", "BBTOT": "999"},
            {"E_KOORD": "200", "N_KOORD": "0", "BBTOT": ""},
        ]
        self.assertEqual(population_centre(cells, [polygon]), ((125.0, 50.0), "statpop", 40))
        point, source, total = population_centre([], [polygon])
        self.assertEqual((source, total), ("polygon-representative-point", 0))
        self.assertTrue(0 <= point[0] <= 300 and 0 <= point[1] <= 200)

    def test_stop_spatial_assignment(self):
        polygons = {
            "4001": [[[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]],
            "4201": [[[(20, 0), (30, 0), (30, 10), (20, 10), (20, 0)]]],
        }
        stops = {"in-a": (5, 5), "in-l": (25, 5), "outside": (15, 5)}
        self.assertEqual(assign_stops(stops, polygons), {"4001": {"in-a"}, "4201": {"in-l"}})


if __name__ == "__main__":
    unittest.main()
