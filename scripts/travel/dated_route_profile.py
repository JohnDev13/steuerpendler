#!/usr/bin/env python3
"""Bounded exact-second shared reverse profile pilot for one destination.

This is deliberately a diagnostic router, not a canonical-route generator.  It
scans each ride connection once in reverse departure order and shares the
resulting destination labels between all first-board events.  Unresolved
transfer evidence is retained as uncertainty rather than converted to a
negative route claim.
"""
from __future__ import annotations

import argparse
import bisect
import dataclasses
import hashlib
import json
import pathlib
import resource
import sqlite3
import time
from collections import defaultdict


CONNECTION_SHA256 = "fc98b4195f0275dca6e0443c1fdcb63158f9127b30f5f13583ed285f9b6600fb"
BOARD_STOP_SHA256 = "53380d7c232074d6097148a7c29a08fe6e3f06213a2301b91a6fb281714f36bb"
TARGET_REGISTRY_SHA256 = "d8a8a926d33f3e3c39be27a053409460f9b78a41faa9f5fc2d3c4af4cbd6f7fb"
FIRST_BOARD_START = 23_400
FIRST_BOARD_END = 30_600
MAX_ELAPSED = 1_800


class RouteProfileError(ValueError):
    """Input evidence cannot safely support the pilot."""


@dataclasses.dataclass(frozen=True)
class Connection:
    connection_id: int
    trip_id: str
    route_id: str
    service_id: str
    from_stop_sequence: int
    to_stop_sequence: int
    departure_seconds: int
    arrival_seconds: int
    from_stop_id: str
    to_stop_id: str
    from_pickup_type: int = 0
    to_drop_off_type: int = 0


@dataclasses.dataclass(frozen=True)
class TransferRule:
    rule_id: int
    from_stop_id: str
    to_stop_id: str
    from_route_id: str
    to_route_id: str
    from_trip_id: str
    to_trip_id: str
    transfer_type: int
    min_transfer_time: int | None
    service_id: str
    selector_specificity: int
    applicability_status: str


@dataclasses.dataclass(frozen=True)
class Leg:
    trip_id: str
    route_id: str
    service_id: str
    board_stop_id: str
    alight_stop_id: str
    board_seconds: int
    alight_seconds: int
    connection_ids: tuple[int, ...]


@dataclasses.dataclass(frozen=True)
class ProfileResult:
    status: str
    first_board_seconds: int
    arrival_seconds: int | None
    elapsed_seconds: int | None
    transfer_count: int | None
    legs: tuple[Leg, ...]
    transfer_rule_ids: tuple[int, ...]
    unresolved_reasons: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class _Path:
    connections: tuple[Connection, ...]
    transfer_rule_ids: tuple[int, ...]
    unresolved_reasons: tuple[str, ...] = ()

    @property
    def arrival(self):
        return self.connections[-1].arrival_seconds

    @property
    def transfers(self):
        return sum(left.trip_id != right.trip_id
                   for left, right in zip(self.connections, self.connections[1:]))

    def key(self):
        stable = tuple((item.trip_id, item.from_stop_id, item.to_stop_id,
                        item.from_stop_sequence, item.connection_id)
                       for item in self.connections)
        return self.arrival, self.transfers, stable


def _matches(rule, incoming, outgoing):
    selectors = (
        (rule.from_stop_id, incoming.to_stop_id),
        (rule.to_stop_id, outgoing.from_stop_id),
        (rule.from_route_id, incoming.route_id),
        (rule.to_route_id, outgoing.route_id),
        (rule.from_trip_id, incoming.trip_id),
        (rule.to_trip_id, outgoing.trip_id),
    )
    return all(not selected or selected == actual for selected, actual in selectors)


