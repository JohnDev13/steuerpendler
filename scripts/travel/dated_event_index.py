"""Build a hash-pinned disk-backed index of dated active GTFS stop calls.

The input GTFS and Phase A active-trip database are privately snapshotted and
hashed before parsing. ``stop_times.txt`` is streamed; only the bounded active
trip map and validation counters live in memory. Frequency rows remain template
clocks and are never represented as scheduled departures.
"""
import argparse
import csv
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
SCHEMA_ID = 'steuerpendler.dated-active-stop-calls.v1'
GENERATOR_VERSION = '1'
MAX_GTFS_BYTES = 1_000_000_000
MAX_ACTIVE_DATABASE_BYTES = 1_000_000_000
COPY_CHUNK_BYTES = 1024 * 1024
SCHEDULE_TYPES = {
    'fixed_scheduled',
    'frequency_template_exact_times_0',
    'frequency_template_exact_times_1',
}


class DatedEventIndexError(ValueError):
    """The dated active stop-call artifact cannot be produced safely."""


def _sha256(path):
    with open(path, 'rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _snapshot(path, expected_sha256, byte_limit, label):
    path = pathlib.Path(path)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f'.{path.name}.snapshot.',
        suffix='.tmp', delete=False)
    snapshot = pathlib.Path(handle.name)
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with handle, open(path, 'rb') as source:
            while chunk := source.read(COPY_CHUNK_BYTES):
                byte_count += len(chunk)
                if byte_count > byte_limit:
                    raise DatedEventIndexError(
                        f'{label} exceeds {byte_limit} byte limit')
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != expected_sha256:
            raise DatedEventIndexError(f'{label} SHA-256 mismatch')
        return snapshot, actual_sha256, byte_count
    except OSError as exc:
        snapshot.unlink(missing_ok=True)
        raise DatedEventIndexError(f'unreadable {label}: {exc}') from exc
    except BaseException:
        snapshot.unlink(missing_ok=True)
        raise


def _readonly_database(path):
    uri = pathlib.Path(path).resolve().as_uri() + '?mode=ro&immutable=1'
    return sqlite3.connect(uri, uri=True)


def _load_active_trips(path, expected_service_date, expected_source_sha256):
    try:
        database = _readonly_database(path)
        try:
            if database.execute('PRAGMA application_id').fetchone()[0] != 0x53504154:
                raise DatedEventIndexError('invalid active-trip application_id')
            if database.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise DatedEventIndexError('unsupported active-trip schema version')
            if database.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise DatedEventIndexError('active-trip SQLite integrity check failed')
            metadata = dict(database.execute('SELECT key, value FROM metadata'))
            required = {'schema_version', 'service_date', 'source_sha256'}
            missing = required - set(metadata)
            if missing:
                raise DatedEventIndexError(
                    f'active-trip metadata missing {sorted(missing)[0]}')
            if metadata['schema_version'] != '1':
                raise DatedEventIndexError('unsupported active-trip metadata schema')
            if (expected_service_date is not None
                    and metadata['service_date'] != expected_service_date):
                raise DatedEventIndexError('active-trip service date mismatch')
            if metadata['source_sha256'] != expected_source_sha256:
                raise DatedEventIndexError('active-trip GTFS source mismatch')
            trips = {}
            for trip_id, route_id, service_id, schedule_type in database.execute(
                    'SELECT trip_id, route_id, service_id, schedule_type FROM trips'):
                if (not trip_id or not route_id or not service_id
                        or schedule_type not in SCHEDULE_TYPES):
                    raise DatedEventIndexError(
                        f'invalid schedule_type or trip metadata for {trip_id!r}')
                if trip_id in trips:
                    raise DatedEventIndexError(
                        f'duplicate trip in active-trip database: {trip_id}')
                trips[trip_id] = (route_id, service_id, schedule_type)
        finally:
            database.close()
    except DatedEventIndexError:
        raise
    except (OSError, sqlite3.DatabaseError) as exc:
        raise DatedEventIndexError(
            f'invalid active-trip SQLite database: {exc}') from exc
    if not trips:
        raise DatedEventIndexError('active-trip database is empty')
    return trips, metadata


def _rows(archive, name, required_fields):
    member_count = sum(member.filename == name for member in archive.infolist())
    if member_count == 0:
        raise DatedEventIndexError(f'missing {name}')
    if member_count > 1:
        raise DatedEventIndexError(f'duplicate member in GTFS archive: {name}')
    try:
        with archive.open(name) as raw, io.TextIOWrapper(
                raw, encoding='utf-8-sig', newline='') as text:
            reader = csv.DictReader(text, strict=True)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)):
                raise DatedEventIndexError(f'invalid {name}: duplicate field')
            missing = required_fields - set(fields)
            if missing:
                raise DatedEventIndexError(
                    f'invalid {name}: missing field {sorted(missing)[0]}')
            for source_row_number, row in enumerate(reader, 2):
                if None in row:
                    raise DatedEventIndexError(
                        f'invalid {name} row {source_row_number}: unexpected field')
                yield source_row_number, row
    except DatedEventIndexError:
        raise
    except (csv.Error, UnicodeError, KeyError) as exc:
        raise DatedEventIndexError(f'invalid {name}: {exc}') from exc


