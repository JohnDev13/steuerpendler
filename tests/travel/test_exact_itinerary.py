"""Synthetic exact-itinerary tests; no Swiss timetable data."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'travel'))
import gtfs_events as ge
from metric_probe import fixture


def event(trip_id, origin, destination, departure, arrival, sequence=1, *,
          board_allowed=True, alight_allowed=True):
    """Build one exact synthetic adjacent-stop event."""
    def clock(seconds):
        return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'

    return ge.ScheduledEvent(
        trip_id=trip_id, from_stop_id=origin, to_stop_id=destination,
        from_stop_sequence=sequence, to_stop_sequence=sequence + 1,
        departure_time=clock(departure), arrival_time=clock(arrival),
        departure_seconds=departure, arrival_seconds=arrival,
        board_allowed=board_allowed, alight_allowed=alight_allowed)


def transfer_row(origin, destination, minimum='0', **changes):
    return {
        'from_stop_id': origin,
        'to_stop_id': destination,
        'from_route_id': '',
        'to_route_id': '',
        'from_trip_id': '',
        'to_trip_id': '',
        'transfer_type': '2',
        'min_transfer_time': minimum,
        'service_id': '',
    } | changes


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
        self.assertEqual(
            itinerary.transfers,
            (exact.TransferFootpath('X', 'Y', 120),))
        self.assertEqual(itinerary.transfer_count, 1)

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

    def test_two_three_and_four_transfers_have_no_search_cap(self):
        import exact_itinerary as exact

        events = []
        footpaths = {}
        current = 7 * 3600
        for index in range(5):
            events.append(event(
                f'trip-{index}', f'board-{index}', f'alight-{index}',
                current, current + 120))
            current += 120
            if index < 4:
                footpaths[(f'alight-{index}', f'board-{index + 1}')] = 30
                current += 60

        for final_index, expected_transfers in ((2, 2), (3, 3), (4, 4)):
            itinerary = exact.find_itinerary(
                events[:final_index + 1], footpaths, {'board-0'},
                {f'alight-{final_index}'})
            self.assertIsNotNone(itinerary)
            self.assertEqual(itinerary.transfer_count, expected_transfers)
            self.assertLessEqual(itinerary.elapsed_seconds, 1800)

    def test_selected_elapsed_limit_is_exact_and_inclusive(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        events = [
            event('exact-1200', 'O', 'D', departure, departure + 1200),
            event('exact-1201', 'O', 'E', departure, departure + 1201),
        ]
        self.assertEqual(exact.find_itinerary(
            events, {}, {'O'}, {'D'}, max_elapsed_seconds=1200).elapsed_seconds, 1200)
        self.assertIsNone(exact.find_itinerary(
            events, {}, {'O'}, {'E'}, max_elapsed_seconds=1200))
        self.assertEqual(exact.find_itinerary(
            events, {}, {'O'}, {'E'}, max_elapsed_seconds=1201).elapsed_seconds, 1201)

    def test_first_board_edges_are_inclusive_but_later_boards_are_unrestricted(self):
        import exact_itinerary as exact

        start = 6 * 3600 + 30 * 60
        end = 8 * 3600 + 30 * 60
        events = [
            event('lower', 'O', 'X', start, start + 5 * 60),
            event('later', 'Y', 'D', start + 6 * 60, start + 8 * 60),
            event('upper', 'O', 'D', end, end + 300),
        ]
        itinerary = exact.find_itinerary(
            events[:2], {('X', 'Y'): 0}, {'O'}, {'D'})
        self.assertEqual(itinerary.first_board_seconds, start)
        self.assertEqual(itinerary.arrival_seconds, start + 8 * 60)
        self.assertEqual(exact.find_itinerary(
            [events[2]], {}, {'O'}, {'D'}).first_board_seconds, end)

        after_window = [
            event('near-upper', 'O', 'X', end - 2 * 60, end - 60),
            event('after-window', 'Y', 'D', end + 60, end + 5 * 60),
        ]
        self.assertEqual(exact.find_itinerary(
            after_window, {('X', 'Y'): 60}, {'O'}, {'D'}).arrival_seconds,
            end + 5 * 60)

    def test_faster_transfer_path_beats_slower_direct(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        events = [
            event('direct', 'O', 'D', departure, departure + 1000),
            event('first', 'O', 'X', departure, departure + 200),
            event('second', 'Y', 'D', departure + 300, departure + 700),
        ]
        itinerary = exact.find_itinerary(
            events, {('X', 'Y'): 60}, {'O'}, {'D'})
        self.assertEqual([leg.trip_id for leg in itinerary.transit_legs],
                         ['first', 'second'])
        self.assertEqual(itinerary.elapsed_seconds, 700)

    def test_same_trip_intermediate_calls_are_one_vehicle_leg(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        events = [
            event('through', 'O', 'M', departure, departure + 100, 1),
            event('through', 'M', 'D', departure + 120, departure + 300, 2),
        ]
        itinerary = exact.find_itinerary(events, {}, {'O'}, {'D'})
        self.assertEqual(len(itinerary.transit_legs), 2)
        self.assertEqual(itinerary.transfer_count, 0)
        self.assertIsNone(itinerary.transfer)

    def test_board_and_alight_permissions_apply_only_when_entering_or_leaving(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        through = [
            event('through', 'O', 'M', departure, departure + 100, 1,
                  alight_allowed=False),
            event('through', 'M', 'D', departure + 120, departure + 300, 2,
                  board_allowed=False),
        ]
        itinerary = exact.find_itinerary(through, {}, {'O'}, {'D'})
        self.assertEqual([leg.from_stop_id for leg in itinerary.transit_legs],
                         ['O', 'M'])
        self.assertIsNone(exact.find_itinerary(
            [event('no-board', 'O', 'D', departure, departure + 60,
                   board_allowed=False)], {}, {'O'}, {'D'}))
        self.assertIsNone(exact.find_itinerary(
            [event('no-alight', 'O', 'D', departure, departure + 60,
                   alight_allowed=False)], {}, {'O'}, {'D'}))

    def test_transfer_requires_permission_to_alight_and_board(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        for first_alight, second_board in ((False, True), (True, False)):
            with self.subTest(first_alight=first_alight,
                              second_board=second_board):
                events = [
                    event('first', 'O', 'X', departure, departure + 100,
                          alight_allowed=first_alight),
                    event('second', 'Y', 'D', departure + 200,
                          departure + 300, board_allowed=second_board),
                ]
                self.assertIsNone(exact.find_itinerary(
                    events, {('X', 'Y'): 0}, {'O'}, {'D'}))

    def test_equal_elapsed_prefers_fewer_vehicle_changes(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        events = [
            event('z-direct', 'O', 'D', departure, departure + 600),
            event('a-first', 'O', 'X', departure, departure + 200),
            event('a-second', 'Y', 'D', departure + 300, departure + 600),
        ]
        itinerary = exact.find_itinerary(
            events, {('X', 'Y'): 50}, {'O'}, {'D'})
        self.assertEqual([leg.trip_id for leg in itinerary.transit_legs], ['z-direct'])

    def test_missing_or_reverse_only_footpath_forbids_transfer(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        events = [
            event('first', 'O', 'X', departure, departure + 100),
            event('second', 'Y', 'D', departure + 200, departure + 300),
        ]
        self.assertIsNone(exact.find_itinerary(events, {}, {'O'}, {'D'}))
        self.assertIsNone(exact.find_itinerary(
            events, {('Y', 'X'): 0}, {'O'}, {'D'}))
        with self.assertRaises(ge.GtfsEventError):
            exact.find_itinerary(events, {('X', 'Y'): -1}, {'O'}, {'D'})

    def test_zero_time_cycle_terminates(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        events = [
            event('loop-a', 'A', 'B', departure, departure),
            event('loop-b', 'B', 'A', departure, departure),
            event('finish', 'A', 'D', departure, departure + 60),
        ]
        itinerary = exact.find_itinerary(
            events, {('B', 'B'): 0, ('A', 'A'): 0}, {'A'}, {'D'})
        self.assertEqual(itinerary.elapsed_seconds, 60)
        self.assertLessEqual(itinerary.transfer_count, 2)

    def test_direct_only_excludes_source_derived_staufen_fixture(self):
        """Source-derived example, not a complete scan or fastest-route proof."""
        import exact_itinerary as exact

        bus_stop = 'ch:1:sloid:78699_gen:missingSLOID_pf:B'
        lenzburg_bus = 'ch:1:sloid:78736:0:01'
        lenzburg_rail = 'ch:1:sloid:2119:3:3'
        aarau = 'ch:1:sloid:2113:3:4'
        events = [
            event('.ojp-92-390.1.TA.127.j26', bus_stop, lenzburg_bus,
                  6 * 3600 + 47 * 60, 6 * 3600 + 53 * 60),
            event('.ojp-91-37-E.1.TA.582.j26', lenzburg_rail, aarau,
                  6 * 3600 + 58 * 60, 7 * 3600 + 5 * 60),
        ]
        footpaths = {(lenzburg_bus, lenzburg_rail): 240}
        itinerary = exact.find_itinerary(events, footpaths, {bus_stop}, {aarau})
        self.assertEqual(itinerary.elapsed_seconds, 1080)
        self.assertEqual(itinerary.transfer_count, 1)
        self.assertIsNone(exact.find_itinerary(
            events, footpaths, {bus_stop}, {aarau}, direct_only=True))

    def test_trip_aware_staufen_transfer_retains_exact_rule_evidence(self):
        """Illustrative source-derived positive, not a whole-feed fastest proof."""
        import exact_itinerary as exact

        bus_stop = 'ch:1:sloid:78699_gen:missingSLOID_pf:B'
        lenzburg_bus = 'ch:1:sloid:78736:0:01'
        lenzburg_rail = 'ch:1:sloid:2119:3:3'
        aarau = 'ch:1:sloid:2113:3:4'
        bus_trip = '.ojp-92-390.1.TA.127.j26'
        train_trip = '.ojp-91-37-E.1.TA.582.j26'
        events = [
            event(bus_trip, bus_stop, lenzburg_bus,
                  6 * 3600 + 47 * 60, 6 * 3600 + 53 * 60),
            event(train_trip, lenzburg_rail, aarau,
                  6 * 3600 + 58 * 60, 7 * 3600 + 5 * 60),
        ]
        resolver = exact.DatedTransferResolver(
            [transfer_row(lenzburg_bus, lenzburg_rail, '240')], {},
            {bus_trip: '92-390-j26-1', train_trip: '91-37-E-j26-1'})

        itinerary = exact.find_itinerary(
            events, {}, {bus_stop}, {aarau}, transfer_resolver=resolver)

        self.assertEqual(itinerary.elapsed_seconds, 1080)
        self.assertEqual(itinerary.transfer_count, 1)
        self.assertEqual(itinerary.transfer.seconds, 240)
        self.assertEqual(itinerary.transfer.available_seconds, 300)
        self.assertEqual(
            itinerary.transfer.provenance,
            'transfers.txt row 1 (stop_pair, child_pair)')

    def test_trip_specific_prohibition_rejects_only_that_departing_trip(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        events = [
            event('arrive', 'O', 'X', departure, departure + 120),
            event('forbidden', 'Y', 'D', departure + 360, departure + 500),
            event('allowed', 'Y', 'D', departure + 420, departure + 600),
        ]
        rows = [
            transfer_row('X', 'Y', '180'),
            transfer_row('X', 'Y', '', transfer_type='3',
                         from_trip_id='arrive', to_trip_id='forbidden'),
        ]
        resolver = exact.DatedTransferResolver(
            rows, {}, {'arrive': 'bus', 'forbidden': 'fast', 'allowed': 'later'})

        itinerary = exact.find_itinerary(
            events, {('X', 'Y'): 0}, {'O'}, {'D'},
            transfer_resolver=resolver)

        self.assertEqual([leg.trip_id for leg in itinerary.transit_legs],
                         ['arrive', 'allowed'])
        self.assertEqual(itinerary.transfer.available_seconds, 300)

    def test_route_minimum_and_unresolved_rule_cannot_use_static_fallback(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        events = [
            event('arrive', 'O', 'X', departure, departure + 100),
            event('depart', 'Y', 'D', departure + 300, departure + 500),
        ]
        routes = {'arrive': 'bus', 'depart': 'rail'}
        static_fallback = {('X', 'Y'): 0}
        too_long = exact.DatedTransferResolver([
            transfer_row('X', 'Y', '0'),
            transfer_row('X', 'Y', '240', from_route_id='bus',
                         to_route_id='rail'),
        ], {}, routes)
        unresolved = exact.DatedTransferResolver([
            transfer_row('X', 'Y', '', transfer_type='1'),
        ], {}, routes)
        service_specific = exact.DatedTransferResolver([
            transfer_row('X', 'Y', '0', service_id='dated-service'),
        ], {}, routes)

        for resolver in (too_long, unresolved, service_specific):
            with self.subTest(resolver=resolver):
                self.assertIsNone(exact.find_itinerary(
                    events, static_fallback, {'O'}, {'D'},
                    transfer_resolver=resolver))

    def test_trip_aware_reverse_only_rule_and_four_changes_fail_closed_or_pass(self):
        import exact_itinerary as exact

        departure = 7 * 3600
        reverse_events = [
            event('arrive', 'O', 'X', departure, departure + 100),
            event('depart', 'Y', 'D', departure + 200, departure + 300),
        ]
        reverse = exact.DatedTransferResolver(
            [transfer_row('Y', 'X', '0')],
            {'X': 'X-parent', 'Y': 'Y-parent'},
            {'arrive': 'r0', 'depart': 'r1'})
        self.assertIsNone(exact.find_itinerary(
            reverse_events, {('X', 'Y'): 0}, {'O'}, {'D'},
            transfer_resolver=reverse))

        events = []
        rows = []
        routes = {}
        current = departure
        for index in range(5):
            trip = f'trip-{index}'
            routes[trip] = f'route-{index}'
            events.append(event(
                trip, f'board-{index}', f'alight-{index}', current, current + 120))
            current += 120
            if index < 4:
                rows.append(transfer_row(
                    f'alight-{index}', f'board-{index + 1}', '30'))
                current += 60
        resolver = exact.DatedTransferResolver(rows, {}, routes)
        itinerary = exact.find_itinerary(
            events, {}, {'board-0'}, {'alight-4'}, transfer_resolver=resolver)
        self.assertEqual(itinerary.transfer_count, 4)
        self.assertEqual(itinerary.elapsed_seconds, 14 * 60)

    def test_invalid_events_and_limits_fail_closed_without_mutating_inputs(self):
        import exact_itinerary as exact

        invalid = event('bad', 'O', 'D', 100, 99)
        events = [invalid]
        footpaths = {('X', 'Y'): 0}
        with self.assertRaises(ge.GtfsEventError):
            exact.find_itinerary(events, footpaths, {'O'}, {'D'})
        with self.assertRaises(ge.GtfsEventError):
            exact.find_itinerary([], footpaths, {'O'}, {'D'}, max_elapsed_seconds=-1)
        with self.assertRaises(ge.GtfsEventError):
            exact.find_itinerary([], footpaths, {'O'}, {'D'}, max_elapsed_seconds=1801)
        with self.assertRaises(ge.GtfsEventError):
            exact.find_itinerary([object()], footpaths, {'O'}, {'D'})
        self.assertEqual(events, [invalid])
        self.assertEqual(footpaths, {('X', 'Y'): 0})


if __name__ == '__main__':
    unittest.main()
