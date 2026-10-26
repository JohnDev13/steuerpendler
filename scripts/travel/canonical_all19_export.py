#!/usr/bin/env python3
"""Sequential bounded exporter for the provisional 19-destination event matrix."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import pathlib
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
import canonical_event_slice as event_slice
import dated_route_export as route_export

DESTINATION_COUNT = 19
CHILD_TIMEOUT_SECONDS = 600
CHILD_VIRTUAL_LIMIT_BYTES = 2 * 1024**3
CHILD_RSS_LIMIT_KIB = 1536 * 1024


def _bound_child_address_space() -> None:
    resource.setrlimit(resource.RLIMIT_AS,
                       (CHILD_VIRTUAL_LIMIT_BYTES, CHILD_VIRTUAL_LIMIT_BYTES))


def _validate_child_memory(report: dict, bfs: int) -> None:
    peak = report.get('peakRssKiB')
    if type(peak) is not int or peak < 0 or peak > CHILD_RSS_LIMIT_KIB:
        raise All19ExportError(f'destination {bfs} memory budget exceeded or unmeasured')
COPY_CHUNK_BYTES = 1024 * 1024
MAX_INPUT_BYTES = {
    "connections": 8 * 1024**3,
    "transferScope": 2 * 1024**3,
    "boardStopGemeinde": 2 * 1024**3,
    "targetRegistry": 64 * 1024**2,
}
CONNECTION_SHA256 = event_slice.CONNECTION_SHA256
BOARD_STOP_SHA256 = event_slice.BOARD_STOP_SHA256
TARGET_REGISTRY_SHA256 = event_slice.TARGET_REGISTRY_SHA256
ALLOWED_STATUSES = frozenset({"best_found_unproven", "unknown"})
EVENT_SLICE_GENERATOR_VERSION = "1.2"


class All19ExportError(ValueError):
    """Pinned evidence cannot safely produce the all-destination matrix."""


def _sha256(path: pathlib.Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


EVENT_SLICE_GENERATOR_SHA256 = _sha256(pathlib.Path(event_slice.__file__))


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _atomic_json(path: pathlib.Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        pathlib.Path(temporary_name).unlink(missing_ok=True)
        raise


def _backup(path: pathlib.Path) -> pathlib.Path | None:
    if not path.exists():
        return None
    descriptor, backup_name = tempfile.mkstemp(prefix=f".{path.name}.backup.", dir=path.parent)
    os.close(descriptor)
    backup = pathlib.Path(backup_name)
    backup.unlink()
    os.replace(path, backup)
    return backup


def _publish_pair(output_temporary: pathlib.Path, report_temporary: pathlib.Path,
                  output: pathlib.Path, report: pathlib.Path) -> None:
    output_backup = report_backup = None
    output_published = report_published = False
    published = False
    try:
        output_backup = _backup(output)
        report_backup = _backup(report)
        os.replace(output_temporary, output)
        output_published = True
        os.replace(report_temporary, report)
        report_published = True
        directory_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        published = True
    except BaseException:
        if report_published:
            report.unlink(missing_ok=True)
        if output_published:
            output.unlink(missing_ok=True)
        if report_backup is not None:
            os.replace(report_backup, report)
            report_backup = None
        if output_backup is not None:
            os.replace(output_backup, output)
            output_backup = None
        raise
    finally:
        output_temporary.unlink(missing_ok=True)
        report_temporary.unlink(missing_ok=True)
        if published and output_backup is not None:
            output_backup.unlink(missing_ok=True)
        if published and report_backup is not None:
            report_backup.unlink(missing_ok=True)


def load_destination_registry(path: pathlib.Path) -> list[dict]:
    """Return the exact sorted destination registry, rejecting ambiguity."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise All19ExportError(f"target registry is unreadable: {error}") from error
    workplaces = payload.get("workplaces")
    if not isinstance(workplaces, list) or len(workplaces) != DESTINATION_COUNT:
        raise All19ExportError(
            f"target registry must contain exactly {DESTINATION_COUNT} destinations")
    groups = []
    seen = set()
    for item in workplaces:
        if not isinstance(item, dict):
            raise All19ExportError("target registry destination is malformed")
        bfs = item.get("bfs")
        if not isinstance(bfs, int) or isinstance(bfs, bool) or bfs <= 0 or bfs in seen:
            raise All19ExportError("target registry requires unique positive integer BFS values")
        seen.add(bfs)
        candidates = item.get("targetCandidates")
        if not isinstance(candidates, list):
            raise All19ExportError(f"destination {bfs} target candidates are malformed")
        raw_children = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise All19ExportError(f"destination {bfs} target candidate is malformed")
            children = candidate.get("childStopIds")
            if not isinstance(children, list):
                raise All19ExportError(f"destination {bfs} child stop inventory is malformed")
            raw_children.extend(children)
        if (not raw_children or any(not isinstance(child, str) or not child
                                    for child in raw_children)):
            raise All19ExportError(f"destination {bfs} child stop inventory is malformed")
        groups.append({"destinationBfs": bfs,
                       "destinationChildStopIds": sorted(set(raw_children))})
    return sorted(groups, key=lambda group: group["destinationBfs"])


