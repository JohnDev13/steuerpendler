"""Tests for the bounded source-scale Aarau canonical-event slice."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "travel"))

import canonical_event_slice as event_slice
import dated_route_profile as profile


def ride(number, trip, start, end, departure, arrival, *, sequence=1,
         pickup=0, drop_off=0, route=None):
    return profile.Connection(
        number, trip, route or f"R-{trip}", "S", sequence, sequence + 1,
        departure, arrival, start, end, pickup, drop_off)


def transfer(number, start, end, *, minimum=0, status="potentially_applicable",
             from_trip="", to_trip="", from_route="", to_route="", kind=2):
    return profile.TransferRule(
        number, start, end, from_route, to_route, from_trip, to_trip, kind,
        minimum if kind == 2 else None, "",
        sum(bool(value) for value in (from_trip, to_trip, from_route, to_route)),
        status)


class CanonicalEventSliceTests(unittest.TestCase):
    def test_event_keyed_results_match_exhaustive_tiny_paths_and_keep_direct_independent(self):
        rides = [
            ride(1, "BUS", "A", "X", 23_400, 23_500),
            ride(2, "TRAIN-B", "Y", "Z", 23_800, 24_000),
            ride(3, "DIRECT", "A", "Z", 23_400, 24_200),
            ride(4, "TRAIN-A", "Y", "Z", 23_800, 24_000),
        ]
        rules = [
            transfer(1, "X", "Y", minimum=240),
            transfer(2, "X", "Y", minimum=0, status="unresolved_route_conflict",
                     from_trip="BUS", to_trip="TRAIN-B"),
        ]
        records = event_slice.evaluate_events(
            rides, rules, {"Z"}, {"A": 999},
            source_uncertainty=("source_inventory_incomplete",))
        by_id = {record["event"]["connectionId"]: record for record in records}

        bus = by_id[1]
        self.assertEqual(bus["event"], {
            "connectionId": 1, "tripInstanceId": "BUS", "stopId": "A",
            "stopSequence": 1, "boardSeconds": 23_400, "originBfs": 999,
        })
        self.assertEqual(bus["allRoutes"]["status"], "best_found_unproven")
        self.assertEqual(bus["allRoutes"]["arrivalSeconds"], 24_000)
        self.assertEqual(bus["allRoutes"]["legs"][1]["trip_id"], "TRAIN-A")
        self.assertEqual(bus["directOnly"]["status"], "unknown")
        self.assertIn("source_inventory_incomplete", bus["allRoutes"]["unresolvedReasons"])
        self.assertNotIn("unreachable_proven", {result["status"] for record in records
                                                for result in (record["allRoutes"],
                                                               record["directOnly"])})
        self.assertNotIn("fastest_proven", {result["status"] for record in records
                                            for result in (record["allRoutes"],
                                                           record["directOnly"])})

    def test_exact_boundaries_in_seat_real_change_and_forbidden_specific_rule(self):
        rides = [
            ride(1, "THROUGH", "A", "B", 23_400, 23_500),
            ride(2, "THROUGH", "B", "Z", 23_510, 25_200, sequence=2,
                 pickup=1),
            ride(3, "LATE", "A", "Z", 30_600, 30_700),
            ride(4, "OUTSIDE", "A", "Z", 30_601, 30_700),
            ride(5, "BUS", "A", "X", 23_400, 23_500),
            ride(6, "RAIL", "Y", "Z", 23_800, 24_000),
        ]
        rules = [
            transfer(1, "X", "Y", minimum=240),
            transfer(2, "X", "Y", status="unresolved_route_conflict",
                     from_trip="BUS", to_trip="RAIL"),
        ]
        records = event_slice.evaluate_events(
            rides, rules, {"Z"}, {"A": 1}, source_uncertainty=("bounded_slice",))
        by_id = {record["event"]["connectionId"]: record for record in records}
        self.assertEqual(set(by_id), {1, 3, 5})
        self.assertEqual(by_id[1]["allRoutes"]["elapsedSeconds"], 1_800)
        self.assertEqual(by_id[1]["allRoutes"]["transferCount"], 0)
        self.assertEqual(len(by_id[1]["allRoutes"]["legs"]), 1)
        self.assertEqual(by_id[3]["allRoutes"]["elapsedSeconds"], 100)
        self.assertEqual(by_id[5]["allRoutes"]["status"], "unknown")
        self.assertIsNone(by_id[5]["allRoutes"]["arrivalSeconds"])

    def test_source_identity_requires_2026_date_and_fixed_transfer_pin(self):
        with self.assertRaisesRegex(event_slice.EventSliceError, 'transfer scope pin'):
            event_slice._validate_transfer_pin('0' * 64)
        for metadata in ({'service_date': '2026-10-26'}, {}, {'service_date': '2026-10-28'}):
            with self.assertRaisesRegex(event_slice.EventSliceError, 'service date'):
                event_slice._validate_service_date(metadata, 'synthetic input')

    def test_tiny_path_is_verified_against_independent_exhaustive_oracle(self):
        # No production evaluator in the oracle: enumerate all simple ride paths.
        rides = [ride(1,'BUS','A','X',23_400,23_500),
                 ride(2,'LATE','Y','Z',23_800,24_000),
                 ride(3,'SLOW','A','Z',23_400,24_200)]
        def edges(left, right):
            return (left.to_stop_id == 'X' and right.from_stop_id == 'Y'
                    and right.departure_seconds-left.arrival_seconds >= 240)
        paths = []
        def visit(path):
            last = path[-1]
            if last.to_stop_id == 'Z':
                paths.append(path)
                return
            for nxt in rides:
                if nxt.connection_id not in {x.connection_id for x in path} and edges(last,nxt):
                    visit(path+[nxt])
        for first in rides:
            if first.from_stop_id == 'A':visit([first])
        expected = min(paths,key=lambda path:(path[-1].arrival_seconds,
                                               len(path)-1,tuple(x.connection_id for x in path)))
        records = event_slice.evaluate_events(rides,[transfer(1,'X','Y',minimum=240)],
                          {'Z'},{'A':1},source_uncertainty=('bounded_slice',))
        actual = next(r['allRoutes'] for r in records if r['event']['connectionId']==expected[0].connection_id)
        self.assertEqual(actual['arrivalSeconds'],expected[-1].arrival_seconds)
        self.assertEqual([leg['trip_id'] for leg in actual['legs']],[x.trip_id for x in expected])

    def test_coverage_exposes_excluded_unassigned_first_board_events(self):
        self.assertEqual(event_slice._source_coverage(
            {'count.candidate_first_board_events':'373344'},295065),
            {'sourceCandidateFirstBoardEvents':373344,
             'excludedFirstBoardEvents':78279})
        for metadata,count in (({},1),({'count.candidate_first_board_events':'2'},3)):
            with self.assertRaisesRegex(event_slice.EventSliceError, 'coverage'):
                event_slice._source_coverage(metadata,count)

    def test_uncertainty_inventory_is_reason_coded_and_cannot_be_omitted(self):
        inventory = event_slice._uncertainty_inventory(
            {"count.quarantined_frequency_pairs": "278",
             "count.quarantined_non_exact_pairs":"17"},
            {"count.status.in_seat_candidate_unvalidated": "19170"},
            {"count.boundary_quarantined": "3565", "count.unassigned": "7841"},
            "PROVISIONAL_SOURCE_CANDIDATES")
        reasons = set(event_slice._uncertainty_reasons(inventory))
        self.assertTrue({"frequency_source_quarantined", "non_exact_source_quarantined",
                         "in_seat_ambiguity",
                         "boundary_board_stops_quarantined", "unassigned_board_stops",
                         "provisional_target_group"}.issubset(reasons))
        for missing in ('count.quarantined_frequency_pairs',
                        'count.quarantined_non_exact_pairs'):
            metadata={'count.quarantined_frequency_pairs':'0',
                      'count.quarantined_non_exact_pairs':'0'}
            del metadata[missing]
            with self.assertRaisesRegex(event_slice.EventSliceError, 'inventory'):
                event_slice._uncertainty_inventory(metadata,
                    {'count.status.in_seat_candidate_unvalidated':'0'},
                    {'count.boundary_quarantined':'0','count.unassigned':'0'},'PROVISIONAL')
        with self.assertRaisesRegex(event_slice.EventSliceError, 'inventory'):
            event_slice._uncertainty_inventory(
                {'count.quarantined_frequency_pairs':'-1',
                 'count.quarantined_non_exact_pairs':'0'},
                {'count.status.in_seat_candidate_unvalidated':'0'},
                {'count.boundary_quarantined':'0','count.unassigned':'0'},'PROVISIONAL')
        with self.assertRaisesRegex(event_slice.EventSliceError, 'inventory'):
            event_slice._uncertainty_inventory(
                {'count.quarantined_frequency_pairs':'0',
                 'count.quarantined_non_exact_pairs':'0'}, {},
                {'count.boundary_quarantined':'0','count.unassigned':'0'},'PROVISIONAL')
        provenance=event_slice._generator_provenance(['Z','A','Z'])
        self.assertEqual(provenance['destinationChildStopIds'],['A','Z'])
        self.assertEqual(len(provenance['generatorSha256']),64)
        with self.assertRaisesRegex(event_slice.EventSliceError, 'destination'):
            event_slice._generator_provenance([])
        with self.assertRaisesRegex(event_slice.EventSliceError, "nonempty"):
            event_slice.evaluate_events(
                [ride(1, "T", "A", "Z", 23_400, 23_500)], (), {"Z"}, {"A": 1},
                source_uncertainty=())


if __name__ == "__main__":
    unittest.main()