def _transition(incoming, outgoing, rules):
    matching = [item for item in rules if _matches(item, incoming, outgoing)]
    if not matching:
        return False, None, ()
    # A more-specific unvalidated rule may override an otherwise usable
    # stop-only minimum. Never prove the lower-priority transfer in that case.
    maximum = max(item.selector_specificity for item in matching)
    matching = [item for item in matching if item.selector_specificity == maximum]
    unresolved = []
    for item in matching:
        if item.applicability_status in {"unresolved_service", "unresolved_route_conflict"}:
            unresolved.append("unresolved_transfer_selector")
        if item.transfer_type == 4 or item.applicability_status == "in_seat_candidate_unvalidated":
            unresolved.append("in_seat_ambiguity")
    usable = [item for item in matching
              if item.applicability_status == "potentially_applicable"
              and item.transfer_type in (1, 2)]
    if len(usable) != len(matching):
        return False, None, tuple(sorted(set(unresolved) |
                                         {"dominant_transfer_rule_unvalidated"}))
    if usable:
        semantics = {(item.transfer_type, item.min_transfer_time,
                      bool(item.from_trip_id), bool(item.to_trip_id))
                     for item in usable}
        if len(semantics) != 1:
            return False, None, tuple(sorted(set(unresolved) |
                                             {"competing_transfer_rules"}))
    usable.sort(key=lambda item: item.rule_id)
    for item in usable:
        wait = outgoing.departure_seconds - incoming.arrival_seconds
        if item.transfer_type == 2 and wait >= (item.min_transfer_time or 0):
            return True, item.rule_id, tuple(sorted(set(unresolved)))
        if item.transfer_type == 1:
            # A timed transfer is accepted only when both source trips select the
            # exact pair.  A generic type-1 row is not enough to prove timing.
            if item.from_trip_id and item.to_trip_id and wait >= 0:
                return True, item.rule_id, tuple(sorted(set(unresolved)))
            unresolved.append("timed_transfer_unvalidated")
    return False, None, tuple(sorted(set(unresolved)))


def _legs(connections):
    groups = []
    current = []
    for item in connections:
        if current and item.trip_id != current[-1].trip_id:
            groups.append(current)
            current = []
        current.append(item)
    if current:
        groups.append(current)
    return tuple(Leg(
        group[0].trip_id, group[0].route_id, group[0].service_id,
        group[0].from_stop_id, group[-1].to_stop_id,
        group[0].departure_seconds, group[-1].arrival_seconds,
        tuple(item.connection_id for item in group)) for group in groups)


def _result(first, path, global_uncertainty):
    if path is None:
        reasons = tuple(sorted(set(global_uncertainty) | {"no_evidenced_path"}))
        return ProfileResult("unknown", first.departure_seconds, None, None, None,
                             (), (), reasons)
    elapsed = path.arrival - first.departure_seconds
    if elapsed > MAX_ELAPSED:
        reasons = tuple(sorted(set(global_uncertainty) | {"outside_elapsed_cap"}))
        return ProfileResult("unknown", first.departure_seconds, None, None, None,
                             (), (), reasons)
    reasons = tuple(sorted(set(global_uncertainty) | set(path.unresolved_reasons)))
    status = "best_found_unproven" if reasons else "fastest_proven"
    return ProfileResult(status, first.departure_seconds, path.arrival, elapsed,
                         path.transfers, _legs(path.connections),
                         path.transfer_rule_ids, reasons)


