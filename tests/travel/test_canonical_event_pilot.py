"""Independent exhaustive-oracle tests for the canonical event pilot."""
import json
import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = pathlib.Path(__file__).with_name("fixtures")
sys.path.insert(0, str(ROOT / "scripts" / "travel"))

import canonical_event_pilot as pilot


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _specificity(rule):
    return sum(bool(rule.get(key)) for key in
               ("fromTripId", "toTripId", "fromRouteId", "toRouteId"))


def _rule_matches(rule, left, right):
    pairs = (("fromStopId", left["toStopId"]), ("toStopId", right["fromStopId"]),
             ("fromTripId", left["tripId"]), ("toTripId", right["tripId"]),
             ("fromRouteId", left["routeId"]), ("toRouteId", right["routeId"]))
    return all(not rule.get(key) or rule[key] == value for key, value in pairs)


def exhaustive_oracle(case):
    """Tiny brute-force oracle; it does not import production graph logic."""
    events = {event["id"]: event for event in case["events"]}
    first = events[case["forcedFirstEventId"]]
    continuations = {(item["fromEventId"], item["toEventId"]): item
                     for item in case.get("continuations", [])
                     if item["status"] == "authorized"}
    candidates = []

    def transition(left, right):
        continuation = continuations.get((left["id"], right["id"]))
        if continuation and right["departureSeconds"] >= left["arrivalSeconds"]:
            return 0
        if not left["dropOffAllowed"] or not right["pickupAllowed"]:
            return None
        matches = [rule for rule in case.get("transferRules", [])
                   if _rule_matches(rule, left, right)]
        if not matches:
            return None
        maximum = max(_specificity(rule) for rule in matches)
        dominant = [rule for rule in matches if _specificity(rule) == maximum]
        if any(rule["status"] == "forbidden" for rule in dominant):
            return None
        minima = {rule["minimumSeconds"] for rule in dominant
                  if rule["status"] == "minimum"}
        if len(minima) != 1:
            return None
        return 1 if right["departureSeconds"] - left["arrivalSeconds"] >= next(iter(minima)) else None

    def visit(path, changes):
        last = path[-1]
        if (last["toStopId"] in case["destinationStopIds"]
                and last["dropOffAllowed"]
                and last["arrivalSeconds"] - first["departureSeconds"] <= 1800):
            stable = tuple((item["tripInstanceId"], item["fromStopId"],
                            item["fromSequence"], item["id"]) for item in path)
            candidates.append((last["arrivalSeconds"], changes, stable,
                               tuple(item["id"] for item in path)))
        for event in events.values():
            if event in path or not event["exact"]:
                continue
            if event["departureSeconds"] < last["arrivalSeconds"]:
                continue
            change = transition(last, event)
            if change is not None:
                visit(path + [event], changes + change)

    visit([first], 0)
    return min(candidates) if candidates else None


