#!/usr/bin/env python3
"""Build a deterministic all-19 observed-positive dated route export.

The export records provisional positive evidence and unknown states.  It does not
claim complete reachability, a proven fastest route, or independent approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sqlite3
import tempfile

import dated_route_profile as route_profile

SERVICE_DATE = "2026-10-27"
SCHEMA = "steuerpendler.dated-observed-route-export.v1"
CONNECTION_SHA256 = route_profile.CONNECTION_SHA256
BOARD_STOP_SHA256 = route_profile.BOARD_STOP_SHA256
TARGET_REGISTRY_SHA256 = route_profile.TARGET_REGISTRY_SHA256
TRANSFER_SCOPE_SHA256 = "6e2d6869ac4b731e96069b6ce35a20253aa704c92512d7b820bc1d6303e0819b"
SOURCE_KEYS = ("connections", "transferScope", "boardStopGemeinde",
               "targetRegistry", "gemeinden")


class RouteExportError(ValueError):
    """Frozen evidence cannot safely support an export."""


def _valid_sha(value):
    return (isinstance(value, str) and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


def _positive_row(result, origin_stop):
    return {
        "status": "best_found_unproven",
        "firstBoardSeconds": result.first_board_seconds,
        "arrivalSeconds": result.arrival_seconds,
        "elapsedSeconds": result.elapsed_seconds,
        "transferCount": result.transfer_count,
        "firstBoardStopId": origin_stop,
        "arrivalStopId": result.legs[-1].alight_stop_id,
        "sourceConnectionId": result.legs[0].connection_ids[0],
        "legs": [{
            "tripId": leg.trip_id,
            "routeId": leg.route_id,
            "serviceId": leg.service_id,
            "boardStopId": leg.board_stop_id,
            "alightStopId": leg.alight_stop_id,
            "boardSeconds": leg.board_seconds,
            "alightSeconds": leg.alight_seconds,
            "connectionIds": list(leg.connection_ids),
        } for leg in result.legs],
        "transferRuleIds": list(result.transfer_rule_ids),
        "unresolvedReasons": sorted(set(result.unresolved_reasons) |
                                    {"optimality_not_proven"}),
    }


def _choice_key(item):
    connection, result = item
    stable = tuple((leg.trip_id, leg.board_stop_id, leg.alight_stop_id,
                    leg.connection_ids) for leg in result.legs)
    return (result.elapsed_seconds, result.arrival_seconds, result.transfer_count,
            stable, connection.connection_id)


def _best_by_bfs(connections, results, assignments):
    candidates = {}
    by_id = {item.connection_id: item for item in connections}
    for connection_id, result in results.items():
        if result.arrival_seconds is None:
            continue
        connection = by_id[connection_id]
        bfs = assignments.get(connection.from_stop_id)
        if bfs is None:
            continue
        pair = (connection, result)
        previous = candidates.get(bfs)
        if previous is None or _choice_key(pair) < _choice_key(previous):
            candidates[bfs] = pair
    return {bfs: _positive_row(result, connection.from_stop_id)
            for bfs, (connection, result) in sorted(candidates.items(),
                                                    key=lambda item: int(item[0]))}


def build_export(connections, transfer_rules, target_groups, board_assignments,
                 municipality_ids, *, service_date, source_sha256):
    """Build a self-contained payload from already validated synthetic/source objects."""
    if service_date != SERVICE_DATE:
        raise RouteExportError("service date mismatch")
    if not isinstance(target_groups, dict) or len(target_groups) != 19:
        raise RouteExportError("exactly 19 destination groups are required")
    if any(not str(key).isdigit() or not isinstance(stops, (list, tuple, set)) or not stops
           for key, stops in target_groups.items()):
        raise RouteExportError("invalid destination group")
    municipalities = [str(value) for value in municipality_ids]
    if (not municipalities or len(municipalities) != len(set(municipalities))
            or any(not value.isdigit() for value in municipalities)):
        raise RouteExportError("invalid Gemeinde authority")
    if set(source_sha256) != set(SOURCE_KEYS) or any(
            not _valid_sha(source_sha256[key]) for key in SOURCE_KEYS):
        raise RouteExportError("invalid source SHA lineage")
    assignments = {str(stop): str(bfs) for stop, bfs in board_assignments.items()
                   if str(bfs) in set(municipalities)}
    municipality_order = sorted(municipalities, key=int)
    destinations = {}
    uncertainties = ("provisional_target_group", "optimality_not_proven",
                     "unmeasured_zero_external_access")
    for destination, target_stops in sorted(target_groups.items(), key=lambda item: int(item[0])):
        all_results = route_profile.build_profile(
            connections, transfer_rules, sorted(set(target_stops)),
            source_uncertainty=uncertainties,
            first_board_stop_ids=assignments)
        positives = _best_by_bfs(connections, all_results, assignments)
        del all_results
        direct_results = route_profile.build_profile(
            connections, (), sorted(set(target_stops)),
            source_uncertainty=uncertainties,
            first_board_stop_ids=assignments)
        direct = _best_by_bfs(connections, direct_results, assignments)
        del direct_results
        statuses = {}
        for bfs in municipality_order:
            statuses[bfs] = positives.get(bfs, {
                "status": "unknown",
                "unresolvedReasons": ["no_evidenced_route_from_assigned_stop"],
            })
        destinations[str(destination)] = {
            "targetChildStopIds": sorted(set(target_stops)),
            "statuses": statuses,
            "directOnly": direct,
            "unresolvedReasonClasses": sorted({reason
                for row in statuses.values()
                for reason in row.get("unresolvedReasons", row.get("unresolved_reasons", []))}),
        }
    return {
        "schema": SCHEMA,
        "schemaVersion": 1,
        "serviceDate": SERVICE_DATE,
        "defaultAllRoutes": True,
        "claims": "OBSERVED_POSITIVE_PROVISIONAL_UNKNOWN_ABSENCE",
        "externalAccessSeconds": 0,
        "externalAccessMeasurement": "unmeasured",
        "sourceSha256": {key: source_sha256[key] for key in SOURCE_KEYS},
        "municipalityCount": len(municipality_order),
        "destinationCount": 19,
        "destinations": destinations,
    }


def encode_export(payload):
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _snapshot(path, expected_sha, directory, label):
    target = pathlib.Path(directory) / label
    digest = hashlib.sha256()
    try:
        with pathlib.Path(path).open("rb") as source, target.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        raise RouteExportError(f"cannot snapshot {label}: {exc}") from exc
    if digest.hexdigest() != expected_sha:
        raise RouteExportError(f"{label} SHA-256 mismatch")
    return target


def _metadata_date(metadata, label):
    if metadata.get("schema_version") != "1":
        raise RouteExportError(f"{label} schema mismatch")
    if metadata.get("service_date") != SERVICE_DATE:
        raise RouteExportError(f"{label} service date mismatch")


def _load_board_assignments(path):
    database = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RouteExportError("board-stop integrity check failed")
        metadata = dict(database.execute("SELECT key,value FROM metadata"))
        if metadata.get("schema_id") != "steuerpendler.dated-board-stop-gemeinde":
            raise RouteExportError("board-stop schema mismatch")
        _metadata_date(metadata, "board-stop")
        rows = database.execute("SELECT stop_id,bfs FROM board_stop_gemeinde "
                                "WHERE evidence_status='assigned' ORDER BY stop_id")
        assignments = {}
        for stop, bfs in rows:
            if stop in assignments:
                raise RouteExportError("duplicate assigned board stop")
            assignments[stop] = str(bfs)
        return assignments
    except sqlite3.Error as exc:
        raise RouteExportError(f"invalid board-stop SQLite: {exc}") from exc
    finally:
        database.close()


def _load_json(path, label):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RouteExportError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RouteExportError(f"invalid {label} JSON root")
    return value


def _load_targets(path):
    payload = _load_json(path, "target registry")
    groups = {}
    for item in payload.get("workplaces", []):
        bfs = str(item.get("bfs", ""))
        children = sorted({child for candidate in item.get("targetCandidates", [])
                           for child in candidate.get("childStopIds", [])})
        if bfs in groups or not bfs.isdigit() or not children:
            raise RouteExportError("invalid target registry group")
        groups[bfs] = children
    if len(groups) != 19:
        raise RouteExportError("target registry must contain 19 destination groups")
    return groups


def run_export(connections_path, transfer_scope_path, board_stop_path,
               target_registry_path, gemeinden_path, output_path, *,
               expected_gemeinden_sha256):
    if not _valid_sha(expected_gemeinden_sha256):
        raise RouteExportError("expected Gemeinden SHA-256 is required")
    pins = {"connections": CONNECTION_SHA256, "transferScope": TRANSFER_SCOPE_SHA256,
            "boardStopGemeinde": BOARD_STOP_SHA256,
            "targetRegistry": TARGET_REGISTRY_SHA256,
            "gemeinden": expected_gemeinden_sha256}
    output = pathlib.Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dated-route-export-", dir=output.parent) as tmp:
        paths = {
            "connections": _snapshot(connections_path, pins["connections"], tmp, "connections.sqlite"),
            "transferScope": _snapshot(transfer_scope_path, pins["transferScope"], tmp, "transfers.sqlite"),
            "boardStopGemeinde": _snapshot(board_stop_path, pins["boardStopGemeinde"], tmp, "board.sqlite"),
            "targetRegistry": _snapshot(target_registry_path, pins["targetRegistry"], tmp, "targets.json"),
            "gemeinden": _snapshot(gemeinden_path, pins["gemeinden"], tmp, "gemeinden.json"),
        }
        connections, connection_metadata = route_profile._load_connections(paths["connections"])
        rules, transfer_metadata = route_profile._load_rules(paths["transferScope"])
        _metadata_date(connection_metadata, "connections")
        _metadata_date(transfer_metadata, "transfer scope")
        if len(connections) != 454_393:
            raise RouteExportError("ride connection count mismatch")
        groups = _load_targets(paths["targetRegistry"])
        assignments = _load_board_assignments(paths["boardStopGemeinde"])
        authority_payload = _load_json(paths["gemeinden"], "Gemeinden")
        if authority_payload.get("meta", {}).get("year") != 2026:
            raise RouteExportError("Gemeinde authority year mismatch")
        authority = authority_payload.get("gemeinden")
        if not isinstance(authority, dict) or len(authority) != 2110:
            raise RouteExportError("Gemeinde authority must contain exactly 2110 IDs")
        payload = build_export(connections, rules, groups, assignments, authority,
                               service_date=SERVICE_DATE, source_sha256=pins)
        temporary = pathlib.Path(tmp) / "output.json"
        temporary.write_bytes(encode_export(payload))
        os.replace(temporary, output)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connections", required=True)
    parser.add_argument("--transfer-scope", required=True)
    parser.add_argument("--board-stops", required=True)
    parser.add_argument("--target-registry", required=True)
    parser.add_argument("--gemeinden", required=True)
    parser.add_argument("--expected-gemeinden-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = run_export(args.connections, args.transfer_scope, args.board_stops,
                         args.target_registry, args.gemeinden, args.output,
                         expected_gemeinden_sha256=args.expected_gemeinden_sha256)
    print(json.dumps({"output": args.output,
                      "destinations": payload["destinationCount"],
                      "municipalities": payload["municipalityCount"]}, sort_keys=True))


if __name__ == "__main__":
    main()