def _copy_checked(source: pathlib.Path, destination: pathlib.Path, *,
                  expected_sha256: str, max_bytes: int, label: str) -> None:
    """Copy one pinned input with a fixed memory buffer and byte ceiling."""
    digest = hashlib.sha256()
    total = 0
    try:
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            while chunk := incoming.read(COPY_CHUNK_BYTES):
                total += len(chunk)
                if total > max_bytes:
                    raise All19ExportError(f"{label} exceeds the staged-copy byte limit")
                digest.update(chunk)
                outgoing.write(chunk)
            outgoing.flush()
            os.fsync(outgoing.fileno())
    except All19ExportError:
        destination.unlink(missing_ok=True)
        raise
    except OSError as error:
        destination.unlink(missing_ok=True)
        raise All19ExportError(f"{label} staged copy failed: {error}") from error
    actual = digest.hexdigest()
    if actual != expected_sha256:
        destination.unlink(missing_ok=True)
        raise All19ExportError(f"{label} SHA-256 mismatch: {actual}")
    destination.chmod(0o400)


def _read_payload(stream, label: str) -> dict | None:
    try:
        line = stream.readline()
    except (OSError, EOFError) as error:
        raise All19ExportError(f"{label} gzip stream is corrupt: {error}") from error
    if not line:
        return None
    try:
        payload = json.loads(line)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise All19ExportError(f"{label} contains malformed NDJSON: {error}") from error
    if not isinstance(payload, dict):
        raise All19ExportError(f"{label} contains a non-object record")
    return payload


def _identity(event: object) -> dict:
    if not isinstance(event, dict):
        raise All19ExportError("event identity is missing")
    keys = ("connectionId", "tripInstanceId", "stopId", "stopSequence",
            "boardSeconds", "originBfs")
    if set(event) != set(keys):
        raise All19ExportError("event identity fields are malformed")
    if (not isinstance(event["connectionId"], int)
            or isinstance(event["connectionId"], bool)
            or event["connectionId"] <= 0
            or not isinstance(event["tripInstanceId"], str)
            or not event["tripInstanceId"]
            or not isinstance(event["stopId"], str)
            or not event["stopId"]
            or not isinstance(event["stopSequence"], int)
            or isinstance(event["stopSequence"], bool)
            or event["stopSequence"] < 0
            or not isinstance(event["boardSeconds"], int)
            or isinstance(event["boardSeconds"], bool)
            or not isinstance(event["originBfs"], int)
            or isinstance(event["originBfs"], bool)
            or event["originBfs"] <= 0):
        raise All19ExportError("event identity values are malformed")
    return event