class CanonicalEventPilotTests(unittest.TestCase):
    def test_synthetic_cases_match_independent_exhaustive_oracle(self):
        fixture = load("canonical-event-pilot-synthetic.json")
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                expected = exhaustive_oracle(case)
                actual = pilot.evaluate_case(case)
                if expected is None:
                    self.assertEqual(actual.route["status"], "unknown")
                    self.assertIsNone(actual.route["itinerary"])
                else:
                    self.assertEqual(actual.route["status"], "best_found_unproven")
                    self.assertEqual(actual.event_ids, expected[3])
                    self.assertEqual(actual.change_count, expected[1])
                    self.assertEqual(actual.route["itinerary"]["arrivalSeconds"], expected[0])

    def test_semantics_and_proof_statuses(self):
        cases = {item["id"]: item for item in
                 load("canonical-event-pilot-synthetic.json")["cases"]}
        in_seat = pilot.evaluate_case(cases["authorized_in_seat"])
        self.assertEqual(in_seat.change_count, 0)
        self.assertEqual(in_seat.event_ids, ("c1", "c2"))
        self.assertEqual(in_seat.route["itinerary"]["transfers"], [])
        through = copy.deepcopy(cases["authorized_in_seat"])
        through["events"][0]["dropOffAllowed"] = False
        through["events"][1]["pickupAllowed"] = False
        expected_through = exhaustive_oracle(through)
        assert expected_through is not None
        self.assertEqual(expected_through[3], ("c1", "c2"))
        self.assertEqual(pilot.evaluate_case(through).event_ids, ("c1", "c2"))
        self.assertEqual(pilot.evaluate_case(cases["block_id_insufficient"]).route["status"],
                         "unknown")
        self.assertEqual(pilot.evaluate_case(cases["specific_forbidden_over_generic"]).route["status"],
                         "unknown")
        destination = pilot.evaluate_case(cases["destination_group_no_free_transfer"])
        self.assertEqual(destination.route["itinerary"]["arrivalStopId"], "Z1")
        uncertain = pilot.evaluate_case(cases["uncertain_frequency"])
        self.assertEqual(uncertain.route["status"], "best_found_unproven")
        self.assertEqual(uncertain.route["unresolvedReasons"],
                         ["non_exact_frequency_may_improve", "pilot_not_source_complete"])
        tie = pilot.evaluate_case(cases["tie_break_stable_ids"])
        self.assertEqual(tie.event_ids, ("t0", "tA"))
        edge = pilot.evaluate_case(cases["elapsed_cap_inclusive"])
        self.assertEqual(edge.route["itinerary"]["elapsedSeconds"], 1800)
        self.assertEqual(edge.route["origin"]["boardSeconds"], 30600)

    def test_disembark_and_zero_duration_are_fail_closed(self):
        cases = {item["id"]: item for item in
                 load("canonical-event-pilot-synthetic.json")["cases"]}
        disembark = copy.deepcopy(cases["destination_group_no_free_transfer"])
        disembark["events"][0]["dropOffAllowed"] = False
        self.assertEqual(pilot.evaluate_case(disembark).route["status"], "unknown")
        zero_ride = copy.deepcopy(cases["authorized_in_seat"])
        zero_ride["events"][0]["arrivalSeconds"] = zero_ride["events"][0]["departureSeconds"]
        with self.assertRaisesRegex(pilot.PilotInputError, "positive duration"):
            pilot.evaluate_case(zero_ride)

    def test_authentic_staufen_excerpt_is_source_pinned_and_provisional(self):
        fixture = load("canonical-event-pilot-staufen.json")
        self.assertEqual(fixture["sourcePins"]["gtfsSha256"],
                         "d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e")
        witness = json.loads((ROOT / "site/data/travel/aarau-transfer-witness-20261027.json")
                             .read_text(encoding="utf-8"))
        self.assertEqual(fixture["sourcePins"]["sourceWitnessSha256"],
                         witness["sourceWitnessSha256"])
        result = pilot.evaluate_case(fixture["cases"][0])
        self.assertEqual(result.route["status"], "best_found_unproven")
        self.assertEqual(result.route["origin"]["boardSeconds"], witness["firstBoardSeconds"])
        self.assertEqual(result.route["itinerary"]["elapsedSeconds"], witness["elapsedSeconds"])
        self.assertEqual(result.route["itinerary"]["arrivalSeconds"], witness["arrivalSeconds"])
        self.assertEqual(result.change_count, 1)
        self.assertEqual(result.route["itinerary"]["transfers"][0]["minimumSeconds"],
                         witness["minimumTransferSeconds"])

    def test_pilot_routes_conform_to_canonical_record_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema not installed; schema validation requires the dependency")
        schema = json.loads((ROOT / "docs/travel/canonical-route-v1.schema.json")
                            .read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for name in ("canonical-event-pilot-synthetic.json", "canonical-event-pilot-staufen.json"):
            for case in load(name)["cases"]:
                with self.subTest(fixture=name, case=case["id"]):
                    validator.validate(pilot.evaluate_case(case).route)

    def test_fixture_limits_and_forced_first_board_are_enforced(self):
        case = load("canonical-event-pilot-synthetic.json")["cases"][0]
        broken = dict(case, forcedFirstEventId="missing")
        with self.assertRaisesRegex(pilot.PilotInputError, "forced first event"):
            pilot.evaluate_case(broken)
        excessive = dict(case, events=case["events"] * 501)
        with self.assertRaisesRegex(pilot.PilotInputError, "1,000"):
            pilot.evaluate_case(excessive)


if __name__ == "__main__":
    unittest.main()
