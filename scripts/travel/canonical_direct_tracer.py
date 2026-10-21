"""Build a bounded, direct-only canonical Route diagnostic for Aarau.

This tracer consumes the pinned positive-screen result and streams only
``trips.txt`` from the matching GTFS archive.  It does not search transfers and
therefore emits only ``best_found_unproven`` records.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import pathlib
import resource
import tempfile
import time
import zipfile

EXPECTED_SOURCE_SHA256 = "0f373c32bf994f145e6b16d3ad5864017f41cb969ea7c67bc84235b9edbc9edb"
EXPECTED_GTFS_SHA256 = "d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e"
REFERENCE_DATE = "2026-10-27"
DESTINATION_BFS = 4001
WINDOW_START_SECONDS = 6 * 3600 + 30 * 60
WINDOW_END_SECONDS = 8 * 3600 + 30 * 60
CAP_SECONDS = 1800
COVERAGE = "PARTIAL_DIRECT_ONLY"
REASON = "transfer_search_missing"


class TracerError(ValueError):
    """An input cannot safely support the bounded diagnostic."""


def _sha256(path):
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _require_int(row, field, index):
    value = row.get(field)
    if type(value) is not int:
        raise TracerError(f"journey {index}: invalid {field}")
    return value


def _require_string(row, field, index):
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise TracerError(f"journey {index}: invalid {field}")
    return value


def _load_source(path, expected_hash, expected_gtfs_hash, max_input_rows):
    if type(max_input_rows) is not int or max_input_rows < 1:
        raise TracerError("max_input_rows must be a positive integer")
    actual_hash = _sha256(path)
    if actual_hash != expected_hash:
        raise TracerError("source SHA-256 mismatch")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TracerError(f"invalid source JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise TracerError("invalid source JSON root")
    if payload.get("service_day") != REFERENCE_DATE:
        raise TracerError("source service_day mismatch")
    if payload.get("boarding_window_inclusive") != ["06:30:00", "08:30:00"]:
        raise TracerError("source boarding window mismatch")
    if payload.get("cap_seconds_inclusive") != CAP_SECONDS:
        raise TracerError("source cap mismatch")
    if payload.get("direct_only") is not True:
        raise TracerError("source is not direct-only")
    if payload.get("source_sha256") != expected_gtfs_hash:
        raise TracerError("source GTFS SHA-256 mismatch")
    journeys = payload.get("journeys")
    if not isinstance(journeys, list):
        raise TracerError("source journeys must be an array")
    if len(journeys) > max_input_rows:
        raise TracerError("source journey count exceeds max_input_rows")
    if payload.get("journey_count") != len(journeys):
        raise TracerError("source journey_count mismatch")
    groups = payload.get("destination_children")
    if not isinstance(groups, dict) or not groups:
        raise TracerError("missing destination_children")
    children = set()
    for parent, values in groups.items():
        if not isinstance(parent, str) or not parent or not isinstance(values, list) or not values:
            raise TracerError("invalid destination_children")
        for child in values:
            if not isinstance(child, str) or not child or child in children:
                raise TracerError("invalid or duplicate destination child")
            children.add(child)
    return payload, journeys, children, actual_hash


def _validated_rows(journeys, destination_children):
    selected = {}
    referenced_trips = set()
    observed_in_bounds = 0
    for index, row in enumerate(journeys):
        if not isinstance(row, dict):
            raise TracerError(f"journey {index}: expected object")
        trip_id = _require_string(row, "trip_id", index)
        stop_id = _require_string(row, "boarding_stop_id", index)
        stop_sequence = _require_int(row, "boarding_stop_sequence", index)
        board = _require_int(row, "boarding_seconds", index)
        arrival_stop = _require_string(row, "destination_stop_id", index)
        arrival_sequence = _require_int(row, "destination_stop_sequence", index)
        arrival = _require_int(row, "arrival_seconds", index)
        service_id = _require_string(row, "service_id", index)
        elapsed = _require_int(row, "transit_seconds", index)
        if arrival_stop not in destination_children:
            raise TracerError(f"journey {index}: unknown destination terminal")
        if stop_sequence < 0 or arrival_sequence <= stop_sequence:
            raise TracerError(f"journey {index}: invalid stop sequence chronology")
        if arrival - board != elapsed or elapsed < 0:
            raise TracerError(f"journey {index}: transit_seconds mismatch")
        referenced_trips.add(trip_id)
        if not (WINDOW_START_SECONDS <= board <= WINDOW_END_SECONDS and elapsed <= CAP_SECONDS):
            continue
        observed_in_bounds += 1
        key = (trip_id, stop_id, stop_sequence, board)
        candidate = {
            "arrival_seconds": arrival,
            "arrival_stop_id": arrival_stop,
            "arrival_stop_sequence": arrival_sequence,
            "board_seconds": board,
            "board_stop_id": stop_id,
            "board_stop_sequence": stop_sequence,
            "elapsed_seconds": elapsed,
            "service_id": service_id,
            "trip_id": trip_id,
        }
        tie_key = (arrival, arrival_stop, arrival_sequence)
        prior = selected.get(key)
        if prior is None or tie_key < (
                prior["arrival_seconds"], prior["arrival_stop_id"],
                prior["arrival_stop_sequence"]):
            selected[key] = candidate
    return selected, referenced_trips, observed_in_bounds


def _trip_metadata(feed_path, expected_hash, referenced_trips):
    actual_hash = _sha256(feed_path)
    if actual_hash != expected_hash:
        raise TracerError("GTFS SHA-256 mismatch")
    selected = {}
    scanned = 0
    try:
        with zipfile.ZipFile(feed_path) as archive:
            if "trips.txt" not in archive.namelist():
                raise TracerError("missing trips.txt")
            with archive.open("trips.txt") as raw, io.TextIOWrapper(
                    raw, encoding="utf-8-sig", newline="") as text:
                reader = csv.DictReader(text)
                required = {"trip_id", "route_id", "service_id"}
                missing = required - set(reader.fieldnames or ())
                if missing:
                    raise TracerError(f"invalid trips.txt: missing {sorted(missing)[0]}")
                for row in reader:
                    scanned += 1
                    trip_id = row["trip_id"]
                    if trip_id not in referenced_trips:
                        continue
                    if trip_id in selected:
                        raise TracerError(f"duplicate trip_id in trips.txt: {trip_id}")
                    if not row["route_id"]:
                        raise TracerError(f"missing route_id for trip: {trip_id}")
                    if not row["service_id"]:
                        raise TracerError(f"missing service_id for trip: {trip_id}")
                    selected[trip_id] = {
                        "route_id": row["route_id"],
                        "service_id": row["service_id"],
                    }
    except (OSError, UnicodeError, csv.Error, zipfile.BadZipFile) as exc:
        raise TracerError(f"unreadable GTFS trips.txt: {exc}") from exc
    absent = sorted(referenced_trips - set(selected))
    if absent:
        raise TracerError(f"missing trip metadata: {absent[0]}")
    return selected, actual_hash, scanned


def _route_record(row, metadata):
    if row["service_id"] != metadata["service_id"]:
        raise TracerError(f"service_id mismatch for trip: {row['trip_id']}")
    leg = {
        "alightSeconds": row["arrival_seconds"],
        "alightSequence": row["arrival_stop_sequence"],
        "alightStopId": row["arrival_stop_id"],
        "boardSeconds": row["board_seconds"],
        "boardSequence": row["board_stop_sequence"],
        "boardStopId": row["board_stop_id"],
        "routeId": metadata["route_id"],
        "serviceId": metadata["service_id"],
        "tripId": row["trip_id"],
        "tripInstanceId": row["trip_id"],
    }
    return {
        "destinationBfs": DESTINATION_BFS,
        "itinerary": {
            "arrivalSeconds": row["arrival_seconds"],
            "arrivalStopId": row["arrival_stop_id"],
            "elapsedSeconds": row["elapsed_seconds"],
            "legs": [leg],
            "minutes": (row["elapsed_seconds"] + 59) // 60,
            "transfers": [],
        },
        "kind": "route",
        "origin": {
            "boardSeconds": row["board_seconds"],
            "stopId": row["board_stop_id"],
            "stopSequence": row["board_stop_sequence"],
            "tripId": row["trip_id"],
            "tripInstanceId": row["trip_id"],
        },
        "schemaVersion": 1,
        "status": "best_found_unproven",
        "unresolvedReasons": [REASON],
    }


def _json_line(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def _gzip_bytes(records):
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0, compresslevel=9) as stream:
        for record in records:
            stream.write(_json_line(record).encode("utf-8"))
    return output.getvalue()


def _atomic_write(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def trace_direct_routes(source_path, feed_path, output_path, report_path, *,
                        expected_source_sha256, expected_gtfs_sha256,
                        max_input_rows, max_output_rows):
    """Trace bounded direct positives into deterministic canonical Route NDJSON."""
    if type(max_output_rows) is not int or max_output_rows < 1:
        raise TracerError("max_output_rows must be a positive integer")
    source_path = pathlib.Path(source_path)
    feed_path = pathlib.Path(feed_path)
    output_path = pathlib.Path(output_path)
    report_path = pathlib.Path(report_path)
    if len({path.resolve() for path in (source_path, feed_path, output_path, report_path)}) != 4:
        raise TracerError("output/report path aliases input or each other")
    payload, journeys, children, source_hash = _load_source(
        source_path, expected_source_sha256, expected_gtfs_sha256, max_input_rows)
    selected, referenced_trips, observed_in_bounds = _validated_rows(journeys, children)
    if len(selected) > max_output_rows:
        raise TracerError("route count exceeds max_output_rows")
    metadata, gtfs_hash, trips_scanned = _trip_metadata(
        feed_path, expected_gtfs_sha256, referenced_trips)
    routes = [_route_record(row, metadata[row["trip_id"]]) for row in selected.values()]
    routes.sort(key=lambda record: (
        record["destinationBfs"], record["origin"]["boardSeconds"],
        record["origin"]["stopId"], record["origin"]["tripInstanceId"],
        record["origin"]["stopSequence"],
    ))
    manifest = {
        "accessModel": "zero_unmeasured_provisional",
        "boardingWindowInclusiveSeconds": [WINDOW_START_SECONDS, WINDOW_END_SECONDS],
        "capSecondsInclusive": CAP_SECONDS,
        "coverage": COVERAGE,
        "destinationBfs": DESTINATION_BFS,
        "destinationChildren": sorted(children),
        "directOnly": True,
        "gtfsSha256": gtfs_hash,
        "kind": "manifest",
        "referenceDate": REFERENCE_DATE,
        "schemaVersion": 1,
        "sourceSha256": source_hash,
        "timezone": "Europe/Zurich",
    }
    summary = {
        "coverage": COVERAGE,
        "inputJourneyRows": len(journeys),
        "kind": "summary",
        "observedInBoundsRows": observed_in_bounds,
        "routeCount": len(routes),
        "schemaVersion": 1,
        "statusCounts": {"best_found_unproven": len(routes)},
        "tripsTxtRowsScanned": trips_scanned,
        "uniqueObservedEvents": len(routes),
    }
    compressed = _gzip_bytes([manifest, *routes, summary])
    result_hash = hashlib.sha256(compressed).hexdigest()
    report = {
        "coverage": COVERAGE,
        "destination_bfs": DESTINATION_BFS,
        "gtfs_sha256": gtfs_hash,
        "input_journey_rows": len(journeys),
        "max_input_rows": max_input_rows,
        "max_output_rows": max_output_rows,
        "observed_in_bounds_rows": observed_in_bounds,
        "result_bytes": len(compressed),
        "result_sha256": result_hash,
        "route_count": len(routes),
        "source_sha256": source_hash,
        "trips_txt_rows_scanned": trips_scanned,
    }
    report_bytes = json.dumps(report, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    _atomic_write(output_path, compressed)
    _atomic_write(report_path, report_bytes)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--feed", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--expected-source-sha256", default=EXPECTED_SOURCE_SHA256)
    parser.add_argument("--expected-gtfs-sha256", default=EXPECTED_GTFS_SHA256)
    parser.add_argument("--max-input-rows", required=True, type=int)
    parser.add_argument("--max-output-rows", required=True, type=int)
    args = parser.parse_args()
    started = time.monotonic()
    report = trace_direct_routes(
        args.source, args.feed, args.output, args.report,
        expected_source_sha256=args.expected_source_sha256,
        expected_gtfs_sha256=args.expected_gtfs_sha256,
        max_input_rows=args.max_input_rows,
        max_output_rows=args.max_output_rows,
    )
    diagnostic = dict(report)
    diagnostic.update({
        "output_path": str(pathlib.Path(args.output).resolve()),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "report_path": str(pathlib.Path(args.report).resolve()),
        "wall_seconds": time.monotonic() - started,
    })
    print(json.dumps(diagnostic, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