def build_profile(connections, transfer_rules, target_stop_ids, *,
                  first_board_start=FIRST_BOARD_START,
                  first_board_end=FIRST_BOARD_END, max_elapsed=MAX_ELAPSED,
                  source_uncertainty=(), first_board_stop_ids=None):
    """Return shared reverse-profile results keyed by candidate connection ID.

    Profiles contain only destination-reaching labels, so memory is bounded by
    the input connections rather than first-board-events × itineraries.
    """
    ordered = sorted(connections, key=lambda item: (
        -item.departure_seconds, -item.arrival_seconds, item.trip_id,
        item.from_stop_sequence, item.connection_id))
    rules = tuple(sorted(transfer_rules, key=lambda item: item.rule_id))
    rules_by_from = defaultdict(list)
    rules_by_from_trip = defaultdict(list)
    generic_rules = []
    global_uncertainty = set(source_uncertainty)
    for item in rules:
        rules_by_from[item.from_stop_id].append(item)
        if not item.from_stop_id and item.from_trip_id:
            rules_by_from_trip[item.from_trip_id].append(item)
        elif not item.from_stop_id:
            generic_rules.append(item)
        if item.applicability_status in {"unresolved_service", "unresolved_route_conflict"}:
            global_uncertainty.add("unresolved_transfer_selector")
        if item.transfer_type == 4 or item.applicability_status == "in_seat_candidate_unvalidated":
            global_uncertainty.add("in_seat_ambiguity")

    solved = {}
    by_stop = defaultdict(list)
    departures = defaultdict(list)
    next_by_trip = {}
    targets = frozenset(target_stop_ids)

    for item in ordered:
        options = []
        if item.to_stop_id in targets and item.to_drop_off_type == 0:
            options.append(_Path((item,), ()))

        next_item = next_by_trip.get((item.trip_id, item.to_stop_sequence))
        if (next_item is not None and next_item.from_stop_id == item.to_stop_id
                and next_item.departure_seconds >= item.arrival_seconds
                and next_item.connection_id in solved):
            suffix = solved[next_item.connection_id]
            options.append(_Path((item,) + suffix.connections,
                                 suffix.transfer_rule_ids,
                                 suffix.unresolved_reasons))

        candidate_stops = set()
        if item.to_drop_off_type == 0:
            candidate_stops.add(item.to_stop_id)
            candidate_stops.update(
                rule.to_stop_id for rule in rules_by_from.get(item.to_stop_id, ())
                if rule.to_stop_id)
        transition_rules = (tuple(rules_by_from.get(item.to_stop_id, ()))
                            + tuple(rules_by_from_trip.get(item.trip_id, ()))
                            + tuple(generic_rules))
        for stop_id in sorted(candidate_stops):
            times = departures.get(stop_id, ())
            start = bisect.bisect_left(times, item.arrival_seconds)
            for outgoing in by_stop.get(stop_id, ())[start:]:
                if outgoing.departure_seconds - item.departure_seconds > max_elapsed:
                    break
                if outgoing.from_pickup_type != 0 or outgoing.trip_id == item.trip_id:
                    continue
                allowed, rule_id, uncertainty = _transition(
                    item, outgoing, transition_rules)
                if not allowed:
                    continue
                suffix = solved[outgoing.connection_id]
                options.append(_Path(
                    (item,) + suffix.connections,
                    ((rule_id,) if rule_id is not None else ()) + suffix.transfer_rule_ids,
                    tuple(sorted(set(uncertainty) | set(suffix.unresolved_reasons)))))

        if options:
            solved[item.connection_id] = min(options, key=lambda path: path.key())
            # Reverse scan inserts decreasing times; maintain ascending profiles.
            position = bisect.bisect_left(departures[item.from_stop_id], item.departure_seconds)
            departures[item.from_stop_id].insert(position, item.departure_seconds)
            by_stop[item.from_stop_id].insert(position, item)
        next_by_trip[(item.trip_id, item.from_stop_sequence)] = item

    output = {}
    allowed_first_stops = (None if first_board_stop_ids is None
                           else frozenset(first_board_stop_ids))
    for item in sorted(connections, key=lambda value: value.connection_id):
        if not first_board_start <= item.departure_seconds <= first_board_end:
            continue
        if item.from_pickup_type != 0:
            continue
        if allowed_first_stops is not None and item.from_stop_id not in allowed_first_stops:
            continue
        path = solved.get(item.connection_id)
        if path is not None and path.arrival - item.departure_seconds > max_elapsed:
            path = None
        output[item.connection_id] = _result(item, path, global_uncertainty)
    return output


def _sha256(path):
    with pathlib.Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _readonly(path):
    return sqlite3.connect(pathlib.Path(path).resolve().as_uri() + "?mode=ro&immutable=1", uri=True)


