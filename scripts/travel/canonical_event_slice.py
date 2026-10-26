#!/usr/bin/env python3
"""Bounded one-destination first-board-event slice exporter.

The implementation reuses the production dated reverse route profile. It emits
positive observations and reason-coded unknowns; it never upgrades incomplete
source evidence to fastest or unreachable proof.
"""
from __future__ import annotations

import argparse
import dataclasses
import gzip
import hashlib
import json
import os
import pathlib
import resource
import tempfile
import time
from collections import Counter
from typing import Iterable

import dated_route_profile as route_profile
import dated_route_export as route_export

FIRST_BOARD_START = 23_400
FIRST_BOARD_END = 30_600
MAX_ELAPSED = 1_800
DESTINATION_BFS = 4001

CONNECTION_SHA256 = route_profile.CONNECTION_SHA256
BOARD_STOP_SHA256 = route_profile.BOARD_STOP_SHA256
TARGET_REGISTRY_SHA256 = route_profile.TARGET_REGISTRY_SHA256


class EventSliceError(ValueError):
    """Pinned source evidence cannot safely produce the bounded slice."""


def _validate_transfer_pin(expected: str) -> None:
    if expected != route_export.TRANSFER_SCOPE_SHA256:
        raise EventSliceError('transfer scope pin differs from the release authority')


def _validate_service_date(metadata: dict[str, str], label: str) -> None:
    if metadata.get('service_date') != route_export.SERVICE_DATE:
        raise EventSliceError(f'{label} service date differs from the pinned reference day')


def _source_coverage(metadata: dict[str, str], assigned_count: int) -> dict[str, int]:
    raw = metadata.get('count.candidate_first_board_events', '')
    if not raw.isdecimal():
        raise EventSliceError('source first-board event coverage count missing')
    total = int(raw)
    if not 0 <= assigned_count <= total:
        raise EventSliceError('assigned-event coverage exceeds the source count')
    return {'sourceCandidateFirstBoardEvents': total,
            'excludedFirstBoardEvents': total-assigned_count}


def _result(value: route_profile.ProfileResult) -> dict:
    payload = {
        "status": value.status,
        "arrivalSeconds": value.arrival_seconds,
        "elapsedSeconds": value.elapsed_seconds,
        "transferCount": value.transfer_count,
        "legs": [dataclasses.asdict(leg) for leg in value.legs],
        "transferRuleIds": list(value.transfer_rule_ids),
        "unresolvedReasons": list(value.unresolved_reasons),
    }
    return payload


def evaluate_events(
    connections: Iterable[route_profile.Connection],
    transfer_rules: Iterable[route_profile.TransferRule],
    target_stop_ids: Iterable[str],
    board_stop_bfs: dict[str, int],
    *,
    source_uncertainty: Iterable[str],
) -> list[dict]:
    """Evaluate all assigned first-board events for one destination.

    The all-route and direct-only profiles are computed independently. Source
    uncertainty is mandatory because this slice is not a completeness proof.
    """
    rides = tuple(connections)
    rules = tuple(transfer_rules)
    uncertainty = tuple(sorted(set(source_uncertainty)))
    if not uncertainty:
        raise EventSliceError("source uncertainty inventory must be nonempty")
    allowed_stops = frozenset(board_stop_bfs)
    arguments = {
        "connections": rides,
        "target_stop_ids": frozenset(target_stop_ids),
        "first_board_start": FIRST_BOARD_START,
        "first_board_end": FIRST_BOARD_END,
        "max_elapsed": MAX_ELAPSED,
        "source_uncertainty": uncertainty,
        "first_board_stop_ids": allowed_stops,
    }
    all_routes = route_profile.build_profile(transfer_rules=rules, **arguments)
    direct_only = route_profile.build_profile(transfer_rules=(), **arguments)
    by_id = {ride.connection_id: ride for ride in rides}
    records = []
    for connection_id in sorted(all_routes, key=lambda item: (
            by_id[item].departure_seconds, by_id[item].from_stop_id,
            by_id[item].trip_id, by_id[item].from_stop_sequence, item)):
        ride = by_id[connection_id]
        records.append({
            "event": {
                "connectionId": connection_id,
                "tripInstanceId": ride.trip_id,
                "stopId": ride.from_stop_id,
                "stopSequence": ride.from_stop_sequence,
                "boardSeconds": ride.departure_seconds,
                "originBfs": board_stop_bfs[ride.from_stop_id],
            },
            "allRoutes": _result(all_routes[connection_id]),
            "directOnly": _result(direct_only[connection_id]),
        })
    if set(all_routes) != set(direct_only):
        raise EventSliceError("all-route and direct-only event denominators differ")
    return records