def _validate_result(value: object, event: dict, label: str) -> str:
    if not isinstance(value, dict):
        raise All19ExportError(f"{label} result is malformed")
    expected_keys = {"status", "arrivalSeconds", "elapsedSeconds", "transferCount",
                     "legs", "transferRuleIds", "unresolvedReasons"}
    if set(value) != expected_keys:
        raise All19ExportError(f"{label} result fields are malformed")
    status = value.get("status")
    if status not in ALLOWED_STATUSES:
        raise All19ExportError(f"unexpected {label} status: {status}")
    reasons = value.get("unresolvedReasons")
    if (not isinstance(reasons, list) or not reasons
            or any(not isinstance(reason, str) or not reason for reason in reasons)):
        raise All19ExportError(f"{label} uncertainty reasons are malformed")
    legs = value.get("legs")
    rules = value.get("transferRuleIds")
    if (not isinstance(legs, list) or not isinstance(rules, list)
            or any(not isinstance(rule, int) or isinstance(rule, bool) or rule <= 0
                   for rule in rules)):
        raise All19ExportError(f"{label} path inventory is malformed")
    if status == "unknown":
        if (value.get("arrivalSeconds") is not None
                or value.get("elapsedSeconds") is not None
                or value.get("transferCount") is not None
                or legs or rules):
            raise All19ExportError(f"{label} unknown result contains a positive path")
    else:
        arrival = value.get("arrivalSeconds")
        elapsed = value.get("elapsedSeconds")
        transfers = value.get("transferCount")
        if (not isinstance(arrival, int) or isinstance(arrival, bool)
                or not isinstance(elapsed, int) or isinstance(elapsed, bool)
                or not 0 <= elapsed <= event_slice.MAX_ELAPSED
                or not isinstance(transfers, int) or isinstance(transfers, bool)
                or transfers < 0 or not legs
                or arrival - event["boardSeconds"] != elapsed
                or transfers != len(legs) - 1):
            raise All19ExportError(f"{label} positive result is malformed")
        leg_keys = {"trip_id", "route_id", "service_id", "board_stop_id",
                    "alight_stop_id", "board_seconds", "alight_seconds",
                    "connection_ids"}
        for leg in legs:
            if (not isinstance(leg, dict) or set(leg) != leg_keys
                    or any(not isinstance(leg[key], str) or not leg[key]
                           for key in ("trip_id", "route_id", "service_id",
                                       "board_stop_id", "alight_stop_id"))
                    or not isinstance(leg["board_seconds"], int)
                    or isinstance(leg["board_seconds"], bool)
                    or not isinstance(leg["alight_seconds"], int)
                    or isinstance(leg["alight_seconds"], bool)
                    or leg["alight_seconds"] < leg["board_seconds"]
                    or not isinstance(leg["connection_ids"], list)
                    or not leg["connection_ids"]
                    or any(not isinstance(item, int) or isinstance(item, bool) or item <= 0
                           for item in leg["connection_ids"])):
                raise All19ExportError(f"{label} positive leg is malformed")
        if (legs[0]["trip_id"] != event["tripInstanceId"]
                or legs[0]["board_stop_id"] != event["stopId"]
                or legs[0]["board_seconds"] != event["boardSeconds"]
                or legs[0]["connection_ids"][0] != event["connectionId"]
                or legs[-1]["alight_seconds"] != arrival):
            raise All19ExportError(f"{label} positive path identity is malformed")
    return status