def _checked(path, expected, label):
    actual = _sha256(path)
    if actual != expected:
        raise RouteProfileError(f"{label} SHA-256 mismatch")
    return pathlib.Path(path)


def _load_connections(path):
    database = _readonly(path)
    try:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RouteProfileError("connection SQLite integrity check failed")
        metadata = dict(database.execute("SELECT key,value FROM metadata"))
        if metadata.get("schema_id") != "steuerpendler.dated-ride-connections.v1":
            raise RouteProfileError("connection schema mismatch")
        query = """SELECT connection_id,trip_id,route_id,service_id,
            from_stop_sequence,to_stop_sequence,departure_seconds,arrival_seconds,
            from_stop_id,to_stop_id,from_pickup_type,to_drop_off_type
            FROM ride_connections ORDER BY departure_seconds DESC, connection_id"""
        return [Connection(*row) for row in database.execute(query)], metadata
    finally:
        database.close()


def _load_rules(path):
    database = _readonly(path)
    try:
        if database.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RouteProfileError("transfer-scope SQLite integrity check failed")
        metadata = dict(database.execute("SELECT key,value FROM metadata"))
        if metadata.get("schema_id") != "steuerpendler.dated-transfer-scope.v1":
            raise RouteProfileError("transfer-scope schema mismatch")
        query = """SELECT rule_id,from_stop_id,to_stop_id,from_route_id,to_route_id,
            from_trip_id,to_trip_id,transfer_type,min_transfer_time,service_id,
            selector_specificity,applicability_status FROM transfer_scope
            WHERE applicability_status IN ('potentially_applicable','unresolved_service',
                'unresolved_route_conflict','in_seat_candidate_unvalidated')
            ORDER BY rule_id"""
        return [TransferRule(*row) for row in database.execute(query)], metadata
    finally:
        database.close()


def _target_children(path, bfs):
    payload = json.loads(path.read_text(encoding="utf-8"))
    matches = [item for item in payload.get("workplaces", []) if item.get("bfs") == bfs]
    if len(matches) != 1:
        raise RouteProfileError("target registry lacks unique requested BFS")
    children = sorted({child for candidate in matches[0].get("targetCandidates", [])
                       for child in candidate.get("childStopIds", [])})
    if not children:
        raise RouteProfileError("target child group is empty")
    return children, payload.get("status")


def _origin_events(path, bfs):
    database = _readonly(path)
    try:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RouteProfileError("board-stop SQLite integrity check failed")
        metadata = dict(database.execute("SELECT key,value FROM metadata"))
        rows = database.execute("""SELECT stop_id FROM board_stop_gemeinde
            WHERE bfs=? AND evidence_status='assigned' ORDER BY stop_id""", (bfs,)).fetchall()
        return {row[0] for row in rows}, metadata
    finally:
        database.close()


def _json_result(result):
    return dataclasses.asdict(result)


