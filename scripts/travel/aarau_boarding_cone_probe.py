"""Bounded GTFS first-boarding cone candidate enumeration.

This is a straight-line screening probe, not pedestrian routing, route search, or
reference-day approval. It streams the large trips and stop_times tables.
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
DEFAULT_RADIUS_M = 1080.0


class BoardingConeError(ValueError):
    """The source cannot safely produce boarding candidates."""


class _PyprojGeometry:
    """WGS84 geometry loaded only for real probe calls."""

    def __init__(self):
        try:
            from pyproj import Geod, Transformer
        except ImportError as exc:
            raise BoardingConeError(
                "pyproj is required for real WGS84 boarding-cone geometry"
            ) from exc
        self._geod = Geod(ellps="WGS84")
        self._transformer = Transformer

    def transform(self, source_crs, x, y):
        return self._transformer.from_crs(
            source_crs, "EPSG:4326", always_xy=True
        ).transform(x, y)

    def distance(self, origin_longitude, origin_latitude, longitude, latitude):
        return self._geod.inv(
            origin_longitude, origin_latitude, longitude, latitude
        )[2]


def _sha256(path):
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _rows(archive, name, required_fields, optional=False):
    if name not in archive.namelist():
        if optional:
            return
        raise BoardingConeError(f"missing {name}")
    try:
        with archive.open(name) as raw, io.TextIOWrapper(
                raw, encoding="utf-8-sig", newline="") as text:
            rows = csv.DictReader(text)
            fields = set(rows.fieldnames or ())
            missing = required_fields - fields
            if missing:
                raise BoardingConeError(
                    f"invalid {name}: missing field {sorted(missing)[0]}")
            yield from rows
    except (csv.Error, UnicodeError, KeyError) as exc:
        raise BoardingConeError(f"invalid {name}: {exc}") from exc


def _active_services(archive, day, counts):
    date = day.strftime("%Y%m%d")
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[day.weekday()]
    required = {"service_id", weekday, "start_date", "end_date"}
    active = set()
    seen = set()
    for row in _rows(archive, "calendar.txt", required, optional=True) or ():
        counts["calendar"] += 1
        service = row["service_id"]
        if not service or service in seen:
            raise BoardingConeError("invalid calendar.txt: missing or duplicate service_id")
        seen.add(service)
        if row[weekday] not in {"0", "1"}:
            raise BoardingConeError("invalid calendar.txt: invalid weekday value")
        if row["start_date"] <= date <= row["end_date"] and row[weekday] == "1":
            active.add(service)
    seen_exceptions = set()
    for row in _rows(
            archive,
            "calendar_dates.txt",
            {"service_id", "date", "exception_type"},
            optional=True,
    ) or ():
        counts["calendar_dates"] += 1
        if row["date"] != date:
            continue
        key = (row["service_id"], row["date"])
        if not row["service_id"] or key in seen_exceptions:
            raise BoardingConeError("invalid calendar_dates.txt: missing or duplicate service/day")
        seen_exceptions.add(key)
        if row["exception_type"] == "1":
            active.add(row["service_id"])
        elif row["exception_type"] == "2":
            active.discard(row["service_id"])
        else:
            raise BoardingConeError("invalid calendar_dates.txt: unsupported exception_type")
    return active


def _origin_points(origins, geometry_provider=None):
    geometry = geometry_provider or _PyprojGeometry()
    points = []
    for origin in origins:
        try:
            origin_id = origin["origin_id"]
            source_crs = origin["source_crs"]
            x, y = float(origin["x"]), float(origin["y"])
            longitude, latitude = geometry.transform(source_crs, x, y)
        except (KeyError, TypeError, ValueError) as exc:
            raise BoardingConeError(f"invalid origin: {exc}") from exc
        if not origin_id:
            raise BoardingConeError("invalid origin: empty origin_id")
        points.append({
            "origin_id": str(origin_id),
            "source_crs": str(source_crs),
            "source_coordinates": [x, y],
            "longitude": longitude,
            "latitude": latitude,
            "geometry": geometry,
        })
    if not points:
        raise BoardingConeError("at least one origin is required")
    return points


def _candidate_stops(archive, origins, radius_m, counts):
    candidates = {}
    unparented = []
    for row in _rows(
            archive,
            "stops.txt",
            {"stop_id", "stop_name", "stop_lat", "stop_lon", "location_type", "parent_station"},
    ):
        counts["stops"] += 1
        stop_id = row["stop_id"]
        if not stop_id:
            raise BoardingConeError("invalid stops.txt: empty stop_id")
        location_type = row["location_type"] or "0"
        if location_type != "0":
            continue
        try:
            latitude = float(row["stop_lat"])
            longitude = float(row["stop_lon"])
        except ValueError as exc:
            raise BoardingConeError(f"invalid stops.txt coordinates for {stop_id}") from exc
        matches = []
        for origin in origins:
            distance = origin["geometry"].distance(
                origin["longitude"], origin["latitude"], longitude, latitude
            )
            if distance <= radius_m:
                matches.append({
                    "origin_id": origin["origin_id"],
                    "origin_source_crs": origin["source_crs"],
                    "origin_source_coordinates": origin["source_coordinates"],
                    "origin_longitude": origin["longitude"],
                    "origin_latitude": origin["latitude"],
                    "geodesic_distance_m": distance,
                })
        if matches:
            if not row["parent_station"]:
                unparented.append(stop_id)
                continue
            candidates[stop_id] = {
                "source_stop_id": stop_id,
                "parent_stop_id": row["parent_station"],
                "stop_name": row["stop_name"],
                "stop_longitude": longitude,
                "stop_latitude": latitude,
                "origins": matches,
            }
    return candidates, sorted(unparented)


def probe_feed(feed_path, service_day, origins, result_path, *, radius_m=DEFAULT_RADIUS_M,
               expected_sha256=None, sample_limit=5, geometry_provider=None):
    """Write every scoped candidate record and return a bounded summary."""
    if not isinstance(service_day, dt.date):
        raise BoardingConeError("service_day must be a date")
    if radius_m <= 0:
        raise BoardingConeError("radius_m must be positive")
    feed_path = pathlib.Path(feed_path)
    result_path = pathlib.Path(result_path)
    source_hash = _sha256(feed_path)
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise BoardingConeError("GTFS SHA-256 mismatch")
    counts = {name: 0 for name in (
        "calendar", "calendar_dates", "stops", "trips", "frequencies", "stop_times"
    )}
    points = _origin_points(origins, geometry_provider)
    try:
        with zipfile.ZipFile(feed_path) as archive:
            services = _active_services(archive, service_day, counts)
            candidate_stops, unparented_candidate_stops = _candidate_stops(
                archive, points, radius_m, counts
            )
            active_trips = {}
            seen_trips = set()
            for row in _rows(archive, "trips.txt", {"trip_id", "service_id"}):
                counts["trips"] += 1
                trip_id = row["trip_id"]
                if not trip_id or trip_id in seen_trips:
                    raise BoardingConeError("invalid trips.txt: missing or duplicate trip_id")
                seen_trips.add(trip_id)
                if row["service_id"] in services:
                    active_trips[trip_id] = row["service_id"]
            frequency_classes = {}
            for row in _rows(
                    archive,
                    "frequencies.txt",
                    {"trip_id", "start_time", "end_time", "headway_secs", "exact_times"},
                    optional=True,
            ) or ():
                counts["frequencies"] += 1
                exact_times = row["exact_times"] or "0"
                if exact_times not in {"0", "1"}:
                    raise BoardingConeError("invalid frequencies.txt: unsupported exact_times")
                if row["trip_id"] in active_trips:
                    frequency_classes.setdefault(row["trip_id"], set()).add(exact_times)

            exact_records = []
            frequency_records = {"0": [], "1": []}
            excluded_pickup = 0
            start, end = gtfs_seconds("06:30:00"), gtfs_seconds("08:30:00")
            required = {"trip_id", "departure_time", "stop_id", "stop_sequence"}
            for row in _rows(archive, "stop_times.txt", required):
                counts["stop_times"] += 1
                pickup = row.get("pickup_type", "") or "0"
                if pickup not in {"0", "1"}:
                    raise BoardingConeError(
                        f"unsupported pickup_type={pickup} at stop_times row {counts['stop_times']}"
                    )
                trip_id, stop_id = row["trip_id"], row["stop_id"]
                if trip_id not in active_trips or stop_id not in candidate_stops:
                    continue
                try:
                    departure_seconds = gtfs_seconds(row["departure_time"])
                    stop_sequence = int(row["stop_sequence"])
                except (TypeError, ValueError) as exc:
                    raise BoardingConeError(f"invalid scoped stop time for trip {trip_id}: {exc}") from exc
                if pickup == "1":
                    if frequency_classes.get(trip_id) or start <= departure_seconds <= end:
                        excluded_pickup += 1
                    continue
                stop = candidate_stops[stop_id]
                for origin in stop["origins"]:
                    record = {
                        **origin,
                        "source_stop_id": stop["source_stop_id"],
                        "parent_stop_id": stop["parent_stop_id"],
                        "stop_name": stop["stop_name"],
                        "stop_longitude": stop["stop_longitude"],
                        "stop_latitude": stop["stop_latitude"],
                        "trip_id": trip_id,
                        "service_id": active_trips[trip_id],
                        "stop_sequence": stop_sequence,
                        "departure_time": row["departure_time"],
                        "departure_seconds": departure_seconds,
                    }
                    classes = frequency_classes.get(trip_id)
                    if classes:
                        record["record_type"] = "template_only"
                        for exact_times in sorted(classes):
                            frequency_records[exact_times].append(record)
                    else:
                        if not start <= departure_seconds <= end:
                            continue
                        if row.get("timepoint") == "0":
                            raise BoardingConeError(f"inexact scoped stop time for trip {trip_id}")
                        exact_records.append(record)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BoardingConeError(f"unreadable GTFS archive: {exc}") from exc

    exact_records.sort(key=lambda row: (
        row["origin_id"], row["departure_seconds"], row["trip_id"],
        row["stop_sequence"], row["source_stop_id"]
    ))
    for records in frequency_records.values():
        records.sort(key=lambda row: (
            row["origin_id"], row["departure_seconds"], row["trip_id"],
            row["stop_sequence"], row["source_stop_id"]
        ))
    if frequency_records["0"]:
        status = "FREQUENCY_CANDIDATES_UNRESOLVED"
    elif frequency_records["1"]:
        status = "EXACT_FREQUENCY_EXPANSION_UNSUPPORTED"
    else:
        status = "EXACT_SCHEDULE_CANDIDATES_ENUMERATED"
    summary = {
        "status": status,
        "service_day": service_day.isoformat(),
        "timezone": "Europe/Zurich",
        "boarding_window_inclusive": ["06:30:00", "08:30:00"],
        "screening_only": True,
        "radius_m": radius_m,
        "source_sha256": source_hash,
        "active_service_count": len(services),
        "active_trip_count": len(active_trips),
        "candidate_stop_ids": sorted(candidate_stops),
        "unparented_candidate_stop_ids": unparented_candidate_stops,
        "exact_candidate_count": len(exact_records),
        "frequency_exact_times_0_candidate_count": len(frequency_records["0"]),
        "frequency_exact_times_1_candidate_count": len(frequency_records["1"]),
        "excluded_pickup_type_1_count": excluded_pickup,
        "scanned_counts": counts,
        "sample_records": exact_records[:sample_limit],
    }
    payload = {
        "summary": summary,
        "origins": [{key: value for key, value in point.items() if key != "geometry"} for point in points],
        "candidate_stops": [candidate_stops[key] for key in sorted(candidate_stops)],
        "candidate_records": exact_records,
        "frequency_exact_times_0_records": frequency_records["0"],
        "frequency_exact_times_1_records": frequency_records["1"],
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _real_origins(path, source_crs):
    source = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    municipalities = source["municipalities"]
    specifications = (
        ("staufen-near-inhabited-cell", "4210", "near_example_10th_closest_cell", "cell_centre_lv95"),
        ("niederlenz-population-weighted-centre", "4204", None, "population_weighted_centre_lv95"),
        ("lenzburg-population-weighted-centre", "4201", None, "population_weighted_centre_lv95"),
    )
    origins = []
    for origin_id, bfs, section, field in specifications:
        item = municipalities[bfs]
        coordinates = item[section][field] if section else item[field]
        origins.append({
            "origin_id": origin_id,
            "bfs_id": bfs,
            "source_crs": source_crs,
            "x": coordinates[0],
            "y": coordinates[1],
        })
    return origins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", required=True)
    parser.add_argument("--origins", required=True)
    parser.add_argument("--source-snapshot", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--expected-sha256", default=EXPECTED_GTFS_SHA256)
    args = parser.parse_args()
    snapshot = json.loads(pathlib.Path(args.source_snapshot).read_text(encoding="utf-8"))
    source_crs = snapshot["sources"]["statpop"]["coordinatesCrs"]
    origins = _real_origins(args.origins, source_crs)
    started = time.monotonic()
    summary = probe_feed(
        args.feed,
        DEFAULT_DAY,
        origins,
        args.result,
        expected_sha256=args.expected_sha256,
    )
    report = {
        **summary,
        "result_path": str(pathlib.Path(args.result).resolve()),
        "result_sha256": _sha256(args.result),
        "wall_seconds": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
