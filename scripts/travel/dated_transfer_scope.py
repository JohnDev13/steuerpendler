"""Resolve exact-day scope evidence for every frozen directed transfer rule.

This is a conservative applicability index, not a router.  It retains every
source rule and selector, distinguishes unknown custom service identifiers from
known inactive services, and keeps type-4 in-seat continuations separate from
walking/path feasibility.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import resource
import sqlite3
import tempfile
import time
import zipfile


SCHEMA_VERSION = 1
SCHEMA_ID = "steuerpendler.dated-transfer-scope.v1"
APPLICATION_ID = 0x53505453
GENERATOR_VERSION = "1"
ACTIVE_APPLICATION_ID = 0x53504154
TRANSFER_APPLICATION_ID = 0x53505452
ACTIVE_SCHEMA_VERSION = 1
TRANSFER_SCHEMA_VERSION = 1
TRANSFER_SCHEMA_ID = "steuerpendler.dated-directed-transfer-rules.v1"
COPY_CHUNK_BYTES = 1024 * 1024
MAX_GTFS_BYTES = 1_000_000_000
MAX_SQLITE_BYTES = 1_500_000_000
WEEKDAYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)
TRANSFER_COLUMNS = {
    "rule_id", "source_row_number", "from_stop_id", "to_stop_id",
    "from_route_id", "to_route_id", "from_trip_id", "to_trip_id",
    "transfer_type", "min_transfer_time", "service_id", "semantic_class",
    "selector_specificity", "scope_status", "service_date_applicability",
    "source_fields_json",
}


class DatedTransferScopeError(ValueError):
    """The transfer-rule date-scope artifact cannot be produced safely."""


def _sha256(path):
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _temporary_path(destination, marker=""):
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=f".{destination.name}.{marker}",
        suffix=".tmp", delete=False,
    )
    path = pathlib.Path(handle.name)
    handle.close()
    return path


def _snapshot(source_path, expected_sha256, destination, label, byte_limit):
    source_path = pathlib.Path(source_path)
    snapshot = _temporary_path(destination, f"{label}.snapshot.")
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with open(source_path, "rb") as source, open(snapshot, "wb") as output:
            while chunk := source.read(COPY_CHUNK_BYTES):
                byte_count += len(chunk)
                if byte_count > byte_limit:
                    raise DatedTransferScopeError(
                        f"{label} exceeds {byte_limit} byte limit")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise DatedTransferScopeError(f"{label} SHA-256 mismatch")
        return snapshot, actual, byte_count
    except OSError as exc:
        snapshot.unlink(missing_ok=True)
        raise DatedTransferScopeError(f"unreadable {label}: {exc}") from exc
    except BaseException:
        snapshot.unlink(missing_ok=True)
        raise


def _member(archive, name):
    members = [item for item in archive.infolist() if item.filename == name]
    if not members:
        raise DatedTransferScopeError(f"missing {name}")
    if len(members) != 1:
        raise DatedTransferScopeError(f"duplicate GTFS member: {name}")
    return members[0]


def _rows(archive, name, required):
    member = _member(archive, name)
    try:
        with archive.open(member) as raw, io.TextIOWrapper(
                raw, encoding="utf-8-sig", newline="") as text:
            reader = csv.DictReader(text, strict=True)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)):
                raise DatedTransferScopeError(f"invalid {name}: duplicate field")
            missing = required - set(fields)
            if missing:
                raise DatedTransferScopeError(
                    f"invalid {name}: missing field {sorted(missing)[0]}")
            for number, row in enumerate(reader, 2):
                if None in row:
                    raise DatedTransferScopeError(
                        f"invalid {name} row {number}: unexpected field")
                yield number, row
    except DatedTransferScopeError:
        raise
    except (csv.Error, UnicodeError, KeyError) as exc:
        raise DatedTransferScopeError(f"invalid {name}: {exc}") from exc


def _parse_gtfs_date(value, context):
    try:
        return dt.datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError) as exc:
        raise DatedTransferScopeError(f"invalid {context}") from exc


def _service_scope(archive, service_day):
    """Return exact-day active and all source-known GTFS service identifiers."""
    active = set()
    known = set()
    selected_weekday = WEEKDAYS[service_day.weekday()]
    required = {"service_id", "start_date", "end_date", *WEEKDAYS}
    for number, row in _rows(archive, "calendar.txt", required):
        service_id = row["service_id"]
        if not service_id:
            raise DatedTransferScopeError(
                f"empty service_id in calendar.txt row {number}")
        if service_id in known:
            raise DatedTransferScopeError(
                f"duplicate service in calendar.txt: {service_id}")
        known.add(service_id)
        if any(row[field] not in {"0", "1"} for field in WEEKDAYS):
            raise DatedTransferScopeError(
                f"invalid weekday metadata for service {service_id}")
        start = _parse_gtfs_date(
            row["start_date"], f"calendar date for service {service_id}")
        end = _parse_gtfs_date(
            row["end_date"], f"calendar date for service {service_id}")
        if start > end:
            raise DatedTransferScopeError(
                f"inverted calendar range for service {service_id}")
        if start <= service_day <= end and row[selected_weekday] == "1":
            active.add(service_id)

    exact_date = service_day.strftime("%Y%m%d")
    selected_exceptions = set()
    required = {"service_id", "date", "exception_type"}
    for number, row in _rows(archive, "calendar_dates.txt", required):
        service_id = row["service_id"]
        if not service_id:
            raise DatedTransferScopeError(
                f"empty service_id in calendar_dates.txt row {number}")
        known.add(service_id)
        _parse_gtfs_date(
            row["date"], f"calendar_dates date for service {service_id}")
        if row["exception_type"] not in {"1", "2"}:
            raise DatedTransferScopeError(
                f"invalid exception_type for service {service_id}")
        if row["date"] != exact_date:
            continue
        key = (service_id, row["date"])
        if key in selected_exceptions:
            raise DatedTransferScopeError(
                f"duplicate service/date in calendar_dates.txt: {service_id}")
        selected_exceptions.add(key)
        if row["exception_type"] == "1":
            active.add(service_id)
        else:
            active.discard(service_id)
    return active, known


def _open_readonly(path):
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)


def _metadata(database):
    try:
        return dict(database.execute("SELECT key, value FROM metadata"))
    except sqlite3.DatabaseError as exc:
        raise DatedTransferScopeError("invalid SQLite metadata table") from exc


def _validate_sqlite(database, *, label, application_id, schema_version):
    try:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DatedTransferScopeError(f"{label} integrity check failed")
        if database.execute("PRAGMA application_id").fetchone()[0] != application_id:
            raise DatedTransferScopeError(f"{label} application_id mismatch")
        if database.execute("PRAGMA user_version").fetchone()[0] != schema_version:
            raise DatedTransferScopeError(f"{label} schema version mismatch")
    except sqlite3.DatabaseError as exc:
        raise DatedTransferScopeError(f"invalid {label} SQLite") from exc


def _validate_sources(active_path, transfer_path, service_day, feed_sha256):
    active = _open_readonly(active_path)
    transfer = _open_readonly(transfer_path)
    try:
        _validate_sqlite(
            active, label="active-trip", application_id=ACTIVE_APPLICATION_ID,
            schema_version=ACTIVE_SCHEMA_VERSION,
        )
        _validate_sqlite(
            transfer, label="transfer-rule", application_id=TRANSFER_APPLICATION_ID,
            schema_version=TRANSFER_SCHEMA_VERSION,
        )
        active_metadata = _metadata(active)
        transfer_metadata = _metadata(transfer)
        expected_date = service_day.isoformat()
        if active_metadata.get("service_date") != expected_date:
            raise DatedTransferScopeError("active-trip service date mismatch")
        if transfer_metadata.get("service_date") != expected_date:
            raise DatedTransferScopeError("transfer-rule service date mismatch")
        if active_metadata.get("source_sha256") != feed_sha256:
            raise DatedTransferScopeError("active-trip GTFS source mismatch")
        if transfer_metadata.get("source_sha256") != feed_sha256:
            raise DatedTransferScopeError("transfer-rule GTFS source mismatch")
        if transfer_metadata.get("schema_id") != TRANSFER_SCHEMA_ID:
            raise DatedTransferScopeError("transfer-rule schema_id mismatch")

        active_columns = {
            row[1] for row in active.execute("PRAGMA table_info(trips)")
        }
        if active_columns != {"trip_id", "route_id", "service_id", "schedule_type"}:
            raise DatedTransferScopeError("active-trip schema mismatch")
        transfer_columns = {
            row[1] for row in transfer.execute("PRAGMA table_info(transfer_rules)")
        }
        if transfer_columns != TRANSFER_COLUMNS:
            raise DatedTransferScopeError("transfer-rule schema mismatch")
        invalid_semantics = transfer.execute("""
            SELECT semantic_class FROM transfer_rules
            WHERE semantic_class NOT IN ('timed', 'minimum_time', 'in_seat')
            LIMIT 1
        """).fetchone()
        if invalid_semantics:
            raise DatedTransferScopeError(
                f"unsupported semantic class: {invalid_semantics[0]!r}")
        invalid_types = transfer.execute("""
            SELECT transfer_type FROM transfer_rules
            WHERE transfer_type NOT IN (1, 2, 4) LIMIT 1
        """).fetchone()
        if invalid_types:
            raise DatedTransferScopeError(
                f"unsupported transfer type: {invalid_types[0]!r}")
        invalid_scope = transfer.execute("""
            SELECT scope_status, service_date_applicability FROM transfer_rules
            WHERE scope_status NOT IN ('resolved', 'unresolved')
               OR service_date_applicability NOT IN (
                    'unrestricted_by_service_id', 'unknown_custom_service_id')
            LIMIT 1
        """).fetchone()
        if invalid_scope:
            raise DatedTransferScopeError("unsupported source scope class")
    finally:
        active.close()
        transfer.close()


def _create_database(path):
    database = sqlite3.connect(path)
    database.execute("PRAGMA page_size = 4096")
    database.execute("PRAGMA journal_mode = DELETE")
    database.execute("PRAGMA synchronous = FULL")
    database.execute("PRAGMA temp_store = FILE")
    database.execute("PRAGMA cache_size = -131072")
    database.execute("PRAGMA auto_vacuum = NONE")
    database.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    database.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    database.executescript("""
        CREATE TABLE transfer_scope (
            rule_id INTEGER PRIMARY KEY,
            source_rule_id INTEGER NOT NULL UNIQUE,
            source_row_number INTEGER NOT NULL UNIQUE,
            from_stop_id TEXT NOT NULL,
            to_stop_id TEXT NOT NULL,
            from_route_id TEXT NOT NULL,
            to_route_id TEXT NOT NULL,
            from_trip_id TEXT NOT NULL,
            to_trip_id TEXT NOT NULL,
            transfer_type INTEGER NOT NULL CHECK (transfer_type IN (1, 2, 4)),
            min_transfer_time INTEGER CHECK (min_transfer_time >= 0),
            service_id TEXT NOT NULL,
            semantic_class TEXT NOT NULL CHECK (
                semantic_class IN ('timed', 'minimum_time', 'in_seat')),
            selector_specificity INTEGER NOT NULL,
            source_scope_status TEXT NOT NULL,
            source_service_date_applicability TEXT NOT NULL,
            service_date_applicability TEXT NOT NULL CHECK (
                service_date_applicability IN (
                    'unrestricted', 'active', 'known_inactive', 'unknown')),
            from_trip_status TEXT NOT NULL CHECK (
                from_trip_status IN ('not_selected', 'active', 'not_active')),
            to_trip_status TEXT NOT NULL CHECK (
                to_trip_status IN ('not_selected', 'active', 'not_active')),
            from_route_status TEXT NOT NULL CHECK (
                from_route_status IN (
                    'not_selected', 'selector_unresolved', 'matches_active_trip',
                    'conflicts_active_trip', 'trip_not_active')),
            to_route_status TEXT NOT NULL CHECK (
                to_route_status IN (
                    'not_selected', 'selector_unresolved', 'matches_active_trip',
                    'conflicts_active_trip', 'trip_not_active')),
            applicability_status TEXT NOT NULL CHECK (
                applicability_status IN (
                    'potentially_applicable', 'in_seat_candidate_unvalidated',
                    'inactive_service', 'inactive_trip', 'unresolved_service',
                    'unresolved_route_conflict')),
            reason TEXT NOT NULL,
            source_fields_json TEXT NOT NULL,
            CHECK ((transfer_type = 2) = (min_transfer_time IS NOT NULL))
        );
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TEMP TABLE active_services (service_id TEXT PRIMARY KEY) WITHOUT ROWID;
        CREATE TEMP TABLE known_services (service_id TEXT PRIMARY KEY) WITHOUT ROWID;
    """)
    return database


def _trip_status(alias):
    return (
        f"CASE WHEN s.{alias}_trip_id='' THEN 'not_selected' "
        f"WHEN a_{alias}.trip_id IS NOT NULL THEN 'active' ELSE 'not_active' END"
    )


def _route_status(alias):
    return (
        f"CASE WHEN s.{alias}_route_id='' THEN 'not_selected' "
        f"WHEN s.{alias}_trip_id='' THEN 'selector_unresolved' "
        f"WHEN a_{alias}.trip_id IS NULL THEN 'trip_not_active' "
        f"WHEN a_{alias}.route_id=s.{alias}_route_id THEN 'matches_active_trip' "
        f"ELSE 'conflicts_active_trip' END"
    )


def _populate(database, active_path, transfer_path, active_services, known_services):
    database.executemany(
        "INSERT INTO active_services VALUES (?)", ((item,) for item in sorted(active_services)))
    database.executemany(
        "INSERT INTO known_services VALUES (?)", ((item,) for item in sorted(known_services)))
    database.execute("ATTACH DATABASE ? AS active", (str(active_path),))
    database.execute("ATTACH DATABASE ? AS source", (str(transfer_path),))
    trip_from = _trip_status("from")
    trip_to = _trip_status("to")
    route_from = _route_status("from")
    route_to = _route_status("to")
    service = """CASE
        WHEN s.service_id='' THEN 'unrestricted'
        WHEN day.service_id IS NOT NULL THEN 'active'
        WHEN known.service_id IS NOT NULL THEN 'known_inactive'
        ELSE 'unknown' END"""
    route_conflict = """(
        (s.from_route_id<>'' AND a_from.trip_id IS NOT NULL
         AND a_from.route_id<>s.from_route_id)
        OR
        (s.to_route_id<>'' AND a_to.trip_id IS NOT NULL
         AND a_to.route_id<>s.to_route_id)
    )"""
    inactive_trip = """(
        (s.from_trip_id<>'' AND a_from.trip_id IS NULL)
        OR (s.to_trip_id<>'' AND a_to.trip_id IS NULL)
    )"""
    status = f"""CASE
        WHEN ({service})='unknown' THEN 'unresolved_service'
        WHEN ({service})='known_inactive' THEN 'inactive_service'
        WHEN {inactive_trip} THEN 'inactive_trip'
        WHEN {route_conflict} THEN 'unresolved_route_conflict'
        WHEN s.transfer_type=4 THEN 'in_seat_candidate_unvalidated'
        ELSE 'potentially_applicable' END"""
    reason = f"""CASE
        WHEN ({service})='unknown' THEN
            'custom service_id is never listed in GTFS calendar sources'
        WHEN ({service})='known_inactive' THEN
            'custom service_id is known but inactive on the service date'
        WHEN {inactive_trip} THEN
            'one or both selected trips are absent from the active-trip index'
        WHEN {route_conflict} THEN
            'route selector conflicts with active-trip route; applicability remains unresolved'
        WHEN s.transfer_type=4 THEN
            'in-seat same-vehicle candidate only; stop, timing, selector, minimum and wait checks remain for the router'
        WHEN s.transfer_type=1 THEN
            'timed transfer remains potentially applicable; router checks are still required'
        ELSE
            'minimum-time transfer remains potentially applicable; router checks are still required'
        END"""
    database.execute(f"""
        INSERT INTO transfer_scope
        SELECT
            s.rule_id, s.rule_id, s.source_row_number,
            s.from_stop_id, s.to_stop_id, s.from_route_id, s.to_route_id,
            s.from_trip_id, s.to_trip_id, s.transfer_type, s.min_transfer_time,
            s.service_id, s.semantic_class, s.selector_specificity,
            s.scope_status, s.service_date_applicability,
            {service}, {trip_from}, {trip_to}, {route_from}, {route_to},
            {status}, {reason}, s.source_fields_json
        FROM source.transfer_rules AS s
        LEFT JOIN active.trips AS a_from ON a_from.trip_id=s.from_trip_id
        LEFT JOIN active.trips AS a_to ON a_to.trip_id=s.to_trip_id
        LEFT JOIN active_services AS day ON day.service_id=s.service_id
        LEFT JOIN known_services AS known ON known.service_id=s.service_id
        ORDER BY s.rule_id
    """)
    database.commit()
    database.execute("DETACH DATABASE source")
    database.execute("DETACH DATABASE active")


def _counts(database):
    counts = {
        "source_rows": database.execute("SELECT COUNT(*) FROM transfer_scope").fetchone()[0],
        "in_seat_both_trips_active_service_active": database.execute("""
            SELECT COUNT(*) FROM transfer_scope
            WHERE transfer_type=4 AND service_date_applicability='active'
              AND from_trip_status='active' AND to_trip_status='active'
        """).fetchone()[0],
        "in_seat_distinct_active_custom_services": database.execute("""
            SELECT COUNT(DISTINCT service_id) FROM transfer_scope
            WHERE transfer_type=4 AND service_date_applicability='active'
              AND from_trip_status='active' AND to_trip_status='active'
        """).fetchone()[0],
        "timed_both_trips_active": database.execute("""
            SELECT COUNT(*) FROM transfer_scope
            WHERE transfer_type=1
              AND from_trip_status='active' AND to_trip_status='active'
        """).fetchone()[0],
    }
    for status, count in database.execute(
            "SELECT applicability_status, COUNT(*) FROM transfer_scope GROUP BY applicability_status"):
        counts[f"status.{status}"] = count
    for status, count in database.execute(
            "SELECT service_date_applicability, COUNT(*) FROM transfer_scope GROUP BY service_date_applicability"):
        counts[f"service.{status}"] = count
    return counts


def _check_expected(counts, expected_in_seat_candidates, expected_timed_trip_pairs):
    if (expected_in_seat_candidates is not None
            and counts["in_seat_both_trips_active_service_active"]
            != expected_in_seat_candidates):
        raise DatedTransferScopeError(
            "in-seat candidate count mismatch: expected "
            f"{expected_in_seat_candidates}, got "
            f"{counts['in_seat_both_trips_active_service_active']}")
    if (expected_timed_trip_pairs is not None
            and counts["timed_both_trips_active"] != expected_timed_trip_pairs):
        raise DatedTransferScopeError(
            "timed trip-pair count mismatch: expected "
            f"{expected_timed_trip_pairs}, got {counts['timed_both_trips_active']}")


def _finalize(database, metadata):
    database.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)", sorted(metadata.items()))
    database.executescript("""
        CREATE INDEX transfer_scope_from_stop_idx ON transfer_scope(
            from_stop_id, to_stop_id, selector_specificity DESC, source_row_number);
        CREATE INDEX transfer_scope_to_stop_idx ON transfer_scope(
            to_stop_id, from_stop_id, selector_specificity DESC, source_row_number);
        CREATE INDEX transfer_scope_from_trip_idx ON transfer_scope(
            from_trip_id, to_trip_id, source_row_number);
        CREATE INDEX transfer_scope_to_trip_idx ON transfer_scope(
            to_trip_id, from_trip_id, source_row_number);
        CREATE INDEX transfer_scope_status_idx ON transfer_scope(
            applicability_status, transfer_type, source_row_number);
        CREATE INDEX transfer_scope_service_idx ON transfer_scope(
            service_id, service_date_applicability, source_row_number);
    """)
    database.commit()
    database.execute("VACUUM")
    if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise DatedTransferScopeError("output SQLite integrity check failed")


def _write_manifest(path, payload):
    temporary = _temporary_path(path)
    data = (json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    try:
        with open(temporary, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _backup(path):
    if not path.exists():
        return None
    backup = _temporary_path(path, "backup.")
    backup.unlink()
    try:
        os.link(path, backup)
        return backup
    except BaseException:
        backup.unlink(missing_ok=True)
        raise


def _publish_pair(database_temporary, output_path, manifest_temporary, manifest_path):
    database_backup = _backup(output_path)
    try:
        manifest_backup = _backup(manifest_path)
    except BaseException:
        if database_backup is not None:
            database_backup.unlink(missing_ok=True)
        raise
    database_published = manifest_published = False
    try:
        os.replace(database_temporary, output_path)
        database_published = True
        os.replace(manifest_temporary, manifest_path)
        manifest_published = True
        directory_fd = os.open(output_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        if manifest_published:
            if manifest_backup is None:
                manifest_path.unlink(missing_ok=True)
            else:
                os.replace(manifest_backup, manifest_path)
                manifest_backup = None
        if database_published:
            if database_backup is None:
                output_path.unlink(missing_ok=True)
            else:
                os.replace(database_backup, output_path)
                database_backup = None
        raise
    finally:
        database_temporary.unlink(missing_ok=True)
        manifest_temporary.unlink(missing_ok=True)
        if database_backup is not None:
            database_backup.unlink(missing_ok=True)
        if manifest_backup is not None:
            manifest_backup.unlink(missing_ok=True)


def build_dated_transfer_scope(
        feed_path, expected_feed_sha256, active_trip_path,
        expected_active_trip_sha256, transfer_rule_path,
        expected_transfer_rule_sha256, service_day, output_path, *,
        expected_in_seat_candidates=None, expected_timed_trip_pairs=None):
    """Build an atomic, deterministic conservative scope index and manifest."""
    if not isinstance(service_day, dt.date) or isinstance(service_day, dt.datetime):
        raise DatedTransferScopeError("service_day must be a date")
    output_path = pathlib.Path(output_path)
    manifest_path = pathlib.Path(f"{output_path}.manifest.json")
    snapshots = []
    database_path = manifest_temporary = None
    database = None
    try:
        feed_snapshot, feed_sha256, feed_bytes = _snapshot(
            feed_path, expected_feed_sha256, output_path, "GTFS ZIP", MAX_GTFS_BYTES)
        snapshots.append(feed_snapshot)
        active_snapshot, active_sha256, active_bytes = _snapshot(
            active_trip_path, expected_active_trip_sha256, output_path,
            "active-trip SQLite", MAX_SQLITE_BYTES)
        snapshots.append(active_snapshot)
        transfer_snapshot, transfer_sha256, transfer_bytes = _snapshot(
            transfer_rule_path, expected_transfer_rule_sha256, output_path,
            "transfer-rule SQLite", MAX_SQLITE_BYTES)
        snapshots.append(transfer_snapshot)

        try:
            with zipfile.ZipFile(feed_snapshot) as archive:
                active_services, known_services = _service_scope(archive, service_day)
        except (OSError, zipfile.BadZipFile) as exc:
            raise DatedTransferScopeError(f"unreadable GTFS ZIP: {exc}") from exc
        _validate_sources(
            active_snapshot, transfer_snapshot, service_day, feed_sha256)

        database_path = _temporary_path(output_path)
        database = _create_database(database_path)
        _populate(
            database, active_snapshot, transfer_snapshot,
            active_services, known_services)
        counts = _counts(database)
        _check_expected(
            counts, expected_in_seat_candidates, expected_timed_trip_pairs)
        metadata = {
            "generator_version": GENERATOR_VERSION,
            "schema_id": SCHEMA_ID,
            "schema_version": str(SCHEMA_VERSION),
            "service_date": service_day.isoformat(),
            "source.active_trip_sha256": active_sha256,
            "source.gtfs_sha256": feed_sha256,
            "source.transfer_rule_sha256": transfer_sha256,
            **{f"count.{key}": str(value) for key, value in counts.items()},
        }
        _finalize(database, metadata)
        database.close()
        database = None
        manifest = {
            "counts": counts,
            "format": "sqlite3",
            "generator_version": GENERATOR_VERSION,
            "limitations": [
                "This is source-day applicability evidence, not a journey or route claim.",
                "Potential applicability still requires stop, timing, selector, minimum-time and wait checks in the router.",
                "Type 4 is an in-seat same-vehicle continuation, not a walking transfer.",
                "Unknown custom services and route conflicts remain unresolved; absent evidence is not a negative route claim.",
            ],
            "output_bytes": database_path.stat().st_size,
            "output_sha256": _sha256(database_path),
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "service_counts": {"active": len(active_services), "known": len(known_services)},
            "service_date": service_day.isoformat(),
            "source_bytes": {
                "active_trip_sqlite": active_bytes,
                "gtfs_zip": feed_bytes,
                "transfer_rule_sqlite": transfer_bytes,
            },
            "source_sha256": {
                "active_trip_sqlite": active_sha256,
                "gtfs_zip": feed_sha256,
                "transfer_rule_sqlite": transfer_sha256,
            },
        }
        manifest_temporary = _write_manifest(manifest_path, manifest)
        _publish_pair(database_path, output_path, manifest_temporary, manifest_path)
        database_path = manifest_temporary = None
        return manifest
    except BaseException:
        if database is not None:
            database.close()
        if database_path is not None:
            database_path.unlink(missing_ok=True)
            pathlib.Path(f"{database_path}-journal").unlink(missing_ok=True)
        if manifest_temporary is not None:
            manifest_temporary.unlink(missing_ok=True)
        raise
    finally:
        for snapshot in snapshots:
            snapshot.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", required=True)
    parser.add_argument("--expected-feed-sha256", required=True)
    parser.add_argument("--active-trips", required=True)
    parser.add_argument("--expected-active-trip-sha256", required=True)
    parser.add_argument("--transfer-rules", required=True)
    parser.add_argument("--expected-transfer-rule-sha256", required=True)
    parser.add_argument("--service-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-in-seat-candidates", type=int)
    parser.add_argument("--expected-timed-trip-pairs", type=int)
    args = parser.parse_args()
    try:
        service_day = dt.date.fromisoformat(args.service_date)
    except ValueError as exc:
        raise DatedTransferScopeError(f"invalid service date: {exc}") from exc
    started = time.monotonic()
    manifest = build_dated_transfer_scope(
        args.feed, args.expected_feed_sha256,
        args.active_trips, args.expected_active_trip_sha256,
        args.transfer_rules, args.expected_transfer_rule_sha256,
        service_day, args.output,
        expected_in_seat_candidates=args.expected_in_seat_candidates,
        expected_timed_trip_pairs=args.expected_timed_trip_pairs,
    )
    print(json.dumps({
        **manifest,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "wall_seconds": time.monotonic() - started,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
