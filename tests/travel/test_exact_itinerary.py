"""Synthetic exact-itinerary tests; no Swiss timetable data."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'travel'))
import gtfs_events as ge
from metric_probe import fixture


class ExactItineraryTests(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed, _ = fixture(pathlib.Path(tmp))
            self.events = ge.scheduled_events(feed, __import__('datetime').date(2027, 1, 12))

    def test_minimum_direct_elapsed_uses_inclusive_upper_boundary(self):
        import exact_itinerary as exact

        itinerary = exact.find_itinerary(
            self.events, {}, {'A1', 'A2'}, {'B1'},
            start_time='06:30:00', end_time='08:30:00')

        self.assertEqual(itinerary.first_board_seconds, 8 * 3600 + 30 * 60)
        self.assertEqual(itinerary.arrival_seconds, 8 * 3600 + 31 * 60)
        self.assertEqual(itinerary.elapsed_seconds, 60)
        self.assertEqual([leg.trip_id for leg in itinerary.transit_legs], ['upper-inclusive'])

        rare = exact.find_itinerary(
            [event for event in self.events if event.trip_id == 'rare-second'],
            {}, {'A2'}, {'B1'})
        self.assertEqual(rare.elapsed_seconds, 121)

    def test_explicit_transfer_footpath_counts_walk_and_wait(self):
        import exact_itinerary as exact

        transfer_events = [event for event in self.events
                           if event.trip_id.startswith('transfer-')]
        itinerary = exact.find_itinerary(
            transfer_events, {('X', 'Y'): 120}, {'A1'}, {'B1'})

        self.assertEqual(itinerary.first_board_seconds, 7 * 3600)
        self.assertEqual(itinerary.arrival_seconds, 7 * 3600 + 14 * 60)
        self.assertEqual(itinerary.elapsed_seconds, 14 * 60)
        self.assertEqual([leg.trip_id for leg in itinerary.transit_legs],
                         ['transfer-first', 'transfer-second'])
        self.assertEqual(
            itinerary.transfer,
            exact.TransferFootpath('X', 'Y', 120))

    def test_no_service_and_footpath_only_return_no_itinerary(self):
        import exact_itinerary as exact

        self.assertIsNone(exact.find_itinerary(
            self.events, {('N', 'B1'): 1}, {'N'}, {'B1'}))
        self.assertIsNone(exact.find_itinerary(
            [], {('N', 'B1'): 1}, {'N'}, {'B1'}))

    def test_extended_gtfs_seconds_do_not_wrap(self):
        import exact_itinerary as exact

        event = ge.ScheduledEvent(
            trip_id='after-midnight', from_stop_id='A1', to_stop_id='B1',
            from_stop_sequence=1, to_stop_sequence=2,
            departure_time='25:00:00', arrival_time='25:05:00',
            departure_seconds=90000, arrival_seconds=90300)
        itinerary = exact.find_itinerary(
            [event], {}, {'A1'}, {'B1'},
            start_time='25:00:00', end_time='25:00:00')

        self.assertEqual(itinerary.elapsed_seconds, 300)
        self.assertEqual(itinerary.arrival_seconds, 90300)


if __name__ == '__main__':
    unittest.main()
