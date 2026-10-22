"""Stream bounded first-leg candidates into direct-positive Aarau hubs.

The output is a necessary cone for a later transfer-rule-aware solver.  It does
not establish that any transfer or municipality is eligible.
"""
import argparse
import bisect
import datetime as dt
import gzip
import hashlib
import json
import os
import pathlib
import resource
import shutil
import tempfile
import time
import zipfile

import gtfs_direct_cap as direct


EXPECTED_GTFS_SHA256 = direct.EXPECTED_GTFS_SHA256
EXPECTED_DIRECT_SHA256 = "0f373c32bf994f145e6b16d3ad5864017f41cb969ea7c67bc84235b9edbc9edb"
DEFAULT_DAY = direct.DEFAULT_DAY
WINDOW_START = direct.WINDOW_START
WINDOW_END = direct.WINDOW_END
CAP_SECONDS = direct.CAP_SECONDS
MAX_SAMPLE_LIMIT = 100
MAX_DIRECT_RESULT_BYTES = 4 * 1024 * 1024
MAX_GTFS_BYTES = 500 * 1024 * 1024
MAX_CANDIDATE_OUTPUT_COUNT = 100_000
COPY_CHUNK_BYTES = 1024 * 1024


class FeederConeError(ValueError):
    """The inputs cannot safely support the bounded feeder cone."""


def _sha256(path):
    return direct._sha256(path)


def _read_bounded(path, limit, label):
    try:
        with pathlib.Path(path).open("rb") as source:
            payload = source.read(limit + 1)
    except OSError as exc:
        raise FeederConeError(f"unreadable {label}: {exc}") from exc
    if len(payload) > limit:
        raise FeederConeError(f"{label} exceeds {limit // (1024 * 1024)} MiB cap")
    return payload


def _snapshot_feed(path):
    digest = hashlib.sha256()
    snapshot = tempfile.TemporaryFile(mode="w+b")
    total = 0
    try:
        with pathlib.Path(path).open("rb") as source:
            while chunk := source.read(COPY_CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_GTFS_BYTES:
                    raise FeederConeError("GTFS exceeds 500 MiB cap")
                digest.update(chunk)
                snapshot.write(chunk)
        snapshot.seek(0)
        return snapshot, digest.hexdigest()
    except OSError as exc:
        snapshot.close()
        raise FeederConeError(f"unreadable GTFS archive: {exc}") from exc
    except Exception:
        snapshot.close()
        raise


def _paths_alias(first, second):
    first = pathlib.Path(first)
    second = pathlib.Path(second)
    if first.resolve(strict=False) == second.resolve(strict=False):
        return True
    try:
        return first.exists() and second.exists() and os.path.samefile(first, second)
    except OSError:
        return False


def _validate_output_paths(feed_path, direct_result_path, result_path,
                           candidate_output_path):
    inputs = (feed_path, direct_result_path)
    if any(_paths_alias(result_path, source) for source in inputs):
        raise FeederConeError("report output must not alias an input")
    if candidate_output_path is not None:
        if (any(_paths_alias(candidate_output_path, source) for source in inputs) or
                _paths_alias(candidate_output_path, result_path)):
            raise FeederConeError("candidate output must not alias feed/direct/report")


class _CandidateStream:
    def __init__(self, target, manifest):
        self.target = pathlib.Path(target)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.NamedTemporaryFile(
            mode="w+b", dir=self.target.parent,
            prefix=f".{self.target.name}.", suffix=".tmp", delete=False)
        self.temporary_path = pathlib.Path(temporary.name)
        self.raw = temporary
        try:
            self.gzip = gzip.GzipFile(filename="", mode="wb", fileobj=temporary, mtime=0)
            self.count = 0
            self._write(manifest)
        except BaseException:
            self.abort()
            raise

    def _write(self, row):
        encoded = (json.dumps(row, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":")) + "\n").encode("utf-8")
        self.gzip.write(encoded)

    def write_candidate(self, candidate):
        if self.count >= MAX_CANDIDATE_OUTPUT_COUNT:
            self.abort()
            raise FeederConeError(
                f"candidate output count would exceed {MAX_CANDIDATE_OUTPUT_COUNT}")
        self._write({"kind": "candidate", **candidate})
        self.count += 1

    def finish(self):
        self._write({"candidate_count": self.count, "kind": "summary"})
        self.gzip.close()
        self.raw.close()

    def publish(self):
        os.replace(self.temporary_path, self.target)

    def abort(self):
        try:
            if hasattr(self, "gzip"):
                self.gzip.close()
        finally:
            self.raw.close()
            self.temporary_path.unlink(missing_ok=True)


