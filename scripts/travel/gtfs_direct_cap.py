"""Bounded direct-only GTFS positive journey screen.

This tool proves only scheduled direct rides to explicitly supplied destination
parents. It does not search transfers, residential access, or municipality
eligibility, and its provisional service day is not owner-approved.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import pathlib
import resource
import time
import zipfile

from primitives import gtfs_seconds


EXPECTED_GTFS_SHA256 = "d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e"
DEFAULT_DAY = dt.date(2026, 10, 27)
WINDOW_START = "06:30:00"
WINDOW_END = "08:30:00"
CAP_SECONDS = 1800


class DirectCapError(ValueError):
    """The source cannot safely support this bounded screen."""


def _sha256(path):
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _rows(archive, name, required_fields, *, optional=False):
    if name not in archive.namelist():
        if optional:
            return
        raise DirectCapError(f"missing {name}")
    try:
        with archive.open(name) as raw, io.TextIOWrapper(
                raw, encoding="utf-8-sig", newline="") as text:
            reader = csv.DictReader(text)
            fields = set(reader.fieldnames or ())
            missing = required_fields - fields
            if missing:
                raise DirectCapError(
                    f"invalid {name}: missing field {sorted(missing)[0]}")
            yield from reader
    except (csv.Error, UnicodeError, KeyError) as exc:
        raise DirectCapError(f"invalid {name}: {exc}") from exc


def _stops(archive, destination_parents, counts):
    stops = {}
    parent_names = {}
    children = {parent: [] for parent in destination_parents}
    required = {"stop_id", "stop_name", "location_type", "parent_station"}
    for row in _rows(archive, "stops.txt", required):
        counts["stops"] += 1
        stop_id = row["stop_id"]
        if not stop_id or stop_id in stops:
            raise DirectCapError("invalid stops.txt: empty or duplicate stop_id")
        location_type = row["location_type"] or "0"
        parent = row["parent_station"]
        stops[stop_id] = parent or stop_id
        if stop_id in destination_parents:
            if location_type != "1" or parent:
                raise DirectCapError(f"destination parent must be a parent station: {stop_id}")
            parent_names[stop_id] = row["stop_name"]
        if location_type == "0" and parent in destination_parents:
            children[parent].append(stop_id)
    missing = sorted(destination_parents - set(parent_names))
    if missing:
        raise DirectCapError(f"destination parent absent from stops.txt: {missing[0]}")
    empty = sorted(parent for parent, values in children.items() if not values)
    if empty:
        raise DirectCapError(f"destination parent has no observed children: {empty[0]}")
    return stops, {parent: sorted(values) for parent, values in sorted(children.items())}


def _target_trips(archive, target_children, counts):
    trips = set()
    required = {"trip_id", "stop_id"}
    for row in _rows(archive, "stop_times.txt", required):
        counts["stop_times_pass_1"] += 1
        if not row["trip_id"] or not row["stop_id"]:
            raise DirectCapError("invalid stop_times.txt: empty trip_id or stop_id")
        if row["stop_id"] in target_children:
            trips.add(row["trip_id"])
    return trips


def _trip_services(archive, target_trips, counts):
    selected = {}
    for row in _rows(archive, "trips.txt", {"trip_id", "service_id"}):
        counts["trips"] += 1
        trip_id = row["trip_id"]
        if trip_id not in target_trips:
            continue
        if not row["service_id"] or trip_id in selected:
            raise DirectCapError("invalid trips.txt: target trip has missing service or duplicate ID")
        selected[trip_id] = row["service_id"]
    missing = sorted(target_trips - set(selected))
    if missing:
        raise DirectCapError(f"target trip absent from trips.txt: {missing[0]}")
    return selected


def _active_selected_services(archive, day, selected_services, counts):
    date = day.strftime("%Y%m%d")
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday",
               "saturday", "sunday")[day.weekday()]
    base = set()
    seen = set()
    required = {"service_id", weekday, "start_date", "end_date"}
    for row in _rows(archive, "calendar.txt", required, optional=True) or ():
        counts["calendar"] += 1
        service = row["service_id"]
        if service not in selected_services:
            continue
        if not service or service in seen:
            raise DirectCapError("invalid calendar.txt: selected service missing or duplicate")
        seen.add(service)
        if row[weekday] not in {"0", "1"}:
            raise DirectCapError("invalid calendar.txt: invalid weekday value")
        if row["start_date"] <= date <= row["end_date"] and row[weekday] == "1":
            base.add(service)
    active = set(base)
    added = set()
    removed = set()
    seen_exceptions = set()
    required = {"service_id", "date", "exception_type"}
    for row in _rows(archive, "calendar_dates.txt", required, optional=True) or ():
        counts["calendar_dates"] += 1
        service = row["service_id"]
        if service not in selected_services or row["date"] != date:
            continue
        key = (service, row["date"])
        if not service or key in seen_exceptions:
            raise DirectCapError("invalid calendar_dates.txt: selected duplicate service/day")
        seen_exceptions.add(key)
        if row["exception_type"] == "1":
            active.add(service)
            added.add(service)
            removed.discard(service)
        elif row["exception_type"] == "2":
            active.discard(service)
            removed.add(service)
            added.discard(service)
        else:
            raise DirectCapError("invalid calendar_dates.txt: unsupported exception_type")
    provenance = {
        service: "exception_added" if service in added else "base_calendar"
        for service in active
    }
    return active, provenance, removed


def _frequency_classes(archive, active_target_trips, counts):
    classes = {}
    required = {"trip_id", "start_time", "end_time", "headway_secs", "exact_times"}
    for row in _rows(archive, "frequencies.txt", required, optional=True) or ():
        counts["frequencies"] += 1
        trip_id = row["trip_id"]
        if trip_id not in active_target_trips:
            continue
        exact = row["exact_times"] or "0"
        if exact not in {"0", "1"}:
            raise DirectCapError("invalid frequencies.txt: unsupported exact_times")
        classes.setdefault(trip_id, set()).add(exact)
    return classes


def _selected_stop_times(archive, active_trips, known_stop_ids, counts, unresolved):
    selected = {trip_id: [] for trip_id in active_trips}
    invalid_trips = set()
    required = {"trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"}
    for row in _rows(archive, "stop_times.txt", required):
        counts["stop_times_pass_2"] += 1
        trip_id = row["trip_id"]
        if trip_id not in selected:
            continue
        try:
            sequence = int(row["stop_sequence"])
            if sequence < 0 or not row["stop_id"] or row["stop_id"] not in known_stop_ids:
                raise ValueError("invalid sequence/stop")
            arrival_seconds = gtfs_seconds(row["arrival_time"])
            departure_seconds = gtfs_seconds(row["departure_time"])
        except (TypeError, ValueError) as exc:
            unresolved["malformed_scoped_stop_time_rows"] += 1
            invalid_trips.add(trip_id)
            continue
        pickup = row.get("pickup_type", "") or "0"
        drop_off = row.get("drop_off_type", "") or "0"
        if pickup not in {"0", "1", "2", "3"} or drop_off not in {"0", "1", "2", "3"}:
            unresolved["malformed_scoped_stop_time_rows"] += 1
            invalid_trips.add(trip_id)
            continue
        if pickup in {"2", "3"} or drop_off in {"2", "3"}:
            unresolved["pickup_or_drop_off_type_2_or_3"] += 1
        if row.get("timepoint") == "0":
            unresolved["timepoint_0_rows"] += 1
            invalid_trips.add(trip_id)
            continue
        selected[trip_id].append({
            "arrival_seconds": arrival_seconds,
            "arrival_time": row["arrival_time"],
            "departure_seconds": departure_seconds,
            "departure_time": row["departure_time"],
            "drop_off_type": drop_off,
            "pickup_type": pickup,
            "stop_id": row["stop_id"],
            "stop_sequence": sequence,
        })
    # A missing/invalid intermediate stop cannot be bypassed by joining the
    # remaining rows: that would fabricate a direct ride across a broken trip.
    for trip_id in invalid_trips:
        selected.pop(trip_id)
    unresolved["invalid_scoped_trips"] = len(invalid_trips)
    return selected


def screen_direct_journeys(feed_path, service_day, destination_parent_ids, result_path,
                            *, expected_sha256=None, sample_limit=10):
    """Write deterministic direct-positive evidence and return its full payload."""
    if not isinstance(service_day, dt.date):
        raise DirectCapError("service_day must be a date")
    destination_parents = set(destination_parent_ids)
    if not destination_parents or any(not isinstance(value, str) or not value
                                      for value in destination_parents):
        raise DirectCapError("nonempty destination parent IDs are required")
    if type(sample_limit) is not int or sample_limit < 0:
        raise DirectCapError("sample_limit must be a nonnegative integer")
    feed_path = pathlib.Path(feed_path)
    result_path = pathlib.Path(result_path)
    source_hash = _sha256(feed_path)
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise DirectCapError("GTFS SHA-256 mismatch")

    counts = {name: 0 for name in (
        "stops", "stop_times_pass_1", "trips", "calendar",
        "calendar_dates", "frequencies", "stop_times_pass_2"
    )}
    unresolved = {
        "frequency_exact_times_0_trips": 0,
        "frequency_exact_times_1_trips": 0,
        "malformed_scoped_stop_time_rows": 0,
        "pickup_or_drop_off_type_2_or_3": 0,
        "timepoint_0_rows": 0,
        "nonmonotonic_trip_time": 0,
    }
    excluded = {"pickup_type_1": 0, "drop_off_type_1": 0}
    try:
        with zipfile.ZipFile(feed_path) as archive:
            stop_parents, destination_children = _stops(
                archive, destination_parents, counts)
            target_children = {
                child for children in destination_children.values() for child in children
            }
            target_trips = _target_trips(archive, target_children, counts)
            trip_services = _trip_services(archive, target_trips, counts)
            active_services, provenance, removed_services = _active_selected_services(
                archive, service_day, set(trip_services.values()), counts)
            active_trips = {
                trip: service for trip, service in trip_services.items()
                if service in active_services
            }
            frequencies = _frequency_classes(archive, set(active_trips), counts)
            fixed_trips = set(active_trips) - set(frequencies)
            rows_by_trip = _selected_stop_times(
                archive, fixed_trips, stop_parents, counts, unresolved)
    except (OSError, zipfile.BadZipFile) as exc:
        raise DirectCapError(f"unreadable GTFS archive: {exc}") from exc

    unresolved_frequency_trips = []
    for trip_id, classes in sorted(frequencies.items()):
        for exact in sorted(classes):
            unresolved[f"frequency_exact_times_{exact}_trips"] += 1
            unresolved_frequency_trips.append({
                "exact_times": exact,
                "service_id": active_trips[trip_id],
                "trip_id": trip_id,
            })

    child_parent = {
        child: parent for parent, children in destination_children.items() for child in children
    }
    start = gtfs_seconds(WINDOW_START)
    end = gtfs_seconds(WINDOW_END)
    journeys = []
    duplicate_sequence_trips = 0
    for trip_id, rows in sorted(rows_by_trip.items()):
        rows.sort(key=lambda item: (item["stop_sequence"], item["stop_id"]))
        if len({row["stop_sequence"] for row in rows}) != len(rows):
            duplicate_sequence_trips += 1
            continue
        previous_departure = None
        chronology_invalid = False
        for row in rows:
            if (row["arrival_seconds"] > row["departure_seconds"] or
                    (previous_departure is not None and row["arrival_seconds"] < previous_departure)):
                chronology_invalid = True
                break
            previous_departure = row["departure_seconds"]
        if chronology_invalid:
            unresolved["nonmonotonic_trip_time"] += 1
            continue
        for destination_index, destination in enumerate(rows):
            if destination["stop_id"] not in target_children:
                continue
            if destination["drop_off_type"] == "1":
                excluded["drop_off_type_1"] += 1
                continue
            if destination["drop_off_type"] in {"2", "3"}:
                continue
            for boarding in rows[:destination_index]:
                if boarding["pickup_type"] == "1":
                    excluded["pickup_type_1"] += 1
                    continue
                if boarding["pickup_type"] in {"2", "3"}:
                    continue
                departure = boarding["departure_seconds"]
                elapsed = destination["arrival_seconds"] - departure
                if not start <= departure <= end or not 0 <= elapsed <= CAP_SECONDS:
                    continue
                journeys.append({
                    "arrival_seconds": destination["arrival_seconds"],
                    "arrival_time": destination["arrival_time"],
                    "boarding_parent_id": stop_parents.get(boarding["stop_id"], boarding["stop_id"]),
                    "boarding_seconds": departure,
                    "boarding_stop_id": boarding["stop_id"],
                    "boarding_stop_sequence": boarding["stop_sequence"],
                    "boarding_time": boarding["departure_time"],
                    "destination_parent_id": child_parent[destination["stop_id"]],
                    "destination_stop_id": destination["stop_id"],
                    "destination_stop_sequence": destination["stop_sequence"],
                    "service_id": active_trips[trip_id],
                    "service_provenance": provenance[active_trips[trip_id]],
                    "transit_seconds": elapsed,
                    "trip_id": trip_id,
                })
    if duplicate_sequence_trips:
        unresolved["duplicate_sequence_trips"] = duplicate_sequence_trips
    journeys.sort(key=lambda row: (
        row["boarding_seconds"], row["arrival_seconds"], row["trip_id"],
        row["boarding_stop_sequence"], row["destination_stop_sequence"],
        row["boarding_stop_id"], row["destination_stop_id"]
    ))
    status = ("DIRECT_POSITIVES_WITH_UNRESOLVED_CLASSES"
              if any(unresolved.values()) else "DIRECT_POSITIVES_ENUMERATED")
    payload = {
        "boarding_window_inclusive": [WINDOW_START, WINDOW_END],
        "cap_seconds_inclusive": CAP_SECONDS,
        "destination_children": destination_children,
        "destination_parent_ids": sorted(destination_parents),
        "direct_only": True,
        "excluded_counts": excluded,
        "journey_count": len(journeys),
        "journeys": journeys,
        "limitations": [
            "No transfers or alternative destination access are searched.",
            "No origin walking or municipality eligibility is evaluated.",
            "Absence from this positive screen is unknown, not proof of ineligibility.",
            "The provisional service day is not an approved reference day.",
        ],
        "removed_service_count": len(removed_services),
        "sample_journeys": journeys[:sample_limit],
        "scanned_counts": counts,
        "service_day": service_day.isoformat(),
        "source_sha256": source_hash,
        "status": status,
        "timezone": "Europe/Zurich",
        "unresolved_counts": unresolved,
        "unresolved_frequency_trips": unresolved_frequency_trips,
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", required=True)
    parser.add_argument("--service-day", default=DEFAULT_DAY.isoformat())
    parser.add_argument("--destination-parent", action="append", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--expected-sha256", default=EXPECTED_GTFS_SHA256)
    parser.add_argument("--sample-limit", type=int, default=10)
    args = parser.parse_args()
    try:
        day = dt.date.fromisoformat(args.service_day)
    except ValueError as exc:
        raise DirectCapError(f"invalid service day: {exc}") from exc
    started = time.monotonic()
    payload = screen_direct_journeys(
        args.feed,
        day,
        args.destination_parent,
        args.result,
        expected_sha256=args.expected_sha256,
        sample_limit=args.sample_limit,
    )
    report = {
        "journey_count": payload["journey_count"],
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "result_path": str(pathlib.Path(args.result).resolve()),
        "result_sha256": _sha256(args.result),
        "scanned_counts": payload["scanned_counts"],
        "source_sha256": payload["source_sha256"],
        "status": payload["status"],
        "unresolved_counts": payload["unresolved_counts"],
        "wall_seconds": time.monotonic() - started,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