def _gtfs_seconds(value, field, trip_id, source_row_number, *, allow_empty):
    if value == '' and allow_empty:
        return None
    try:
        parts = value.split(':')
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise ValueError
        hours, minutes, seconds = map(int, parts)
        total = hours * 3600 + minutes * 60 + seconds
        if (hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60
                or total > 2_147_483_647):
            raise ValueError
        return total
    except (AttributeError, TypeError, ValueError) as exc:
        raise DatedEventIndexError(
            f'invalid {field} for active trip {trip_id} '
            f'at stop_times.txt row {source_row_number}') from exc


def _integer(value, field, trip_id, source_row_number):
    try:
        if not value or not value.isdigit():
            raise ValueError
        parsed = int(value)
        if parsed > 2_147_483_647:
            raise ValueError
        return parsed
    except (AttributeError, TypeError, ValueError) as exc:
        raise DatedEventIndexError(
            f'invalid {field} for active trip {trip_id} '
            f'at stop_times.txt row {source_row_number}') from exc


def _enum(value, default, allowed, field, trip_id, source_row_number):
    normalized = value or default
    if normalized not in allowed:
        raise DatedEventIndexError(
            f'invalid {field} for active trip {trip_id} '
            f'at stop_times.txt row {source_row_number}')
    return int(normalized)


def _create_database(path):
    database = sqlite3.connect(path)
    database.execute('PRAGMA page_size = 4096')
    database.execute('PRAGMA journal_mode = DELETE')
    database.execute('PRAGMA synchronous = FULL')
    database.execute('PRAGMA temp_store = FILE')
    database.execute('PRAGMA auto_vacuum = NONE')
    database.execute('PRAGMA application_id = 0x53504556')
    database.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
    database.executescript('''
        CREATE TABLE stop_calls (
            trip_id TEXT NOT NULL,
            stop_sequence INTEGER NOT NULL CHECK (stop_sequence >= 0),
            source_row_number INTEGER NOT NULL UNIQUE CHECK (source_row_number >= 2),
            arrival_seconds INTEGER,
            departure_seconds INTEGER,
            stop_id TEXT NOT NULL,
            pickup_type INTEGER NOT NULL CHECK (pickup_type BETWEEN 0 AND 3),
            drop_off_type INTEGER NOT NULL CHECK (drop_off_type BETWEEN 0 AND 3),
            timepoint INTEGER NOT NULL CHECK (timepoint IN (0, 1)),
            event_time_status TEXT NOT NULL CHECK (event_time_status IN (
                'exact', 'non_exact', 'frequency_template'
            )),
            route_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            schedule_type TEXT NOT NULL CHECK (schedule_type IN (
                'fixed_scheduled',
                'frequency_template_exact_times_0',
                'frequency_template_exact_times_1'
            )),
            PRIMARY KEY (trip_id, stop_sequence)
        ) WITHOUT ROWID;
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;
    ''')
    return database