def _load_direct_result(path, expected_hash, feed_hash, service_day):
    encoded = _read_bounded(path, MAX_DIRECT_RESULT_BYTES, "direct result (4 MiB)")
    observed_hash = hashlib.sha256(encoded).hexdigest()
    if expected_hash is not None and observed_hash != expected_hash:
        raise FeederConeError("direct result SHA-256 mismatch")
    try:
        payload = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FeederConeError(f"invalid direct result: {exc}") from exc
    if payload.get("source_sha256") != feed_hash:
        raise FeederConeError("direct result source SHA-256 mismatch")
    if payload.get("service_day") != service_day.isoformat():
        raise FeederConeError("direct result service day mismatch")
    journeys = payload.get("journeys")
    if not isinstance(journeys, list):
        raise FeederConeError("invalid direct result: journeys must be a list")
    downstream = {}
    required = ("boarding_stop_id", "boarding_seconds", "boarding_time",
                "arrival_seconds", "arrival_time", "trip_id")
    for row in journeys:
        if not isinstance(row, dict) or any(field not in row for field in required):
            raise FeederConeError("invalid direct result journey")
        hub = row["boarding_stop_id"]
        if (not isinstance(hub, str) or not hub or
                type(row["boarding_seconds"]) is not int or
                type(row["arrival_seconds"]) is not int or
                row["arrival_seconds"] < row["boarding_seconds"]):
            raise FeederConeError("invalid direct result journey clock")
        downstream.setdefault(hub, []).append({field: row[field] for field in required})
    if not downstream:
        raise FeederConeError("direct result contains no positive boarding hubs")
    for rows in downstream.values():
        rows.sort(key=lambda row: (
            row["boarding_seconds"], row["arrival_seconds"], row["trip_id"],
            row["boarding_time"], row["arrival_time"]
        ))
    return observed_hash, downstream


def _known_stops(archive, counts):
    known = set()
    for row in direct._rows(archive, "stops.txt", {"stop_id"}):
        counts["stops"] += 1
        stop_id = row["stop_id"]
        if not stop_id or stop_id in known:
            raise FeederConeError("invalid stops.txt: empty or duplicate stop_id")
        known.add(stop_id)
    return known