def _validate_manifest(manifest: dict, group: dict, expected_transfer_scope_sha256: str,
                       expected_registry_sha256: str) -> None:
    expected_sources = {
        "connections": CONNECTION_SHA256,
        "transferScope": expected_transfer_scope_sha256,
        "boardStopGemeinde": BOARD_STOP_SHA256,
        "targetRegistry": expected_registry_sha256,
    }
    if (manifest.get("kind") != "manifest"
            or manifest.get("schema") != "steuerpendler.canonical-event-slice.v1"
            or manifest.get("destinationBfs") != group["destinationBfs"]
            or manifest.get("destinationChildStopIds") != group["destinationChildStopIds"]
            or manifest.get("serviceDate") != route_export.SERVICE_DATE
            or manifest.get("timezone") != "Europe/Zurich"
            or manifest.get("firstBoardWindowSecondsInclusive")
            != [event_slice.FIRST_BOARD_START, event_slice.FIRST_BOARD_END]
            or manifest.get("maxElapsedSecondsInclusive") != event_slice.MAX_ELAPSED
            or manifest.get("sourceSha256") != expected_sources):
        raise All19ExportError(
            f"destination {group['destinationBfs']} slice manifest differs from pinned inputs")
    if (not isinstance(manifest.get("denominator"), int)
            or isinstance(manifest.get("denominator"), bool)
            or manifest["denominator"] < 0
            or not isinstance(manifest.get("sourceCoverage"), dict)
            or not isinstance(manifest.get("uncertaintyInventory"), dict)
            or not isinstance(manifest.get("unresolvedReasons"), list)
            or not manifest["unresolvedReasons"]
            or manifest.get("generatorVersion") != EVENT_SLICE_GENERATOR_VERSION
            or not isinstance(manifest.get("generatorSha256"), str)
            or manifest["generatorSha256"] != EVENT_SLICE_GENERATOR_SHA256
            or manifest.get("claims")
            != "BOUNDED_DESTINATION_POSITIVES_AND_UNKNOWNS_NOT_GLOBAL_PROOF"):
        raise All19ExportError(
            f"destination {group['destinationBfs']} slice provenance is malformed")
    coverage = manifest["sourceCoverage"]
    if (coverage.get("sourceCandidateFirstBoardEvents")
            != manifest["denominator"] + coverage.get("excludedFirstBoardEvents", -1)):
        raise All19ExportError(
            f"destination {group['destinationBfs']} source coverage is malformed")


def _common_manifest(manifest: dict) -> dict:
    keys = ("serviceDate", "timezone", "firstBoardWindowSecondsInclusive",
            "maxElapsedSecondsInclusive", "sourceSha256", "denominator",
            "sourceCoverage", "generatorVersion", "generatorSha256",
            "uncertaintyInventory", "unresolvedReasons")
    return {key: manifest.get(key) for key in keys}


def _validate_summary(summary: dict, denominator: int,
                      statuses: dict[str, Counter]) -> None:
    expected_statuses = {mode: dict(sorted(statuses[mode].items()))
                         for mode in ("allRoutes", "directOnly")}
    expected_positives = {mode: statuses[mode].get("best_found_unproven", 0)
                          for mode in statuses}
    expected_unknowns = {mode: statuses[mode].get("unknown", 0) for mode in statuses}
    if (summary.get("kind") != "summary"
            or summary.get("denominator") != denominator
            or summary.get("emitted") != denominator
            or summary.get("statuses") != expected_statuses
            or summary.get("positives") != expected_positives
            or summary.get("unknowns") != expected_unknowns):
        raise All19ExportError("slice summary does not match emitted records")


