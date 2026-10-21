"""Synthetic access-option tests; SYN IDs are not authentic Swiss routes."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'travel'))

from gtfs_events import ScheduledEvent


def event(trip, origin, destination, departure, arrival, sequence=1):
    return ScheduledEvent(
        trip_id=trip,
        from_stop_id=origin,
        to_stop_id=destination,
        from_stop_sequence=sequence,
        to_stop_sequence=sequence + 1,
        departure_time='',
        arrival_time='',
        departure_seconds=departure,
        arrival_seconds=arrival,
    )


class AccessOptionTests(unittest.TestCase):
    def setUp(self):
        import access_options as access

        self.access = access
        self.destination = access.DestinationTarget(
            parent_stop_id='SYN_AARAU_PARENT',
            platform_stop_ids=('SYN_AARAU_PLATFORM',),
            evidence_ref='fixture:synthetic-destination',
        )
        self.transfers = {('SYN_LENZ_BUS_BAY', 'SYN_LENZ_RAIL'): 240}
        self.events = [
            event('SYN_BUS', 'SYN_STAUFEN_BUS', 'SYN_LENZ_BUS_BAY',
                  6 * 3600 + 50 * 60, 6 * 3600 + 51 * 60),
            event('SYN_TRAIN', 'SYN_LENZ_RAIL', 'SYN_AARAU_PLATFORM',
                  7 * 3600, 7 * 3600 + 12 * 60),
        ]

    def candidate(self, parent, platform, walk, evidence='fixture:synthetic-access'):
        return self.access.AccessCandidate(
            parent_stop_id=parent,
            platform_stop_ids=(platform,),
            external_walk_seconds=walk,
            evidence_ref=evidence,
        )

    def test_near_direct_walk_to_rail_beats_bus_but_farther_case_uses_bus(self):
        bus = self.candidate('SYN_STAUFEN_BUS_PARENT', 'SYN_STAUFEN_BUS', 120)
        near_rail = self.candidate('SYN_LENZ_RAIL_PARENT', 'SYN_LENZ_RAIL', 600)
        far_rail = self.candidate('SYN_LENZ_RAIL_PARENT', 'SYN_LENZ_RAIL', 840)

        near = self.access.build_access_options(
            self.events, self.transfers, [bus, near_rail], self.destination)
        far = self.access.build_access_options(
            self.events, self.transfers, [bus, far_rail], self.destination)

        self.assertEqual(len(near), 2)
        self.assertEqual(self.access.select_option(near, 15, 30).origin_parent_id,
                         'SYN_LENZ_RAIL_PARENT')
        self.assertEqual(self.access.select_option(far, 15, 30).origin_parent_id,
                         'SYN_STAUFEN_BUS_PARENT')
        bus_option = next(o for o in near
                          if o.origin_parent_id == 'SYN_STAUFEN_BUS_PARENT')
        self.assertEqual(bus_option.transit_seconds, 22 * 60)
        self.assertEqual(bus_option.transfer_seconds, 240)

    def test_transfer_minimum_is_directed_and_never_inferred_as_zero(self):
        bus = self.candidate('SYN_STAUFEN_BUS_PARENT', 'SYN_STAUFEN_BUS', 120)

        missing = self.access.build_access_options(
            self.events, {}, [bus], self.destination)
        reverse_only = self.access.build_access_options(
            self.events, {('SYN_LENZ_RAIL', 'SYN_LENZ_BUS_BAY'): 240},
            [bus], self.destination)
        directed = self.access.build_access_options(
            self.events, self.transfers, [bus], self.destination)

        self.assertEqual(missing, ())
        self.assertEqual(reverse_only, ())
        self.assertEqual(directed[0].transfer_seconds, 240)

    def test_first_board_window_is_inclusive_and_one_second_outside_is_rejected(self):
        start = 6 * 3600 + 30 * 60
        end = 8 * 3600 + 30 * 60
        candidate = self.candidate('SYN_ORIGIN_PARENT', 'SYN_ORIGIN', 1)
        for departure in (start, end):
            with self.subTest(departure=departure):
                options = self.access.build_access_options(
                    [event(f'SYN_{departure}', 'SYN_ORIGIN', 'SYN_AARAU_PLATFORM',
                           departure, departure + 60)],
                    {}, [candidate], self.destination)
                self.assertEqual(options[0].first_board_seconds, departure)

        for departure in (start - 1, end + 1):
            with self.subTest(departure=departure):
                options = self.access.build_access_options(
                    [event(f'SYN_{departure}', 'SYN_ORIGIN', 'SYN_AARAU_PLATFORM',
                           departure, departure + 60)],
                    {}, [candidate], self.destination)
                self.assertEqual(options, ())

    def test_ceil_minutes_separate_caps_and_optional_combined_cap(self):
        candidate = self.candidate('SYN_ORIGIN_PARENT', 'SYN_ORIGIN', 15 * 60)
        departure = 7 * 3600
        options = self.access.build_access_options(
            [event('SYN_CAP', 'SYN_ORIGIN', 'SYN_AARAU_PLATFORM',
                   departure, departure + 15 * 60)],
            {}, [candidate], self.destination)

        self.assertEqual(self.access.ceil_minutes(1), 1)
        self.assertEqual(self.access.ceil_minutes(60), 1)
        self.assertEqual(len(self.access.eligible_options(options, 15, 15)), 1)
        self.assertEqual(self.access.eligible_options(options, 14, 15), ())
        self.assertEqual(self.access.eligible_options(options, 15, 14), ())
        self.assertEqual(
            self.access.eligible_options(options, 15, 29, count_walk=True), ())
        self.assertEqual(
            len(self.access.eligible_options(options, 15, 30, count_walk=True)), 1)

    def test_requested_caps_cannot_exceed_supported_controls(self):
        for method in (self.access.eligible_options, self.access.select_option):
            with self.subTest(method=method.__name__, cap='walk'):
                with self.assertRaises(self.access.AccessOptionError):
                    method((), 16, 30)
            with self.subTest(method=method.__name__, cap='transit'):
                with self.assertRaises(self.access.AccessOptionError):
                    method((), 15, 31)

    def test_nondominated_frontier_keeps_short_walk_fallback(self):
        departure = 7 * 3600
        events = [
            event('SYN_FAST', 'SYN_FAST_ORIGIN', 'SYN_AARAU_PLATFORM',
                  departure, departure + 10 * 60),
            event('SYN_SHORT_WALK', 'SYN_NEAR_ORIGIN', 'SYN_AARAU_PLATFORM',
                  departure, departure + 18 * 60),
        ]
        candidates = [
            self.candidate('SYN_FAST_PARENT', 'SYN_FAST_ORIGIN', 14 * 60),
            self.candidate('SYN_NEAR_PARENT', 'SYN_NEAR_ORIGIN', 2 * 60),
        ]

        options = self.access.build_access_options(
            events, {}, candidates, self.destination)

        self.assertEqual(len(options), 2)
        self.assertEqual(self.access.select_option(options, 15, 15).origin_parent_id,
                         'SYN_FAST_PARENT')
        self.assertEqual(self.access.select_option(options, 5, 20).origin_parent_id,
                         'SYN_NEAR_PARENT')

    def test_dominated_and_equal_metric_routes_resolve_stably(self):
        departure = 7 * 3600
        events = [
            event('SYN_TRIP_Z', 'SYN_Z', 'SYN_AARAU_PLATFORM', departure, departure + 600),
            event('SYN_TRIP_A', 'SYN_A', 'SYN_AARAU_PLATFORM', departure, departure + 600),
            event('SYN_DOMINATED', 'SYN_D', 'SYN_AARAU_PLATFORM', departure, departure + 601),
        ]
        candidates = [
            self.candidate('SYN_PARENT_Z', 'SYN_Z', 120),
            self.candidate('SYN_PARENT_A', 'SYN_A', 120),
            self.candidate('SYN_PARENT_D', 'SYN_D', 120),
        ]

        options = self.access.build_access_options(events, {}, candidates, self.destination)

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].origin_parent_id, 'SYN_PARENT_A')

    def test_supported_build_bounds_use_ceiling(self):
        departure = 7 * 3600
        for walk_seconds in (0, 15 * 60):
            with self.subTest(bound='transit-exact', walk_seconds=walk_seconds):
                candidate = self.candidate('SYN_TRANSIT_EXACT', 'SYN_ORIGIN', walk_seconds)
                options = self.access.build_access_options(
                    [event('SYN_TRANSIT_EXACT', 'SYN_ORIGIN', 'SYN_AARAU_PLATFORM',
                           departure, departure + 30 * 60)],
                    {}, [candidate], self.destination)
                self.assertEqual(options[0].transit_seconds, 30 * 60)

            with self.subTest(bound='transit-over', walk_seconds=walk_seconds):
                candidate = self.candidate('SYN_TRANSIT_OVER', 'SYN_ORIGIN', walk_seconds)
                options = self.access.build_access_options(
                    [event('SYN_TRANSIT_OVER', 'SYN_ORIGIN', 'SYN_AARAU_PLATFORM',
                           departure, departure + 30 * 60 + 1)],
                    {}, [candidate], self.destination)
                self.assertEqual(options, ())

        for walk_seconds, expected_count in ((15 * 60, 1), (15 * 60 + 1, 0)):
            with self.subTest(bound='walk', walk_seconds=walk_seconds):
                candidate = self.candidate('SYN_WALK', 'SYN_ORIGIN', walk_seconds)
                options = self.access.build_access_options(
                    [event('SYN_WALK', 'SYN_ORIGIN', 'SYN_AARAU_PLATFORM',
                           departure, departure + 60)],
                    {}, [candidate], self.destination)
                self.assertEqual(len(options), expected_count)

    def test_missing_or_invalid_access_evidence_fails_closed(self):
        bad_candidates = [
            self.candidate('', 'SYN_PLATFORM', 1),
            self.candidate('SYN_PARENT', '', 1),
            self.candidate('SYN_PARENT', 'SYN_PLATFORM', -1),
            self.candidate('SYN_PARENT', 'SYN_PLATFORM', 1, evidence=''),
        ]
        for candidate in bad_candidates:
            with self.subTest(candidate=candidate):
                with self.assertRaises(self.access.AccessOptionError):
                    self.access.build_access_options(
                        self.events, self.transfers, [candidate], self.destination)

        with self.assertRaises(self.access.AccessOptionError):
            self.access.build_access_options(
                self.events, self.transfers, [None], self.destination)

        invalid_destination = self.access.DestinationTarget(
            'SYN_AARAU_PARENT', ('SYN_AARAU_PLATFORM',), '')
        with self.assertRaises(self.access.AccessOptionError):
            self.access.build_access_options(
                self.events, self.transfers, [], invalid_destination)


if __name__ == '__main__':
    unittest.main()