def build_feeder_cone(feed_path, direct_result_path, service_day, result_path,
                      *, expected_feed_sha256=None, expected_direct_sha256=None,
                      sample_limit=10, candidate_output_path=None):
    """Count candidates, retaining only a bounded deterministic evidence sample."""
    if not isinstance(service_day, dt.date):
        raise FeederConeError("service_day must be a date")
    if type(sample_limit) is not int or not 0 <= sample_limit <= MAX_SAMPLE_LIMIT:
        raise FeederConeError("sample_limit must be an integer from 0 to 100")
    feed_path = pathlib.Path(feed_path)
    direct_result_path = pathlib.Path(direct_result_path)
    result_path = pathlib.Path(result_path)
    candidate_output_path = (None if candidate_output_path is None else
                             pathlib.Path(candidate_output_path))
    _validate_output_paths(
        feed_path, direct_result_path, result_path, candidate_output_path)
    feed_snapshot, feed_hash = _snapshot_feed(feed_path)
    if expected_feed_sha256 is not None and feed_hash != expected_feed_sha256:
        feed_snapshot.close()
        raise FeederConeError("GTFS SHA-256 mismatch")
    try:
        direct_hash, downstream = _load_direct_result(
            direct_result_path, expected_direct_sha256, feed_hash, service_day)
    except Exception:
        feed_snapshot.close()
        raise
    hub_ids = set(downstream)

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
        "duplicate_sequence_trips": 0,
        "invalid_scoped_trips": 0,
    }
    excluded = {"pickup_type_1": 0, "drop_off_type_1": 0}
    try:
        with zipfile.ZipFile(feed_snapshot) as archive:
            known_stops = _known_stops(archive, counts)
            missing_hubs = sorted(hub_ids - known_stops)
            if missing_hubs:
                raise FeederConeError(f"direct-result hub absent from stops.txt: {missing_hubs[0]}")
            target_trips = direct._target_trips(archive, hub_ids, counts)
            trip_services = direct._trip_services(archive, target_trips, counts)
            active_services, provenance, removed_services = direct._active_selected_services(
                archive, service_day, set(trip_services.values()), counts)
            active_trips = {
                trip_id: service_id for trip_id, service_id in trip_services.items()
                if service_id in active_services
            }
            frequencies = direct._frequency_classes(archive, set(active_trips), counts)
            fixed_trips = set(active_trips) - set(frequencies)
            rows_by_trip = direct._selected_stop_times(
                archive, fixed_trips, known_stops, counts, unresolved)
    except direct.DirectCapError as exc:
        raise FeederConeError(str(exc)) from exc
    except (OSError, zipfile.BadZipFile) as exc:
        raise FeederConeError(f"unreadable GTFS archive: {exc}") from exc
    finally:
        feed_snapshot.close()

    unresolved_frequency_trips = []
    for trip_id, classes in sorted(frequencies.items()):
        for exact in sorted(classes):
            unresolved[f"frequency_exact_times_{exact}_trips"] += 1
            unresolved_frequency_trips.append({
                "exact_times": exact,
                "service_id": active_trips[trip_id],
                "trip_id": trip_id,
            })

    start = direct.gtfs_seconds(WINDOW_START)
    end = direct.gtfs_seconds(WINDOW_END)
    candidate_count = 0
    sample = []
    candidate_stream = None
    if candidate_output_path is not None:
        candidate_stream = _CandidateStream(candidate_output_path, {
            "direct_result_sha256": direct_hash,
            "kind": "manifest",
            "service_day": service_day.isoformat(),
            "source_sha256": feed_hash,
            "status": "necessary_only",
        })
    # Stable source-trip order is not event-time order. Downstream route consumers
    # must key/sort by exact first-boarding seconds, never infer chronology here.
    try:
        for trip_id, rows in sorted(rows_by_trip.items()):
            rows.sort(key=lambda row: (row["stop_sequence"], row["stop_id"]))
            if len({row["stop_sequence"] for row in rows}) != len(rows):
                unresolved["duplicate_sequence_trips"] += 1
                continue
            chronology_invalid = False
            previous_departure = None
            for row in rows:
                if (row["arrival_seconds"] > row["departure_seconds"] or
                        (previous_departure is not None and
                         row["arrival_seconds"] < previous_departure)):
                    chronology_invalid = True
                    break
                previous_departure = row["departure_seconds"]
            if chronology_invalid:
                unresolved["nonmonotonic_trip_time"] += 1
                continue
            for hub_index, hub_row in enumerate(rows):
                if hub_row["stop_id"] not in hub_ids:
                    continue
                if hub_row["drop_off_type"] == "1":
                    excluded["drop_off_type_1"] += 1
                    continue
                if hub_row["drop_off_type"] in {"2", "3"}:
                    continue
                for boarding in rows[:hub_index]:
                    if boarding["pickup_type"] == "1":
                        excluded["pickup_type_1"] += 1
                        continue
                    if boarding["pickup_type"] in {"2", "3"}:
                        continue
                    first_board = boarding["departure_seconds"]
                    if not start <= first_board <= end:
                        continue
                    for second in downstream[hub_row["stop_id"]]:
                        # Continuing aboard the same trip is already counted by
                        # the direct screen, not a two-vehicle feeder candidate.
                        if trip_id == second["trip_id"]:
                            continue
                        total = second["arrival_seconds"] - first_board
                        if (hub_row["arrival_seconds"] > second["boarding_seconds"] or
                                not 0 <= total <= CAP_SECONDS):
                            continue
                        candidate = {
                            "first_board_arrival_seconds": boarding["arrival_seconds"],
                            "first_board_arrival_time": boarding["arrival_time"],
                            "first_board_departure_time": boarding["departure_time"],
                            "first_board_pickup_type": boarding["pickup_type"],
                            "first_board_seconds": first_board,
                            "first_board_stop_id": boarding["stop_id"],
                            "first_board_stop_sequence": boarding["stop_sequence"],
                            "first_leg_trip_id": trip_id,
                            "hub_arrival_seconds": hub_row["arrival_seconds"],
                            "hub_arrival_time": hub_row["arrival_time"],
                            "hub_departure_seconds": hub_row["departure_seconds"],
                            "hub_departure_time": hub_row["departure_time"],
                            "hub_drop_off_type": hub_row["drop_off_type"],
                            "hub_stop_id": hub_row["stop_id"],
                            "hub_stop_sequence": hub_row["stop_sequence"],
                            "second_leg_arrival_seconds": second["arrival_seconds"],
                            "second_leg_arrival_time": second["arrival_time"],
                            "second_leg_boarding_seconds": second["boarding_seconds"],
                            "second_leg_boarding_time": second["boarding_time"],
                            "second_leg_trip_id": second["trip_id"],
                            "service_id": active_trips[trip_id],
                            "service_provenance": provenance[active_trips[trip_id]],
                            "total_transit_seconds": total,
                        }
                        if candidate_stream is not None:
                            candidate_stream.write_candidate(candidate)
                        candidate_count += 1
                        if sample_limit:
                            order = (
                                candidate["first_board_seconds"],
                                candidate["second_leg_arrival_seconds"],
                                candidate["first_leg_trip_id"],
                                candidate["first_board_stop_sequence"],
                                candidate["hub_stop_sequence"],
                                candidate["second_leg_trip_id"],
                                candidate["first_board_stop_id"],
                                candidate["hub_stop_id"],
                                candidate_count,
                            )
                            if len(sample) < sample_limit or order < sample[-1][0]:
                                bisect.insort(sample, (order, candidate))
                                if len(sample) > sample_limit:
                                    sample.pop()
    except Exception:
        if candidate_stream is not None:
            candidate_stream.abort()
        raise
    payload = {
        "boarding_window_inclusive": [WINDOW_START, WINDOW_END],
        "candidate_count": candidate_count,
        "cap_seconds_inclusive": CAP_SECONDS,
        "direct_result_sha256": direct_hash,
        "excluded_counts": excluded,
        "limitations": [
            "This is a necessary feeder cone, not proof of a feasible transfer.",
            "Transfer minima, same-parent walking, trip-specific rules, and linked trips remain unresolved.",
            "Absence from this cone is unknown, not proof of ineligibility.",
            "The owner approved the 2026-10-27 reference day; independent all-canton holiday review is incomplete.",
        ],
        "removed_service_count": len(removed_services),
        "sample_candidates": [candidate for _, candidate in sample],
        "scanned_counts": counts,
        "second_leg_hub_count": len(hub_ids),
        "second_leg_hub_ids": sorted(hub_ids),
        "service_day": service_day.isoformat(),
        "source_sha256": feed_hash,
        "status": ("FEEDER_CANDIDATES_WITH_UNRESOLVED_CLASSES"
                   if any(unresolved.values()) else "FEEDER_CANDIDATES_ENUMERATED"),
        "timezone": "Europe/Zurich",
        "unresolved_counts": unresolved,
        "unresolved_frequency_trips": unresolved_frequency_trips,
    }
    staged_report = None
    candidate_backup = None
    candidate_publication_started = False
    publication_complete = False
    rollback_complete = False
    try:
        if candidate_stream is not None:
            candidate_stream.finish()
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=result_path.parent,
                                         prefix=f".{result_path.name}.", suffix=".tmp", delete=False) as stage:
            staged_report = pathlib.Path(stage.name)
            stage.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        if candidate_stream is not None:
            if candidate_stream.target.exists():
                with tempfile.NamedTemporaryFile(dir=candidate_stream.target.parent,
                                                 prefix=f".{candidate_stream.target.name}.",
                                                 suffix=".tmp", delete=False) as backup:
                    candidate_backup = pathlib.Path(backup.name)
                shutil.copyfile(candidate_stream.target, candidate_backup)
            candidate_publication_started = True
            candidate_stream.publish()
        os.replace(staged_report, result_path)
        publication_complete = True
    except BaseException:
        try:
            if candidate_stream is not None and candidate_publication_started:
                if candidate_backup is not None:
                    os.replace(candidate_backup, candidate_stream.target)
                else:
                    candidate_stream.target.unlink(missing_ok=True)
                rollback_complete = True
        except BaseException as rollback_error:
            raise FeederConeError(
                f"candidate rollback failed; recovery backup retained: {candidate_backup}"
            ) from rollback_error
        finally:
            if candidate_stream is not None:
                candidate_stream.abort()
        raise
    finally:
        if staged_report is not None:
            staged_report.unlink(missing_ok=True)
        if candidate_backup is not None and (
            publication_complete or rollback_complete or not candidate_publication_started
        ):
            candidate_backup.unlink(missing_ok=True)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", required=True)
    parser.add_argument("--direct-result", required=True)
    parser.add_argument("--service-day", default=DEFAULT_DAY.isoformat())
    parser.add_argument("--result", required=True)
    parser.add_argument("--expected-feed-sha256", default=EXPECTED_GTFS_SHA256)
    parser.add_argument("--expected-direct-sha256", default=EXPECTED_DIRECT_SHA256)
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--candidate-output")
    args = parser.parse_args()
    try:
        day = dt.date.fromisoformat(args.service_day)
    except ValueError as exc:
        raise FeederConeError(f"invalid service day: {exc}") from exc
    started = time.monotonic()
    payload = build_feeder_cone(
        args.feed, args.direct_result, day, args.result,
        expected_feed_sha256=args.expected_feed_sha256,
        expected_direct_sha256=args.expected_direct_sha256,
        sample_limit=args.sample_limit,
        candidate_output_path=args.candidate_output,
    )
    print(json.dumps({
        "candidate_count": payload["candidate_count"],
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "result_path": str(pathlib.Path(args.result).resolve()),
        "result_sha256": _sha256(args.result),
        "scanned_counts": payload["scanned_counts"],
        "second_leg_hub_count": payload["second_leg_hub_count"],
        "source_sha256": payload["source_sha256"],
        "status": payload["status"],
        "unresolved_counts": payload["unresolved_counts"],
        "wall_seconds": time.monotonic() - started,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