def run_pilot(connections_path, transfer_scope_path, board_stop_path,
              target_registry_path, output_path, *, origin_bfs=4210,
              destination_bfs=4001, expected_transfer_scope_sha256=None):
    if (not isinstance(expected_transfer_scope_sha256, str)
            or len(expected_transfer_scope_sha256) != 64
            or any(char not in "0123456789abcdef" for char in expected_transfer_scope_sha256)):
        raise RouteProfileError("expected transfer-scope SHA-256 is required")
    started = time.monotonic()
    _checked(connections_path, CONNECTION_SHA256, "connections")
    _checked(board_stop_path, BOARD_STOP_SHA256, "board-stop evidence")
    _checked(target_registry_path, TARGET_REGISTRY_SHA256, "target registry")
    transfer_sha = _sha256(transfer_scope_path)
    if transfer_sha != expected_transfer_scope_sha256:
        raise RouteProfileError("transfer-scope SHA-256 mismatch")
    connections, connection_metadata = _load_connections(connections_path)
    rules, transfer_metadata = _load_rules(transfer_scope_path)
    targets, target_status = _target_children(pathlib.Path(target_registry_path), destination_bfs)
    origin_stops, board_metadata = _origin_events(board_stop_path, origin_bfs)
    if not origin_stops:
        raise RouteProfileError("origin BFS has no assigned board stops")
    # This bounded pilot deliberately omits validated parent/120-second fallback
    # expansion and cannot prove absence of a faster unsearched alternative.
    uncertainties = ["pilot_transfer_search_incomplete", "provisional_target_group"]
    if int(connection_metadata.get("count.quarantined_frequency_pairs", "0")):
        uncertainties.append("frequency_source_quarantined")
    if int(connection_metadata.get("count.quarantined_non_exact_pairs", "0")):
        uncertainties.append("non_exact_source_quarantined")
    selected = build_profile(
        connections, rules, targets, source_uncertainty=uncertainties,
        first_board_stop_ids=origin_stops)
    witness = [result for result in selected.values()
               if result.first_board_seconds == 24_420
               and result.arrival_seconds == 25_500
               and result.elapsed_seconds == 1_080]
    if not witness:
        raise RouteProfileError("Staufen 06:47 to 07:05 regression not evidenced")
    statuses = defaultdict(int)
    for result in selected.values():
        statuses[result.status] += 1
    direct = sum(1 for result in selected.values()
                 if result.arrival_seconds is not None and result.transfer_count == 0)
    payload = {
        "schema": "steuerpendler.aarau-route-profile-pilot.v1",
        "status": "DIAGNOSTIC_NOT_CANONICAL",
        "targetChildGroupStatus": target_status or "PROVISIONAL",
        "originBfs": origin_bfs,
        "destinationBfs": destination_bfs,
        "sourceSha256": {
            "connections": CONNECTION_SHA256,
            "transferScope": transfer_sha,
            "boardStopGemeinde": BOARD_STOP_SHA256,
            "targetRegistry": TARGET_REGISTRY_SHA256,
        },
        "counts": {
            "rideConnectionsScanned": len(connections),
            "transferRulesLoaded": len(rules),
            "originAssignedStops": len(origin_stops),
            "activeCandidateEvents": len(selected),
            "authenticDirectPositiveEvents": direct,
            "statuses": dict(sorted(statuses.items())),
        },
        "staufenRegression": _json_result(witness[0]),
        "samplePositiveResults": [_json_result(item) for item in
                                  sorted((value for value in selected.values()
                                          if value.arrival_seconds is not None),
                                         key=lambda value: (value.first_board_seconds,
                                                            value.arrival_seconds))[:20]],
        "unresolved": sorted({reason for item in selected.values()
                              for reason in item.unresolved_reasons}),
        "wallSeconds": time.monotonic() - started,
        "peakRssKiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "limitations": [
            "One provisional destination group only; not a national or canonical route file.",
            "Zero external residence-to-entrance access is unmeasured; no entrance-to-platform walk is added.",
            "Frequency/non-exact and unresolved transfer evidence prevents negative or fastest claims where relevant.",
        ],
        "sourceServiceDate": transfer_metadata.get("service_date"),
        "boardEvidenceServiceDate": board_metadata.get("service_date"),
    }
    output = pathlib.Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connections", required=True)
    parser.add_argument("--transfer-scope", required=True)
    parser.add_argument("--board-stops", required=True)
    parser.add_argument("--target-registry", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-transfer-scope-sha256", required=True)
    parser.add_argument("--origin-bfs", type=int, default=4210)
    parser.add_argument("--destination-bfs", type=int, default=4001)
    args = parser.parse_args()
    report = run_pilot(
        args.connections, args.transfer_scope, args.board_stops,
        args.target_registry, args.output, origin_bfs=args.origin_bfs,
        destination_bfs=args.destination_bfs,
        expected_transfer_scope_sha256=args.expected_transfer_scope_sha256)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