def aggregate_slices(slice_paths: dict[int, pathlib.Path], target_registry_path,
                     output_path, *, expected_transfer_scope_sha256,
                     child_reports=None):
    """Stream validated destination slices into one deterministic atomic matrix."""
    started = time.monotonic()
    registry = pathlib.Path(target_registry_path)
    actual_registry_sha256 = _sha256(registry)
    if actual_registry_sha256 != TARGET_REGISTRY_SHA256:
        raise All19ExportError(f"target registry SHA-256 mismatch: {actual_registry_sha256}")
    groups = load_destination_registry(registry)
    expected_bfs = {group["destinationBfs"] for group in groups}
    if set(slice_paths) != expected_bfs:
        raise All19ExportError("slice destinations do not exactly match the target registry")

    output = pathlib.Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    identity_descriptor, identity_name = tempfile.mkstemp(
        prefix=f".{output.name}.identities.", dir=output.parent)
    os.close(identity_descriptor)
    temporary = pathlib.Path(temporary_name)
    identity_path = pathlib.Path(identity_name)
    first_common = None
    first_fingerprint = None
    denominator = None
    totals = {"allRoutes": Counter(), "directOnly": Counter()}
    per_destination = []
    try:
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
                # The final manifest is emitted after inspecting the first slice but before
                # any event records. Later failures only discard this temporary file.
                for index, group in enumerate(groups):
                    bfs = group["destinationBfs"]
                    path = pathlib.Path(slice_paths[bfs])
                    try:
                        source = gzip.open(path, "rb")
                    except OSError as error:
                        raise All19ExportError(f"destination {bfs} slice is unreadable: {error}") from error
                    statuses = {"allRoutes": Counter(), "directOnly": Counter()}
                    count = 0
                    previous_id = None
                    fingerprint = hashlib.sha256()
                    identity_reader = None
                    try:
                        manifest = _read_payload(source, f"destination {bfs}")
                        if manifest is None:
                            raise All19ExportError(f"destination {bfs} slice is empty")
                        _validate_manifest(manifest, group, expected_transfer_scope_sha256,
                                           actual_registry_sha256)
                        common = _common_manifest(manifest)
                        if index == 0:
                            first_common = common
                            denominator = manifest["denominator"]
                            global_manifest = {
                                "kind": "manifest",
                                "schema": "steuerpendler.canonical-all19-event-matrix.v1",
                                "status": "PROVISIONAL_ENGINEERING_EVIDENCE",
                                "destinationBfs": [item["destinationBfs"] for item in groups],
                                "destinationGroups": groups,
                                "destinationCount": DESTINATION_COUNT,
                                "serviceDate": manifest["serviceDate"],
                                "timezone": manifest["timezone"],
                                "firstBoardWindowSecondsInclusive":
                                    manifest["firstBoardWindowSecondsInclusive"],
                                "maxElapsedSecondsInclusive":
                                    manifest["maxElapsedSecondsInclusive"],
                                "sourceSha256": manifest["sourceSha256"],
                                "sourceCoverage": manifest["sourceCoverage"],
                                "firstBoardEvents": denominator,
                                "eventDestinationRecords": denominator * DESTINATION_COUNT,
                                "generatorCodeSha256": {
                                    "canonicalEventSlice": manifest["generatorSha256"],
                                    "canonicalAll19Export": _sha256(pathlib.Path(__file__)),
                                },
                                "uncertaintyInventory": manifest["uncertaintyInventory"],
                                "unresolvedReasons": manifest["unresolvedReasons"],
                                "claims": (
                                    "BOUNDED_PROVISIONAL_POSITIVES_AND_UNKNOWNS;"
                                    "NOT_GLOBAL_FASTEST_OR_UNREACHABLE_PROOF"),
                            }
                            compressed.write(_json_bytes(global_manifest))
                            identity_writer = identity_path.open("wb")
                        else:
                            if common != first_common:
                                raise All19ExportError(
                                    f"destination {bfs} slice denominator/provenance mismatch")
                            identity_writer = None
                            identity_reader = identity_path.open("rb")
                        while True:
                            payload = _read_payload(source, f"destination {bfs}")
                            if payload is None:
                                raise All19ExportError(f"destination {bfs} slice is missing summary")
                            if payload.get("kind") == "summary":
                                summary = payload
                                if _read_payload(source, f"destination {bfs}") is not None:
                                    raise All19ExportError(
                                        f"destination {bfs} has records after its summary")
                                break
                            if set(payload) != {"event", "allRoutes", "directOnly"}:
                                raise All19ExportError(f"destination {bfs} event record is malformed")
                            event = _identity(payload["event"])
                            connection_id = event["connectionId"]
                            if previous_id is not None and connection_id <= previous_id:
                                raise All19ExportError(
                                    f"destination {bfs} connection IDs are not strictly increasing")
                            previous_id = connection_id
                            identity_bytes = _json_bytes(event)
                            fingerprint.update(identity_bytes)
                            if identity_writer is not None:
                                identity_writer.write(identity_bytes)
                            else:
                                if identity_reader.readline() != identity_bytes:
                                    raise All19ExportError(
                                        f"destination {bfs} first-event identity/order mismatch")
                            validated = {mode: _validate_result(payload[mode], event, mode)
                                         for mode in ("allRoutes", "directOnly")}
                            if (validated["directOnly"] == "best_found_unproven"
                                    and validated["allRoutes"] != "best_found_unproven"):
                                raise All19ExportError(
                                    f"destination {bfs} direct-only path lacks an all-routes path")
                            for mode, status in validated.items():
                                statuses[mode][status] += 1
                            payload["destinationBfs"] = bfs
                            compressed.write(_json_bytes(payload))
                            count += 1
                        if identity_writer is not None:
                            identity_writer.flush()
                            os.fsync(identity_writer.fileno())
                            identity_writer.close()
                            identity_writer = None
                            first_fingerprint = fingerprint.hexdigest()
                        else:
                            if identity_reader.readline():
                                raise All19ExportError(
                                    f"destination {bfs} first-event identity/order mismatch")
                            if fingerprint.hexdigest() != first_fingerprint:
                                raise All19ExportError(
                                    f"destination {bfs} first-event identity fingerprint mismatch")
                        if count != denominator:
                            raise All19ExportError(
                                f"destination {bfs} denominator mismatch: {count} != {denominator}")
                        _validate_summary(summary, denominator, statuses)
                        per_destination.append({
                            "destinationBfs": bfs, "denominator": denominator,
                            "statuses": {mode: dict(sorted(statuses[mode].items()))
                                         for mode in statuses},
                        })
                        for mode in totals:
                            totals[mode].update(statuses[mode])
                    except (OSError, EOFError, gzip.BadGzipFile) as error:
                        raise All19ExportError(
                            f"destination {bfs} gzip stream is corrupt: {error}") from error
                    finally:
                        source.close()
                        if identity_reader is not None:
                            identity_reader.close()
                        if "identity_writer" in locals() and identity_writer is not None:
                            identity_writer.close()
                global_summary = {
                    "kind": "summary",
                    "destinationCount": DESTINATION_COUNT,
                    "firstBoardEvents": denominator,
                    "eventDestinationRecords": denominator * DESTINATION_COUNT,
                    "firstEventIdentitySha256": first_fingerprint,
                    "statuses": {mode: dict(sorted(totals[mode].items())) for mode in totals},
                    "positives": {mode: totals[mode].get("best_found_unproven", 0)
                                  for mode in totals},
                    "unknowns": {mode: totals[mode].get("unknown", 0) for mode in totals},
                    "destinations": per_destination,
                }
                compressed.write(_json_bytes(global_summary))
            raw.flush()
            os.fsync(raw.fileno())
        output_bytes = temporary.stat().st_size
        output_sha256 = _sha256(temporary)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        identity_path.unlink(missing_ok=True)
    aggregate_report = {
        "output": str(output), "outputBytes": output_bytes,
        "outputSha256": output_sha256,
        "wallSeconds": time.monotonic() - started,
        "peakRssKiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    run_report = aggregate_report if child_reports is None else {
        "aggregate": aggregate_report, "children": child_reports,
    }
    report = output.with_suffix(output.suffix + ".run.json")
    report_descriptor, report_name = tempfile.mkstemp(
        prefix=f".{report.name}.staged.", dir=report.parent)
    os.close(report_descriptor)
    report_temporary = pathlib.Path(report_name)
    report_temporary.unlink()
    try:
        _atomic_json(report_temporary, run_report)
        _publish_pair(temporary, report_temporary, output, report)
    except BaseException:
        temporary.unlink(missing_ok=True)
        report_temporary.unlink(missing_ok=True)
        raise
    return global_manifest, global_summary, run_report


