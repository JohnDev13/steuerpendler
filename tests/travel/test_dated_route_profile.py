"""Tests for the bounded exact-second one-destination route-profile pilot."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))

import dated_route_profile as profile


def connection(number, trip, start, end, departure, arrival, *, route=None,
               pickup=0, drop_off=0, from_sequence=1, to_sequence=2):
    return profile.Connection(
        number, trip, route or f"R-{trip}", "S", from_sequence, to_sequence,
        departure, arrival, start, end, pickup, drop_off)


def rule(number, start, end, *, kind=2, minimum=0, status="potentially_applicable",
         from_trip="", to_trip="", from_route="", to_route="", service=""):
    return profile.TransferRule(
        number, start, end, from_route, to_route, from_trip, to_trip,
        kind, minimum if kind == 2 else None, service,
        sum(bool(item) for item in (from_trip, to_trip, from_route, to_route)), status)


class RouteProfileTests(unittest.TestCase):
    def solve(self, connections, *, rules=(), targets=("Z",), **changes):
        arguments = {
            "connections": connections,
            "transfer_rules": rules,
            "target_stop_ids": targets,
            "first_board_start": 23_400,
            "first_board_end": 30_600,
            "max_elapsed": 1_800,
        }
        arguments.update(changes)
        return profile.build_profile(**arguments)

    def test_path_with_four_changes_has_no_change_cap(self):
        rides = []
        rules = []
        stops = list("ABCDEF")
        for index in range(5):
            departure = 23_400 + index * 300
            rides.append(connection(index + 1, f"T{index}", stops[index], stops[index + 1],
                                    departure, departure + 120))
            if index < 4:
                rules.append(rule(index + 1, stops[index + 1], stops[index + 1]))
        result = self.solve(rides, rules=rules, targets=("F",))[1]
        self.assertEqual(result.status, "fastest_proven")
        self.assertEqual(result.transfer_count, 4)
        self.assertEqual(result.arrival_seconds, 24_720)

    def test_no_pickup_does_not_break_same_trip_through_rider(self):
        rides = [
            connection(1, "T", "A", "B", 23_400, 23_500, to_sequence=2),
            connection(2, "T", "B", "Z", 23_510, 23_700,
                       pickup=1, from_sequence=2, to_sequence=3),
        ]
        result = self.solve(rides)[1]
        self.assertEqual(result.status, "fastest_proven")
        self.assertEqual([leg.connection_ids for leg in result.legs], [(1, 2)])
        self.assertEqual(result.transfer_count, 0)
        self.assertNotIn(2, self.solve(rides))

    def test_directed_cross_stop_minimum_accepts_300_rejects_239(self):
        rules = [rule(1, "BUS", "RAIL", minimum=240)]
        accepted = [
            connection(1, "BUS-1", "A", "BUS", 23_400, 23_500),
            connection(2, "TRAIN", "RAIL", "Z", 23_800, 24_000),
        ]
        rejected = [accepted[0], connection(3, "TRAIN2", "RAIL", "Z", 23_739, 24_000)]
        self.assertEqual(self.solve(accepted, rules=rules)[1].status, "fastest_proven")
        self.assertEqual(self.solve(rejected, rules=rules)[1].status, "unknown")
        self.assertEqual(self.solve(accepted, rules=[rule(2, "RAIL", "BUS", minimum=240)])[1].status,
                         "unknown")

    def test_no_rule_same_stop_change_fails_closed(self):
        rides = [connection(1, "A", "O", "X", 23_400, 23_500),
                 connection(2, "B", "X", "Z", 23_600, 23_700)]
        self.assertEqual(self.solve(rides)[1].status, "unknown")

    def test_destination_requires_drop_off_rights(self):
        prohibited = [connection(1, "T1", "A", "Z", 23_400, 23_600, drop_off=1)]
        allowed_later = prohibited + [connection(2, "T2", "A", "Z", 23_500, 23_750)]
        self.assertEqual(self.solve(prohibited)[1].status, "unknown")
        self.assertEqual(self.solve(allowed_later)[2].arrival_seconds, 23_750)

    def test_transfer_requires_drop_off_rights_even_with_explicit_rule(self):
        rides = [connection(1, "BUS", "A", "X", 23_400, 23_500, drop_off=1),
                 connection(2, "TRAIN", "Y", "Z", 23_800, 24_000)]
        self.assertEqual(self.solve(rides, rules=[rule(1, "X", "Y", minimum=240)])[1].status,
                         "unknown")

    def test_board_window_and_elapsed_boundaries_are_inclusive(self):
        rides = [
            connection(1, "EARLY", "A", "Z", 23_399, 23_500),
            connection(2, "START", "A", "Z", 23_400, 25_200),
            connection(3, "TOO-LONG", "A", "Z", 23_401, 25_202),
            connection(4, "END", "A", "Z", 30_600, 30_700),
            connection(5, "LATE", "A", "Z", 30_601, 30_700),
        ]
        results = self.solve(rides)
        self.assertEqual(set(results), {2, 3, 4})
        self.assertEqual(results[2].status, "fastest_proven")
        self.assertEqual(results[2].elapsed_seconds, 1_800)
        self.assertEqual(results[3].status, "unknown")
        self.assertEqual(results[4].status, "fastest_proven")

    def test_equal_arrival_prefers_fewer_transfers_then_stable_trip(self):
        rides = [
            connection(1, "DIRECT-B", "A", "Z", 23_400, 24_000),
            connection(2, "X", "A", "B", 23_400, 23_600),
            connection(3, "Y", "B", "Z", 23_700, 24_000),
            connection(4, "DIRECT-A", "A", "Z", 23_400, 24_000),
        ]
        result = self.solve(rides, rules=[rule(1, "B", "B")])[4]
        self.assertEqual(result.transfer_count, 0)
        self.assertEqual(result.legs[0].trip_id, "DIRECT-A")

    def test_unknown_selector_and_in_seat_ambiguity_preserve_uncertainty(self):
        rides = [
            connection(1, "A", "O", "X", 23_400, 23_500),
            connection(2, "B", "X", "Z", 23_600, 23_700),
        ]
        rules = [
            rule(1, "X", "X"),
            rule(2, "X", "X", status="unresolved_service", service="CUSTOM"),
            rule(3, "", "", kind=4, status="in_seat_candidate_unvalidated",
                 from_trip="A", to_trip="B"),
        ]
        result = self.solve(rides, rules=rules)[1]
        self.assertEqual(result.status, "unknown")
        self.assertEqual(set(result.unresolved_reasons),
                         {"unresolved_transfer_selector", "in_seat_ambiguity", "no_evidenced_path"})

    def test_rule_service_scope_is_not_outgoing_trip_service_selector(self):
        rides = [connection(1, "A", "O", "X", 23_400, 23_500),
                 connection(2, "B", "Y", "Z", 23_800, 24_000)]
        scoped = rule(1, "X", "Y", minimum=240, service="DAY-SCOPE")
        self.assertEqual(self.solve(rides, rules=[scoped])[1].arrival_seconds, 24_000)

    def test_equal_specificity_competing_rules_fail_closed(self):
        rides = [connection(1, "A", "O", "X", 23_400, 23_500),
                 connection(2, "B", "Y", "Z", 23_800, 24_000)]
        rules = [rule(1, "X", "Y", minimum=240),
                 rule(2, "X", "Y", kind=1)]
        result = self.solve(rides, rules=rules)[1]
        self.assertEqual(result.status, "unknown")

    def test_more_specific_unresolved_rule_cannot_be_overridden_by_generic_minimum(self):
        rides = [connection(1, "BUS", "A", "X", 23_400, 23_500),
                 connection(2, "TRAIN", "Y", "Z", 23_800, 24_000)]
        rules = [rule(1, "X", "Y", minimum=240),
                 rule(2, "X", "Y", status="unresolved_route_conflict",
                      from_trip="BUS", to_trip="TRAIN")]
        self.assertEqual(self.solve(rides, rules=rules)[1].status, "unknown")

    def test_repeat_is_deterministic(self):
        rides = [connection(2, "B", "A", "Z", 23_400, 23_500),
                 connection(1, "A", "A", "Z", 23_400, 23_500)]
        first = self.solve(rides)
        second = self.solve(list(reversed(rides)))
        self.assertEqual(first, second)

    def test_source_run_requires_explicit_transfer_scope_pin(self):
        with self.assertRaisesRegex(profile.RouteProfileError, "expected transfer-scope"):
            profile.run_pilot("missing", "missing", "missing", "missing", "missing")


if __name__ == "__main__":
    unittest.main()