def _sha256(path: pathlib.Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _checked(path: pathlib.Path, expected: str, label: str) -> pathlib.Path:
    actual = _sha256(path)
    if actual != expected:
        raise EventSliceError(f"{label} SHA-256 mismatch: {actual}")
    return path


def _board_assignments(path: pathlib.Path) -> tuple[dict[str, int], dict[str, str]]:
    database = route_profile._readonly(path)
    try:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise EventSliceError("board-stop SQLite integrity check failed")
        metadata = dict(database.execute("SELECT key,value FROM metadata"))
        if metadata.get('schema_id') != 'steuerpendler.dated-board-stop-gemeinde':
            raise EventSliceError('board-stop schema mismatch')
        rows = database.execute("""SELECT stop_id,bfs FROM board_stop_gemeinde
            WHERE evidence_status='assigned' ORDER BY stop_id""").fetchall()
        return {stop_id: bfs for stop_id, bfs in rows}, metadata
    finally:
        database.close()


def _uncertainty_inventory(connection_metadata, transfer_metadata, board_metadata,
                           target_status) -> dict[str, int | str]:
    return {
        "frequency_source_quarantined": int(
            connection_metadata.get("count.quarantined_frequency_pairs", "0")),
        "in_seat_continuations_unvalidated": int(
            transfer_metadata.get("count.status.in_seat_candidate_unvalidated", "0")),
        "board_stops_boundary_quarantined": int(
            board_metadata.get("count.boundary_quarantined", "0")),
        "board_stops_unassigned": int(board_metadata.get("count.unassigned", "0")),
        "target_group_status": target_status or "PROVISIONAL",
    }


def _uncertainty_reasons(inventory: dict[str, int | str]) -> tuple[str, ...]:
    reasons = {
        "source_scale_slice_not_global_completeness_proof",
        "residential_access_zero_unmeasured",
        "parent_station_fallback_not_searched",
    }
    if inventory["frequency_source_quarantined"]:
        reasons.add("frequency_source_quarantined")
    if inventory["in_seat_continuations_unvalidated"]:
        reasons.add("in_seat_ambiguity")
    if inventory["board_stops_boundary_quarantined"]:
        reasons.add("boundary_board_stops_quarantined")
    if inventory["board_stops_unassigned"]:
        reasons.add("unassigned_board_stops")
    if inventory["target_group_status"] != "VERIFIED":
        reasons.add("provisional_target_group")
    return tuple(sorted(reasons))


def export_slice(connections_path, transfer_scope_path, board_stop_path,
                 target_registry_path, output_path, *, expected_transfer_scope_sha256):
    """Write a deterministic, atomic gzip NDJSON Aarau slice."""
    started = time.monotonic()
    _validate_transfer_pin(expected_transfer_scope_sha256)
    connections_path = _checked(pathlib.Path(connections_path), CONNECTION_SHA256, "connections")
    board_stop_path = _checked(pathlib.Path(board_stop_path), BOARD_STOP_SHA256, "board-stop evidence")
    target_registry_path = _checked(
        pathlib.Path(target_registry_path), TARGET_REGISTRY_SHA256, "target registry")
    transfer_scope_path = _checked(
        pathlib.Path(transfer_scope_path), expected_transfer_scope_sha256, "transfer scope")

    connections, connection_metadata = route_profile._load_connections(connections_path)
    rules, transfer_metadata = route_profile._load_rules(transfer_scope_path)
    targets, target_status = route_profile._target_children(target_registry_path, DESTINATION_BFS)
    assignments, board_metadata = _board_assignments(board_stop_path)
    for label, metadata in (("connections", connection_metadata),
                            ("transfer scope", transfer_metadata),
                            ("board stops", board_metadata)):
        _validate_service_date(metadata, label)
    inventory = _uncertainty_inventory(
        connection_metadata, transfer_metadata, board_metadata, target_status)
    reasons = _uncertainty_reasons(inventory)
    records = evaluate_events(
        connections, rules, targets, assignments, source_uncertainty=reasons)

    expected = sum(1 for ride in connections
                   if FIRST_BOARD_START <= ride.departure_seconds <= FIRST_BOARD_END
                   and ride.from_pickup_type == 0 and ride.from_stop_id in assignments)
    if len(records) != expected:
        raise EventSliceError(f"event coverage mismatch: emitted {len(records)}, expected {expected}")
    coverage = _source_coverage(connection_metadata, expected)

    statuses = {mode: Counter(record[mode]["status"] for record in records)
                for mode in ("allRoutes", "directOnly")}
    positives = {mode: sum(value in {"best_found_unproven", "fastest_proven"}
                           for value in statuses[mode].elements())
                 for mode in statuses}
    manifest = {
        "kind": "manifest",
        "schema": "steuerpendler.canonical-event-slice.v1",
        "destinationBfs": DESTINATION_BFS,
        "serviceDate": connection_metadata.get("service_date"),
        "timezone": "Europe/Zurich",
        "firstBoardWindowSecondsInclusive": [FIRST_BOARD_START, FIRST_BOARD_END],
        "maxElapsedSecondsInclusive": MAX_ELAPSED,
        "sourceSha256": {
            "connections": CONNECTION_SHA256,
            "transferScope": expected_transfer_scope_sha256,
            "boardStopGemeinde": BOARD_STOP_SHA256,
            "targetRegistry": TARGET_REGISTRY_SHA256,
        },
        "denominator": expected,
        "sourceCoverage": coverage,
        "uncertaintyInventory": inventory,
        "unresolvedReasons": list(reasons),
        "claims": "BOUNDED_AARAU_POSITIVES_AND_UNKNOWNS_NOT_GLOBAL_PROOF",
    }
    summary = {
        "kind": "summary",
        "denominator": expected,
        "emitted": len(records),
        "positives": positives,
        "unknowns": {mode: statuses[mode].get("unknown", 0) for mode in statuses},
        "statuses": {mode: dict(sorted(statuses[mode].items())) for mode in statuses},
    }

    output = pathlib.Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
                for payload in (manifest, *records, summary):
                    compressed.write((json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                                                 sort_keys=True) + "\n").encode("utf-8"))
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(temporary_name, output)
    except BaseException:
        pathlib.Path(temporary_name).unlink(missing_ok=True)
        raise
    run_report = {
        "output": str(output),
        "outputBytes": output.stat().st_size,
        "outputSha256": _sha256(output),
        "wallSeconds": time.monotonic() - started,
        "peakRssKiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    report_path = output.with_suffix(output.suffix + ".run.json")
    report_path.write_text(json.dumps(run_report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    return manifest, summary, run_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connections", required=True)
    parser.add_argument("--transfer-scope", required=True)
    parser.add_argument("--board-stops", required=True)
    parser.add_argument("--target-registry", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-transfer-scope-sha256", required=True)
    args = parser.parse_args()
    manifest, summary, run_report = export_slice(
        args.connections, args.transfer_scope, args.board_stops, args.target_registry,
        args.output, expected_transfer_scope_sha256=args.expected_transfer_scope_sha256)
    print(json.dumps({"manifest": manifest, "summary": summary, "run": run_report},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