def export_all19(connections_path, transfer_scope_path, board_stop_path,
                 target_registry_path, output_path, *, expected_transfer_scope_sha256):
    """Stage pinned inputs once, run 19 isolated children sequentially, aggregate."""
    event_slice._validate_transfer_pin(expected_transfer_scope_sha256)
    output = pathlib.Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = pathlib.Path(tempfile.mkdtemp(prefix=".canonical-all19-stage-",
                                         dir=output.parent))
    stage.chmod(0o700)
    try:
        inputs = {
            "connections": (pathlib.Path(connections_path), CONNECTION_SHA256),
            "transferScope": (pathlib.Path(transfer_scope_path), expected_transfer_scope_sha256),
            "boardStopGemeinde": (pathlib.Path(board_stop_path), BOARD_STOP_SHA256),
            "targetRegistry": (pathlib.Path(target_registry_path), TARGET_REGISTRY_SHA256),
        }
        staged = {}
        for label, (source, expected) in inputs.items():
            destination = stage / f"{label}{source.suffix}"
            _copy_checked(source, destination, expected_sha256=expected,
                          max_bytes=MAX_INPUT_BYTES[label], label=label)
            staged[label] = destination
        groups = load_destination_registry(staged["targetRegistry"])
        slices = {}
        child_reports = []
        script = pathlib.Path(event_slice.__file__).resolve()
        for group in groups:
            bfs = group["destinationBfs"]
            child_output = stage / f"destination-{bfs}.ndjson.gz"
            command = [
                sys.executable, str(script),
                "--connections", str(staged["connections"]),
                "--transfer-scope", str(staged["transferScope"]),
                "--board-stops", str(staged["boardStopGemeinde"]),
                "--target-registry", str(staged["targetRegistry"]),
                "--output", str(child_output),
                "--expected-transfer-scope-sha256", expected_transfer_scope_sha256,
                "--destination-bfs", str(bfs),
            ]
            try:
                process = subprocess.run(command, stdin=subprocess.DEVNULL,
                                         capture_output=True, text=True,
                                         timeout=CHILD_TIMEOUT_SECONDS,
                                         preexec_fn=_bound_child_address_space,
                                         check=False)
            except subprocess.TimeoutExpired as error:
                raise All19ExportError(
                    f"destination {bfs} child exceeded {CHILD_TIMEOUT_SECONDS}s") from error
            if process.returncode != 0:
                detail = (process.stderr or process.stdout).strip()[-2000:]
                raise All19ExportError(
                    f"destination {bfs} child failed ({process.returncode}): {detail}")
            if not child_output.is_file():
                raise All19ExportError(f"destination {bfs} child produced no slice")
            report_path = child_output.with_suffix(child_output.suffix + ".run.json")
            if not report_path.is_file():
                raise All19ExportError(f"destination {bfs} child produced no run report")
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise All19ExportError(
                    f"destination {bfs} child run report is malformed") from error
            _validate_child_memory(report, bfs)
            child_reports.append({"destinationBfs": bfs, **report})
            slices[bfs] = child_output
        manifest, summary, aggregate_report = aggregate_slices(
            slices, staged["targetRegistry"], output,
            expected_transfer_scope_sha256=expected_transfer_scope_sha256,
            child_reports=child_reports)
        return manifest, summary, aggregate_report
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connections", required=True)
    parser.add_argument("--transfer-scope", required=True)
    parser.add_argument("--board-stops", required=True)
    parser.add_argument("--target-registry", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-transfer-scope-sha256", required=True)
    args = parser.parse_args()
    manifest, summary, report = export_all19(
        args.connections, args.transfer_scope, args.board_stops,
        args.target_registry, args.output,
        expected_transfer_scope_sha256=args.expected_transfer_scope_sha256)
    print(json.dumps({"manifest": manifest, "summary": summary, "run": report},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
