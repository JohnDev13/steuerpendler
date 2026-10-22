"""Synthetic tests for one necessary-only Aarau transfer candidate."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))
import aarau_candidate_transfer as assessor


STREAM_SHA = "1a1173576d2f9873ca25eee057ed85fa1c9e6a949661a0a39d8eb94d9e4009ee"
LINEAGE = assessor.CandidateSourceLineage(
    candidate_stream_sha256=STREAM_SHA,
    source_gtfs_sha256="d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e",
    service_day="2026-10-27",
    stream_status="necessary_only",
)
BASE = {
    "first_board_seconds": 23_400,
    "first_board_stop_id": "origin-child",
    "first_leg_trip_id": "feeder-trip",
    "hub_stop_id": "hub-child",
    "hub_arrival_seconds": 24_000,
    "hub_drop_off_type": "0",
    "first_board_pickup_type": "0",
    "second_leg_trip_id": "aarau-trip",
    "second_leg_boarding_seconds": 24_120,
    "second_leg_arrival_seconds": 25_200,
    "total_transit_seconds": 1_800,
    "service_provenance": "calendar",
}
ROUTES = {"feeder-trip": "feeder-route", "aarau-trip": "aarau-route"}
PARENTS = {"hub-child": "hub-parent"}


def transfer_row(minimum="180", **changes):
    return {
        "from_stop_id": "hub-child",
        "to_stop_id": "hub-child",
        "from_route_id": "",
        "to_route_id": "",
        "from_trip_id": "",
        "to_trip_id": "",
        "transfer_type": "2",
        "min_transfer_time": minimum,
        "service_id": "",
    } | changes


def assess(*, candidate=None, routes=None, parents=None, rows=(), lineage=LINEAGE):
    return assessor.assess_candidate_transfer(
        BASE if candidate is None else candidate,
        ROUTES if routes is None else routes,
        PARENTS if parents is None else parents,
        rows,
        source_lineage=lineage,
    )


class CandidateTransferTests(unittest.TestCase):
    def test_same_child_same_parent_default_is_positive_and_preserves_evidence(self):
        candidate = BASE | {"diagnostic_marker": "raw-value"}
        result = assess(candidate=candidate)

        self.assertEqual(result.status, "feasible_one_transfer_positive")
        self.assertEqual(result.minimum_seconds, 120)
        self.assertEqual(result.available_seconds, 120)
        self.assertEqual(result.provenance, "swiss_same_parent_default")
        self.assertEqual(result.candidate_evidence, candidate)
        self.assertIsNot(result.candidate_evidence, candidate)
        self.assertEqual(result.source_lineage, LINEAGE)
        self.assertEqual(result.from_route_id, "feeder-route")
        self.assertEqual(result.to_route_id, "aarau-route")
        self.assertEqual(result.total_transit_seconds, 1_800)

    def test_default_requires_the_exact_hub_child_parent_mapping(self):
        result = assess(parents={})
        self.assertEqual(result.status, "unresolved")
        self.assertEqual(result.minimum_seconds, None)
        self.assertEqual(result.available_seconds, 120)
        self.assertEqual(result.provenance, "stop_parent_identity_not_evidenced")

    def test_explicit_directed_minimum_rejects_179_and_accepts_180(self):
        rule = transfer_row("180")
        short = assess(candidate=BASE | {
            "second_leg_boarding_seconds": 24_179,
            "second_leg_arrival_seconds": 25_200,
        }, rows=[rule])
        exact = assess(candidate=BASE | {
            "second_leg_boarding_seconds": 24_180,
            "second_leg_arrival_seconds": 25_200,
        }, rows=[rule])

        self.assertEqual(short.status, "insufficient_time")
        self.assertEqual(short.minimum_seconds, 180)
        self.assertEqual(short.available_seconds, 179)
        self.assertEqual(exact.status, "feasible_one_transfer_positive")
        self.assertEqual(exact.available_seconds, 180)

    def test_unresolved_transfer_classes_remain_distinct_from_rejection(self):
        cases = (
            transfer_row("", transfer_type="1"),
            transfer_row("", transfer_type="4", from_trip_id="feeder-trip",
                         to_trip_id="aarau-trip"),
            transfer_row("180", service_id="dated-service"),
        )
        for row in cases:
            with self.subTest(row=row):
                result = assess(rows=[row])
                self.assertEqual(result.status, "unresolved")
                self.assertIsNone(result.minimum_seconds)

    def test_forbidden_rule_remains_prohibited(self):
        result = assess(rows=[transfer_row("", transfer_type="3")])
        self.assertEqual(result.status, "prohibited")
        self.assertIsNone(result.minimum_seconds)
        self.assertIn("prohibited_type_3", result.provenance)

    def test_trip_and_route_specificity_use_exact_metadata(self):
        rows = [
            transfer_row("999"),
            transfer_row("180", from_route_id="feeder-route",
                         to_route_id="aarau-route"),
            transfer_row("120", from_trip_id="different-trip",
                         to_trip_id="aarau-trip"),
            transfer_row("121", from_trip_id="feeder-trip",
                         to_trip_id="aarau-trip"),
        ]
        result = assess(rows=rows)
        self.assertEqual(result.status, "insufficient_time")
        self.assertEqual(result.minimum_seconds, 121)
        self.assertIn("both_trips", result.provenance)

    def test_boarding_window_endpoints_are_inclusive(self):
        for first_board in (23_400, 30_600):
            with self.subTest(first_board=first_board):
                candidate = BASE | {
                    "first_board_seconds": first_board,
                    "hub_arrival_seconds": first_board + 60,
                    "second_leg_boarding_seconds": first_board + 180,
                    "second_leg_arrival_seconds": first_board + 1_800,
                }
                result = assess(candidate=candidate, rows=[transfer_row("120")])
                self.assertEqual(result.status, "feasible_one_transfer_positive")

        for first_board in (23_399, 30_601):
            with self.subTest(first_board=first_board):
                candidate = BASE | {
                    "first_board_seconds": first_board,
                    "hub_arrival_seconds": first_board + 60,
                    "second_leg_boarding_seconds": first_board + 180,
                    "second_leg_arrival_seconds": first_board + 1_800,
                }
                with self.assertRaisesRegex(assessor.CandidateTransferError,
                                            "first_board_seconds"):
                    assess(candidate=candidate)

    def test_elapsed_cap_is_inclusive_and_declared_total_must_match(self):
        accepted = BASE | {
            "hub_arrival_seconds": 23_500,
            "second_leg_boarding_seconds": 23_620,
            "second_leg_arrival_seconds": 25_200,
            "total_transit_seconds": 1_800,
        }
        self.assertEqual(assess(candidate=accepted).total_transit_seconds, 1_800)

        with self.assertRaisesRegex(assessor.CandidateTransferError, "1,800"):
            assess(candidate=accepted | {
                "second_leg_arrival_seconds": 25_201,
                "total_transit_seconds": 1_801,
            })
        with self.assertRaisesRegex(assessor.CandidateTransferError,
                                    "total_transit_seconds"):
            assess(candidate=accepted | {"total_transit_seconds": 1_799})

    def test_invalid_times_and_permissions_are_rejected(self):
        invalid = (
            ({"hub_arrival_seconds": -1}, "hub_arrival_seconds"),
            ({"hub_arrival_seconds": 24_121}, "chronology"),
            ({"second_leg_boarding_seconds": 23_999}, "chronology"),
            ({"second_leg_arrival_seconds": 24_119,
              "total_transit_seconds": 719}, "chronology"),
            ({"first_board_seconds": True}, "first_board_seconds"),
            ({"first_board_pickup_type": "1"}, "first_board_pickup_type"),
            ({"first_board_pickup_type": "2"}, "first_board_pickup_type"),
            ({"hub_drop_off_type": "1"}, "hub_drop_off_type"),
            ({"hub_drop_off_type": 0}, "hub_drop_off_type"),
        )
        for changes, message in invalid:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(assessor.CandidateTransferError, message):
                    assess(candidate=BASE | changes)

    def test_identifiers_distinct_trips_and_route_metadata_are_validated(self):
        cases = (
            (BASE | {"hub_stop_id": ""}, ROUTES, "hub_stop_id"),
            (BASE | {"second_leg_trip_id": "feeder-trip"},
             {"feeder-trip": "route"}, "distinct"),
            (BASE, {"feeder-trip": "feeder-route"}, "exactly"),
            (BASE, ROUTES | {"other-trip": "other-route"}, "exactly"),
            (BASE, {"feeder-trip": "feeder-route", "aarau-trip": ""},
             "route_id"),
            (BASE, {"wrong-trip": "feeder-route", "aarau-trip": "aarau-route"},
             "exactly"),
        )
        for candidate, routes, message in cases:
            with self.subTest(candidate=candidate, routes=routes):
                with self.assertRaisesRegex(assessor.CandidateTransferError, message):
                    assess(candidate=candidate, routes=routes)

    def test_missing_or_malformed_candidate_fields_and_lineage_are_rejected(self):
        missing = dict(BASE)
        del missing["hub_stop_id"]
        with self.assertRaisesRegex(assessor.CandidateTransferError, "hub_stop_id"):
            assess(candidate=missing)
        with self.assertRaisesRegex(assessor.CandidateTransferError,
                                    "CandidateSourceLineage"):
            assess(lineage={"candidate_stream_sha256": STREAM_SHA})
        with self.assertRaisesRegex(assessor.CandidateTransferError, "SHA-256"):
            assess(lineage=assessor.CandidateSourceLineage(
                candidate_stream_sha256="not-a-hash",
                source_gtfs_sha256=LINEAGE.source_gtfs_sha256,
                service_day=LINEAGE.service_day,
                stream_status=LINEAGE.stream_status,
            ))

    def test_transfer_minimum_is_not_added_to_elapsed_time(self):
        candidate = BASE | {
            "hub_arrival_seconds": 24_000,
            "second_leg_boarding_seconds": 24_180,
        }
        result = assess(candidate=candidate, rows=[transfer_row("180")])
        self.assertEqual(result.status, "feasible_one_transfer_positive")
        self.assertEqual(result.total_transit_seconds, 1_800)
        self.assertEqual(result.minimum_seconds, 180)


if __name__ == "__main__":
    unittest.main()
