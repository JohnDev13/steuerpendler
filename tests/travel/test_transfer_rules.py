"""Synthetic directed GTFS transfer-rule tests; no real journey claims."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'travel'))
import transfer_rules as rules


PARENTS = {'A-platform': 'A', 'B-platform': 'B', 'A-bus': 'A'}
PAIR = {
    'from_stop_id': 'A-platform',
    'to_stop_id': 'A-bus',
    'from_trip_id': 'arriving',
    'to_trip_id': 'departing',
    'from_route_id': 'rail',
    'to_route_id': 'bus',
    'arrival_seconds': 25_000,
    'departure_seconds': 25_600,
}


def resolve(rows, **changes):
    pair = PAIR | changes
    return rules.resolve_transfer(rows, PARENTS, **pair)


def row(minimum: object = '120', **changes):
    return {
        'from_stop_id': 'A-platform',
        'to_stop_id': 'A-bus',
        'from_route_id': '',
        'to_route_id': '',
        'from_trip_id': '',
        'to_trip_id': '',
        'transfer_type': '2',
        'min_transfer_time': minimum,
        'service_id': '',
    } | changes


class TransferRuleTests(unittest.TestCase):
    def test_gtfs_trip_and_route_specificity_overrides_generic_not_smallest(self):
        rows = (
            item for item in [
                row('60'),
                row('700', from_route_id='rail', to_route_id='bus'),
                row('650', from_trip_id='arriving'),
                row('600', from_trip_id='arriving', to_route_id='bus'),
                row('550', from_trip_id='arriving', to_trip_id='departing'),
            ]
        )

        result = resolve(rows)

        self.assertEqual(result.status, 'allowed')
        self.assertEqual(result.minimum_seconds, 550)
        self.assertEqual(result.available_seconds, 600)
        self.assertEqual(result.provenance, 'transfers.txt row 5 (both_trips, child_pair)')

    def test_station_parent_fallback_and_explicit_child_override(self):
        parent_only = row('240', from_stop_id='A', to_stop_id='A')
        result = resolve([parent_only])
        self.assertEqual((result.status, result.minimum_seconds), ('allowed', 240))
        self.assertEqual(result.provenance, 'transfers.txt row 1 (stop_pair, parent_pair)')

        child = row('480')
        result = resolve([parent_only, child])
        self.assertEqual((result.status, result.minimum_seconds), ('allowed', 480))
        self.assertEqual(result.provenance, 'transfers.txt row 2 (stop_pair, child_pair)')

    def test_parent_selector_and_child_stop_specificity_tradeoff_is_unresolved(self):
        # GTFS documents route/trip order and parent expansion separately. Do
        # not invent a winner when their precedence dimensions disagree.
        parent_trip = row('180', from_stop_id='A', to_stop_id='A',
                          from_trip_id='arriving')
        child_pair = row('300')
        result = resolve([parent_trip, child_pair],
                         arrival_seconds=25_000, departure_seconds=25_240)
        self.assertEqual((result.status, result.minimum_seconds), ('unresolved', None))
        self.assertIn('competing_stop_selector_specificity', result.provenance)

    def test_direction_and_exact_temporal_boundary(self):
        forward = row('120')
        reverse = row('999', from_stop_id='A-bus', to_stop_id='A-platform')

        exact = resolve([reverse, forward], arrival_seconds=25_000, departure_seconds=25_120)
        short = resolve([reverse, forward], arrival_seconds=25_000, departure_seconds=25_119)

        self.assertEqual(exact.status, 'allowed')
        self.assertEqual(short.status, 'insufficient_time')
        self.assertEqual(short.minimum_seconds, 120)

    def test_swiss_default_requires_evidenced_shared_parent(self):
        same = resolve([])
        distinct = resolve([], to_stop_id='B-platform')
        unevidenced = resolve([], to_stop_id='unknown-child')

        self.assertEqual((same.status, same.minimum_seconds, same.provenance),
                         ('allowed', 120, 'swiss_same_parent_default'))
        self.assertEqual((distinct.status, distinct.minimum_seconds, distinct.provenance),
                         ('unresolved', None, 'no_applicable_rule_for_distinct_parents'))
        self.assertEqual((unevidenced.status, unevidenced.minimum_seconds, unevidenced.provenance),
                         ('unresolved', None, 'stop_parent_identity_not_evidenced'))

    def test_unsupported_classes_and_service_extension_are_unresolved(self):
        cases = [
            (row('', transfer_type='1'), 'timed_transfer_type_1'),
            (row('', transfer_type='4', from_trip_id='arriving',
                 to_trip_id='departing'), 'in_seat_transfer_type_4'),
            (row('', transfer_type='4', from_stop_id='', to_stop_id='',
                 from_trip_id='arriving', to_trip_id='departing'),
             'in_seat_transfer_type_4'),
            (row('120', service_id='dated-service'), 'transfer_service_id'),
        ]
        for transfer_row, provenance in cases:
            with self.subTest(provenance=provenance):
                result = resolve([transfer_row])
                self.assertEqual((result.status, result.minimum_seconds), ('unresolved', None))
                self.assertIn(provenance, result.provenance)

    def test_applicable_type_3_is_prohibited(self):
        result = resolve([row('', transfer_type='3')])
        self.assertEqual((result.status, result.minimum_seconds), ('prohibited', None))
        self.assertEqual(result.provenance,
                         'transfers.txt row 1 (stop_pair, child_pair): prohibited_type_3')

    def test_equal_maximal_conflicts_and_invalid_durations_fail_closed(self):
        conflict = resolve([
            row('120', from_route_id='rail'),
            row('180', to_route_id='bus'),
        ])
        self.assertEqual((conflict.status, conflict.minimum_seconds), ('unresolved', None))
        self.assertEqual(conflict.provenance,
                         'conflicting equally specific transfers.txt rows 1,2')

        for invalid in ('', '-1', '12.5', ' 120', None):
            with self.subTest(invalid=invalid):
                result = resolve([row(invalid)])
                self.assertEqual((result.status, result.minimum_seconds), ('unresolved', None))
                self.assertIn('invalid_min_transfer_time', result.provenance)

    def test_destination_entrance_walking_is_not_added(self):
        result = resolve([], arrival_seconds=25_000, departure_seconds=25_120)
        self.assertEqual((result.status, result.minimum_seconds, result.available_seconds),
                         ('allowed', 120, 120))
        self.assertEqual(result.provenance, 'swiss_same_parent_default')

    def test_invalid_event_times_fail_closed(self):
        for changes in (
            {'arrival_seconds': -1},
            {'departure_seconds': 24_999},
            {'arrival_seconds': True},
        ):
            with self.subTest(changes=changes):
                result = resolve([], **changes)
                self.assertEqual((result.status, result.minimum_seconds), ('unresolved', None))
                self.assertEqual(result.provenance, 'invalid_scheduled_times')


if __name__ == '__main__':
    unittest.main()