def _stream_stop_calls(archive, database, active_trips, counts):
    trip_call_counts = {trip_id: 0 for trip_id in active_trips}
    required = {
        'trip_id', 'arrival_time', 'departure_time', 'stop_id', 'stop_sequence',
    }
    insert = '''
        INSERT INTO stop_calls (
            trip_id, stop_sequence, source_row_number, arrival_seconds,
            departure_seconds, stop_id, pickup_type, drop_off_type, timepoint,
            event_time_status, route_id, service_id, schedule_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    for source_row_number, row in _rows(archive, 'stop_times.txt', required):
        counts['source_stop_time_rows'] += 1
        trip_id = row['trip_id']
        if not trip_id:
            raise DatedEventIndexError(
                f'empty trip_id at stop_times.txt row {source_row_number}')
        trip = active_trips.get(trip_id)
        if trip is None:
            continue
        route_id, service_id, schedule_type = trip
        sequence = _integer(
            row['stop_sequence'], 'stop_sequence', trip_id, source_row_number)
        stop_id = row['stop_id']
        if not stop_id:
            raise DatedEventIndexError(
                f'empty stop_id for active trip {trip_id} '
                f'at stop_times.txt row {source_row_number}')
        pickup = _enum(
            row.get('pickup_type', ''), '0', {'0', '1', '2', '3'},
            'pickup_type', trip_id, source_row_number)
        drop_off = _enum(
            row.get('drop_off_type', ''), '0', {'0', '1', '2', '3'},
            'drop_off_type', trip_id, source_row_number)
        timepoint = _enum(
            row.get('timepoint', ''), '1', {'0', '1'},
            'timepoint', trip_id, source_row_number)
        arrival = _gtfs_seconds(
            row['arrival_time'], 'arrival_time', trip_id, source_row_number,
            allow_empty=True)
        departure = _gtfs_seconds(
            row['departure_time'], 'departure_time', trip_id, source_row_number,
            allow_empty=True)
        if timepoint == 1 and (arrival is None or departure is None):
            raise DatedEventIndexError(
                f'exact stop call has missing time for active trip {trip_id} '
                f'at stop_times.txt row {source_row_number}')
        if arrival is not None and departure is not None and arrival > departure:
            raise DatedEventIndexError(
                f'arrival after departure for active trip {trip_id} '
                f'at stop_times.txt row {source_row_number}')
        if schedule_type.startswith('frequency_template_'):
            event_time_status = 'frequency_template'
            counts['frequency_template_stop_calls'] += 1
        elif timepoint == 0:
            event_time_status = 'non_exact'
            counts['non_exact_stop_calls'] += 1
        else:
            event_time_status = 'exact'
            counts['exact_stop_calls'] += 1
        try:
            database.execute(insert, (
                trip_id, sequence, source_row_number, arrival, departure, stop_id,
                pickup, drop_off, timepoint, event_time_status, route_id,
                service_id, schedule_type))
        except sqlite3.IntegrityError as exc:
            if ('stop_calls.trip_id, stop_calls.stop_sequence' in str(exc)
                    or 'trip_id, stop_sequence' in str(exc)):
                raise DatedEventIndexError(
                    f'duplicate stop_sequence for active trip {trip_id}') from exc
            raise DatedEventIndexError(
                f'invalid active stop call for trip {trip_id}: {exc}') from exc
        trip_call_counts[trip_id] += 1
        counts['active_stop_calls'] += 1
        if schedule_type == 'fixed_scheduled':
            counts['fixed_scheduled_stop_calls'] += 1

    for trip_id, call_count in trip_call_counts.items():
        if call_count < 2:
            raise DatedEventIndexError(
                f'active trip has fewer than two stop calls: {trip_id}')
    counts['active_trips_with_stop_calls'] = sum(
        count > 0 for count in trip_call_counts.values())


def _validate_chronology(database):
    current_trip = None
    prior_known = None
    for (trip_id, source_row_number, arrival, departure) in database.execute('''
            SELECT trip_id, source_row_number, arrival_seconds, departure_seconds
            FROM stop_calls ORDER BY trip_id, stop_sequence
            '''):
        if trip_id != current_trip:
            current_trip = trip_id
            prior_known = None
        current_known = arrival if arrival is not None else departure
        if (prior_known is not None and current_known is not None
                and current_known < prior_known):
            raise DatedEventIndexError(
                f'nonmonotonic chronology for active trip {trip_id} '
                f'at stop_times.txt row {source_row_number}')
        if departure is not None:
            prior_known = departure
        elif arrival is not None:
            prior_known = arrival


def _check_expected(counts, expected_source_rows, expected_active_stop_calls,
                    expected_active_trips):
    checks = (
        ('source stop-time', expected_source_rows,
         counts['source_stop_time_rows']),
        ('active stop-call', expected_active_stop_calls,
         counts['active_stop_calls']),
        ('active trip', expected_active_trips, counts['active_trips']),
    )
    for label, expected, actual in checks:
        if expected is not None and expected != actual:
            raise DatedEventIndexError(
                f'{label} count mismatch: expected {expected}, got {actual}')


def _temporary_path(destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=f'.{destination.name}.',
        suffix='.tmp', delete=False)
    path = pathlib.Path(handle.name)
    handle.close()
    return path


def _write_manifest(path, payload):
    data = (json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')) + '\n').encode('utf-8')
    temporary = _temporary_path(path)
    try:
        with open(temporary, 'wb') as output:
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
    backup = _temporary_path(path)
    backup.unlink()
    try:
        os.link(path, backup)
        return backup
    except BaseException:
        backup.unlink(missing_ok=True)
        raise


def _publish_pair(database_temporary, output_path,
                  manifest_temporary, manifest_path):
    database_backup = _backup(output_path)
    try:
        manifest_backup = _backup(manifest_path)
    except BaseException:
        if database_backup is not None:
            database_backup.unlink(missing_ok=True)
        raise
    database_published = False
    manifest_published = False
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
        if database_backup is not None:
            database_backup.unlink(missing_ok=True)
        if manifest_backup is not None:
            manifest_backup.unlink(missing_ok=True)


def build_dated_event_index(
        feed_path, expected_feed_sha256, active_trip_path,
        expected_active_trip_sha256, output_path, *, expected_service_date=None,
        expected_source_rows=None, expected_active_stop_calls=None,
        expected_active_trips=None):
    """Write an atomic SQLite active stop-call index and JSON manifest."""
    feed_path = pathlib.Path(feed_path)
    active_trip_path = pathlib.Path(active_trip_path)
    output_path = pathlib.Path(output_path)
    manifest_path = pathlib.Path(f'{output_path}.manifest.json')
    feed_snapshot, feed_sha256, feed_bytes = _snapshot(
        feed_path, expected_feed_sha256, MAX_GTFS_BYTES, 'GTFS')
    active_snapshot = None
    database_path = None
    database = None
    manifest_temporary = None
    try:
        active_snapshot, active_sha256, active_bytes = _snapshot(
            active_trip_path, expected_active_trip_sha256,
            MAX_ACTIVE_DATABASE_BYTES, 'active-trip')
        active_trips, active_metadata = _load_active_trips(
            active_snapshot, expected_service_date, feed_sha256)
        counts = {
            'active_stop_calls': 0,
            'active_trips': len(active_trips),
            'active_trips_with_stop_calls': 0,
            'exact_stop_calls': 0,
            'fixed_scheduled_stop_calls': 0,
            'frequency_template_stop_calls': 0,
            'non_exact_stop_calls': 0,
            'source_stop_time_rows': 0,
        }
        database_path = _temporary_path(output_path)
        database = _create_database(database_path)
        try:
            with zipfile.ZipFile(feed_snapshot) as archive:
                _stream_stop_calls(archive, database, active_trips, counts)
        except (OSError, zipfile.BadZipFile) as exc:
            raise DatedEventIndexError(f'unreadable GTFS archive: {exc}') from exc
        _validate_chronology(database)
        _check_expected(
            counts, expected_source_rows, expected_active_stop_calls,
            expected_active_trips)
        metadata = {
            'active_trip_source_sha256': active_sha256,
            'generator_version': GENERATOR_VERSION,
            'parsed_source_sha256': feed_sha256,
            'schema_id': SCHEMA_ID,
            'schema_version': str(SCHEMA_VERSION),
            'service_date': active_metadata['service_date'],
            **{f'count.{key}': str(value) for key, value in counts.items()},
        }
        database.executemany(
            'INSERT INTO metadata(key, value) VALUES (?, ?)',
            sorted(metadata.items()))
        database.commit()
        database.execute('VACUUM')
        if database.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise DatedEventIndexError('output SQLite integrity check failed')
        database.close()
        database = None

        output_sha256 = _sha256(database_path)
        manifest = {
            'active_trip_source_bytes': active_bytes,
            'active_trip_source_sha256': active_sha256,
            'counts': counts,
            'format': 'sqlite3',
            'generator_version': GENERATOR_VERSION,
            'output_bytes': database_path.stat().st_size,
            'output_sha256': output_sha256,
            'parsed_source_bytes': feed_bytes,
            'parsed_source_sha256': feed_sha256,
            'schema_id': SCHEMA_ID,
            'schema_version': SCHEMA_VERSION,
            'service_date': active_metadata['service_date'],
        }
        manifest_temporary = _write_manifest(manifest_path, manifest)
        _publish_pair(
            database_path, output_path, manifest_temporary, manifest_path)
        database_path = None
        manifest_temporary = None
        return manifest
    except BaseException:
        if database is not None:
            database.close()
        if database_path is not None:
            database_path.unlink(missing_ok=True)
            pathlib.Path(f'{database_path}-journal').unlink(missing_ok=True)
        if manifest_temporary is not None:
            manifest_temporary.unlink(missing_ok=True)
        raise
    finally:
        feed_snapshot.unlink(missing_ok=True)
        if active_snapshot is not None:
            active_snapshot.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', required=True)
    parser.add_argument('--expected-feed-sha256', required=True)
    parser.add_argument('--active-trips', required=True)
    parser.add_argument('--expected-active-trips-sha256', required=True)
    parser.add_argument('--service-date', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--expected-source-rows', type=int)
    parser.add_argument('--expected-active-stop-calls', type=int)
    parser.add_argument('--expected-active-trips', type=int)
    args = parser.parse_args()
    started = time.monotonic()
    manifest = build_dated_event_index(
        args.feed, args.expected_feed_sha256, args.active_trips,
        args.expected_active_trips_sha256, args.output,
        expected_service_date=args.service_date,
        expected_source_rows=args.expected_source_rows,
        expected_active_stop_calls=args.expected_active_stop_calls,
        expected_active_trips=args.expected_active_trips)
    report = {
        **manifest,
        'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'wall_seconds': time.monotonic() - started,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
