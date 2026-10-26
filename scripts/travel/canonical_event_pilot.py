#!/usr/bin/env python3
"""Bounded first-board-event routing-semantics pilot.

This evaluator accepts only small pinned fixtures.  It is not a national router,
GTFS importer, canonical-file generator, or proof about unsearched source data.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import pathlib
from typing import Any

FIRST_BOARD_START = 23_400
FIRST_BOARD_END = 30_600
MAX_ELAPSED = 1_800
MAX_EVENTS = 1_000


class PilotInputError(ValueError):
    """The bounded fixture cannot be evaluated safely."""


@dataclasses.dataclass(frozen=True)
class Evaluation:
    route: dict[str, Any]
    event_ids: tuple[str, ...]
    change_count: int | None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PilotInputError(message)


def _event_key(event: dict[str, Any]) -> tuple[Any, ...]:
    return (event["departureSeconds"], event["arrivalSeconds"],
            event["tripInstanceId"], event["fromStopId"],
            event["fromSequence"], event["id"])


def _stable_path(events: tuple[dict[str, Any], ...]) -> tuple[Any, ...]:
    return tuple((event["tripInstanceId"], event["fromStopId"],
                  event["fromSequence"], event["id"]) for event in events)


def _validate_case(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    events = case.get("events")
    _require(isinstance(events, list), "events must be a list")
    _require(0 < len(events) <= MAX_EVENTS,
             "fixture must contain between 1 and 1,000 events")
    by_id: dict[str, dict[str, Any]] = {}
    required_strings = ("id", "tripId", "tripInstanceId", "routeId", "serviceId",
                        "fromStopId", "toStopId")
    required_ints = ("fromSequence", "toSequence", "departureSeconds", "arrivalSeconds")
    for event in events:
        _require(isinstance(event, dict), "each event must be an object")
        _require(all(isinstance(event.get(key), str) and event[key]
                     for key in required_strings), "event identifiers must be nonempty strings")
        _require(all(type(event.get(key)) is int for key in required_ints),
                 "event sequences and times must be integers")
        _require(event["id"] not in by_id, "event IDs must be unique")
        _require(event["fromSequence"] < event["toSequence"],
                 "event stop sequences must increase")
        _require(0 <= event["departureSeconds"] < event["arrivalSeconds"],
                 "event rides require positive duration; zero-duration source edges remain unresolved")
        _require(type(event.get("pickupAllowed")) is bool
                 and type(event.get("dropOffAllowed")) is bool,
                 "pickup/drop-off flags must be booleans")
        _require(event.get("exact") is True,
                 "materialized events must have exact scheduled times")
        by_id[event["id"]] = event
    first_id = case.get("forcedFirstEventId")
    _require(first_id in by_id, "forced first event is missing")
    first = by_id[first_id]
    _require(first["pickupAllowed"], "forced first event does not allow pickup")
    _require(FIRST_BOARD_START <= first["departureSeconds"] <= FIRST_BOARD_END,
             "forced first event is outside the inclusive board window")
    destinations = case.get("destinationStopIds")
    _require(isinstance(destinations, list) and destinations
             and all(isinstance(item, str) and item for item in destinations),
             "destination stop group must be nonempty")
    _require(type(case.get("destinationBfs")) is int and case["destinationBfs"] > 0,
             "destination BFS must be a positive integer")
    reasons = case.get("unresolvedReasons", [])
    _require(isinstance(reasons, list) and len(reasons) == len(set(reasons))
             and all(isinstance(item, str) and item for item in reasons),
             "unresolved reasons must be unique nonempty strings")
    for item in case.get("continuations", []):
        _require(item.get("fromEventId") in by_id and item.get("toEventId") in by_id,
                 "continuation references an unknown event")
        _require(item.get("status") in {"authorized", "forbidden"},
                 "continuation status is unsupported")
        _require(isinstance(item.get("source"), str) and item["source"],
                 "continuation requires source authority")
    return by_id


def _specificity(rule: dict[str, Any]) -> int:
    from_kind = ("trip" if rule.get("fromTripId") else
                 "route" if rule.get("fromRouteId") else None)
    to_kind = ("trip" if rule.get("toTripId") else
               "route" if rule.get("toRouteId") else None)
    kinds = (from_kind, to_kind)
    if kinds == ("trip", "trip"):
        return 6
    if set(kinds) == {"trip", "route"}:
        return 5
    if "trip" in kinds:
        return 4
    if kinds == ("route", "route"):
        return 3
    if "route" in kinds:
        return 2
    return 1


def _rule_matches(rule: dict[str, Any], left: dict[str, Any],
                  right: dict[str, Any]) -> bool:
    selectors = (("fromStopId", left["toStopId"]),
                 ("toStopId", right["fromStopId"]),
                 ("fromTripId", left["tripId"]),
                 ("toTripId", right["tripId"]),
                 ("fromRouteId", left["routeId"]),
                 ("toRouteId", right["routeId"]))
    return all(not rule.get(key) or rule[key] == actual
               for key, actual in selectors)


def _transition(case: dict[str, Any], left: dict[str, Any],
                right: dict[str, Any]) -> tuple[int, int, str] | None:
    if right["departureSeconds"] < left["arrivalSeconds"]:
        return None
    if (left["tripInstanceId"] == right["tripInstanceId"]
            and left["toStopId"] == right["fromStopId"]
            and left["toSequence"] == right["fromSequence"]):
        return 0, 0, "same trip instance"
    continuation = [item for item in case.get("continuations", [])
                    if item["fromEventId"] == left["id"]
                    and item["toEventId"] == right["id"]]
    if continuation:
        _require(len(continuation) == 1, "duplicate continuation authority")
        item = continuation[0]
        if item["status"] == "authorized":
            return 0, 0, item["source"]
        return None
    if not left["dropOffAllowed"] or not right["pickupAllowed"]:
        return None
    rules = [rule for rule in case.get("transferRules", [])
             if _rule_matches(rule, left, right)]
    if not rules:
        return None
    maximum = max(_specificity(rule) for rule in rules)
    dominant = [rule for rule in rules if _specificity(rule) == maximum]
    if any(rule.get("status") == "forbidden" for rule in dominant):
        return None
    minima = {rule.get("minimumSeconds") for rule in dominant
              if rule.get("status") == "minimum"}
    if len(minima) != 1 or any(type(value) is not int or value < 0 for value in minima):
        return None
    minimum = next(iter(minima))
    if right["departureSeconds"] - left["arrivalSeconds"] < minimum:
        return None
    sources = sorted({rule.get("source", "") for rule in dominant})
    if not sources or not sources[0]:
        raise PilotInputError("transfer rule requires source authority")
    return 1, minimum, "; ".join(sources)


def _legs(path: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    for event in path:
        if not groups or groups[-1][-1]["tripInstanceId"] != event["tripInstanceId"]:
            groups.append([])
        groups[-1].append(event)
    return [{
        "tripId": group[0]["tripId"],
        "tripInstanceId": group[0]["tripInstanceId"],
        "routeId": group[0]["routeId"],
        "serviceId": group[0]["serviceId"],
        "boardStopId": group[0]["fromStopId"],
        "alightStopId": group[-1]["toStopId"],
        "boardSequence": group[0]["fromSequence"],
        "alightSequence": group[-1]["toSequence"],
        "boardSeconds": group[0]["departureSeconds"],
        "alightSeconds": group[-1]["arrivalSeconds"],
    } for group in groups]


def evaluate_case(case: dict[str, Any]) -> Evaluation:
    """Evaluate one forced first-board event against a tiny exact event graph."""
    by_id = _validate_case(case)
    first = by_id[case["forcedFirstEventId"]]
    ordered = sorted(by_id.values(), key=_event_key)
    # Each event has a fixed arrival time, so fewer changes and stable IDs dominate
    # any other way of reaching the same event.
    labels: dict[str, tuple[int, tuple[Any, ...], tuple[dict[str, Any], ...],
                            tuple[tuple[int, int, str], ...]]] = {
        first["id"]: (0, _stable_path((first,)), (first,), ())
    }
    for left in ordered:
        label = labels.get(left["id"])
        if label is None:
            continue
        for right in ordered:
            if right["id"] in {item["id"] for item in label[2]}:
                continue
            if right["arrivalSeconds"] - first["departureSeconds"] > MAX_ELAPSED:
                continue
            transition = _transition(case, left, right)
            if transition is None:
                continue
            path = label[2] + (right,)
            changes = label[0] + transition[0]
            candidate = (changes, _stable_path(path), path,
                         label[3] + (transition,))
            current = labels.get(right["id"])
            if current is None or candidate[:2] < current[:2]:
                labels[right["id"]] = candidate

    candidates = []
    destinations = set(case["destinationStopIds"])
    for event_id, label in labels.items():
        event = by_id[event_id]
        elapsed = event["arrivalSeconds"] - first["departureSeconds"]
        if event["toStopId"] in destinations and event["dropOffAllowed"] and elapsed <= MAX_ELAPSED:
            candidates.append((event["arrivalSeconds"], label[0], label[1], label))
    # The fixture does not establish completeness of the national timetable.
    # Even an exhaustive search of this tiny graph cannot prove a public
    # fastest journey or a negative municipality-level reachability claim.
    reasons = sorted(set(case.get("unresolvedReasons", [])) | {"pilot_not_source_complete"})
    origin = {
        "tripId": first["tripId"], "tripInstanceId": first["tripInstanceId"],
        "stopId": first["fromStopId"], "stopSequence": first["fromSequence"],
        "boardSeconds": first["departureSeconds"],
    }
    if not candidates:
        route = {"kind": "route", "schemaVersion": 1, "origin": origin,
                 "destinationBfs": case["destinationBfs"], "status": "unknown",
                 "itinerary": None, "unresolvedReasons": reasons}
        return Evaluation(route, (), None)

    _, changes, _, label = min(candidates, key=lambda item: item[:3])
    path = label[2]
    transitions = label[3]
    legs = _legs(path)
    transfers = []
    for left, right, transition in zip(path, path[1:], transitions):
        if transition[0] == 0:
            continue
        transfers.append({
            "fromStopId": left["toStopId"], "toStopId": right["fromStopId"],
            "fromTripInstanceId": left["tripInstanceId"],
            "toTripInstanceId": right["tripInstanceId"],
            "arrivalSeconds": left["arrivalSeconds"],
            "departureSeconds": right["departureSeconds"],
            "minimumSeconds": transition[1], "source": transition[2],
        })
    arrival = path[-1]["arrivalSeconds"]
    elapsed = arrival - first["departureSeconds"]
    status = "best_found_unproven"
    route = {
        "kind": "route", "schemaVersion": 1, "origin": origin,
        "destinationBfs": case["destinationBfs"], "status": status,
        "itinerary": {
            "arrivalStopId": path[-1]["toStopId"], "arrivalSeconds": arrival,
            "elapsedSeconds": elapsed, "minutes": math.ceil(elapsed / 60),
            "legs": legs, "transfers": transfers,
        },
        "unresolvedReasons": reasons,
    }
    return Evaluation(route, tuple(event["id"] for event in path), changes)


def evaluate_fixture(payload: dict[str, Any]) -> list[Evaluation]:
    _require(payload.get("schema") == "steuerpendler.canonical-event-pilot-fixture.v1",
             "fixture schema mismatch")
    cases = payload.get("cases")
    _require(isinstance(cases, list) and cases, "fixture cases must be nonempty")
    _require(sum(len(case.get("events", [])) for case in cases) <= MAX_EVENTS,
             "fixture must contain at most 1,000 events")
    return [evaluate_case(case) for case in cases]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    payload = json.loads(args.fixture.read_text(encoding="utf-8"))
    results = evaluate_fixture(payload)
    output = {
        "schema": "steuerpendler.canonical-event-pilot-result.v1",
        "sourceKind": payload.get("sourceKind"),
        "sourcePins": payload.get("sourcePins", {}),
        "routes": [result.route for result in results],
    }
    text = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
