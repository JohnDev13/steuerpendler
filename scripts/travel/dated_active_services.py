"""Build a pinned, exact-date index of active GTFS trips.

The SQLite artifact contains service-active trip identifiers and source metadata;
frequency-based trips remain templates, not fabricated departure events. Large
GTFS members are streamed and temporary uniqueness indexes live on disk.
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
GENERATOR_VERSION = '1'
MAX_SOURCE_BYTES = 1_000_000_000
COPY_CHUNK_BYTES = 1024 * 1024
WEEKDAYS = (
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
    'saturday', 'sunday',
)
SCHEDULE_TYPES = (
    'fixed_scheduled',
    'frequency_template_exact_times_0',
    'frequency_template_exact_times_1',
)


class ActiveServiceError(ValueError):
    """The pinned active-trip artifact cannot be produced safely."""


def _sha256(path):
    with open(path, 'rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _snapshot_feed(path, expected_sha256):
    """Copy and hash one opened feed into a private, bounded local snapshot."""
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f'.{path.name}.snapshot.',
        suffix='.tmp', delete=False)
    snapshot = pathlib.Path(handle.name)
    digest = hashlib.sha256()
    source_bytes = 0
    try:
        with handle, open(path, 'rb') as source:
            while chunk := source.read(COPY_CHUNK_BYTES):
                source_bytes += len(chunk)
                if source_bytes > MAX_SOURCE_BYTES:
                    raise ActiveServiceError(
                        f'GTFS archive exceeds {MAX_SOURCE_BYTES} byte limit')
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        source_sha256 = digest.hexdigest()
        if source_sha256 != expected_sha256:
            raise ActiveServiceError('GTFS SHA-256 mismatch')
        return snapshot, source_sha256, source_bytes
    except OSError as exc:
        snapshot.unlink(missing_ok=True)
        raise ActiveServiceError(f'unreadable GTFS archive: {exc}') from exc
    except BaseException:
        snapshot.unlink(missing_ok=True)
        raise


def _rows(archive, name, required_fields):
    if name not in archive.namelist():
        raise ActiveServiceError(f'missing {name}')
    try:
        with archive.open(name) as raw, io.TextIOWrapper(
                raw, encoding='utf-8-sig', newline='') as text:
            reader = csv.DictReader(text, strict=True)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)):
                raise ActiveServiceError(f'invalid {name}: duplicate field')
            missing = required_fields - set(fields)
            if missing:
                raise ActiveServiceError(
                    f'invalid {name}: missing field {sorted(missing)[0]}')
            for number, row in enumerate(reader, 2):
                if None in row:
                    raise ActiveServiceError(
                        f'invalid {name} row {number}: unexpected field')
                yield number, row
    except ActiveServiceError:
        raise
    except (csv.Error, UnicodeError, KeyError) as exc:
        raise ActiveServiceError(f'invalid {name}: {exc}') from exc


def _parse_date(value, context):
    try:
        return dt.datetime.strptime(value, '%Y%m%d').date()
    except (TypeError, ValueError) as exc:
        raise ActiveServiceError(f'invalid {context}') from exc


def _gtfs_seconds(value):
    try:
        parts = value.split(':')
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise ValueError
        hours, minutes, seconds = map(int, parts)
        if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
            raise ValueError
        return hours * 3600 + minutes * 60 + seconds
    except (AttributeError, TypeError, ValueError) as exc:
        raise ActiveServiceError('invalid frequency row') from exc


def _active_services(archive, service_day, counts):
    active = set()
    seen = set()
    required = {'service_id', 'start_date', 'end_date', *WEEKDAYS}
    selected_weekday = WEEKDAYS[service_day.weekday()]
    for number, row in _rows(archive, 'calendar.txt', required):
        counts['calendar_rows'] += 1
        service_id = row['service_id']
        if not service_id:
            raise ActiveServiceError(f'empty service_id in calendar.txt row {number}')
        if service_id in seen:
            raise ActiveServiceError(
                f'duplicate service in calendar.txt: {service_id}')
        seen.add(service_id)
        if any(row[field] not in {'0', '1'} for field in WEEKDAYS):
            raise ActiveServiceError(
                f'invalid weekday metadata for service {service_id}')
        start = _parse_date(
            row['start_date'], f'calendar date for service {service_id}')
        end = _parse_date(
            row['end_date'], f'calendar date for service {service_id}')
        if start > end:
            raise ActiveServiceError(
                f'inverted calendar range for service {service_id}')
        if start <= service_day <= end and row[selected_weekday] == '1':
            active.add(service_id)

    exact_date = service_day.strftime('%Y%m%d')
    exception_seen = set()
    required = {'service_id', 'date', 'exception_type'}
    for number, row in _rows(archive, 'calendar_dates.txt', required):
        counts['calendar_date_rows'] += 1
        service_id = row['service_id']
        if not service_id:
            raise ActiveServiceError(
                f'empty service_id in calendar_dates.txt row {number}')
        row_date = _parse_date(
            row['date'], f'calendar_dates date for service {service_id}')
        if row['exception_type'] not in {'1', '2'}:
            raise ActiveServiceError(
                f'invalid exception_type for service {service_id}')
        if row['date'] != exact_date:
            continue
        key = (service_id, row['date'])
        if key in exception_seen:
            raise ActiveServiceError(
                f'duplicate service/date in calendar_dates.txt: {service_id}')
        exception_seen.add(key)
        if row['exception_type'] == '1':
            active.add(service_id)
        else:
            active.discard(service_id)
        # Parsing above intentionally validates even irrelevant exception dates.
        del row_date
    counts['resolved_active_services'] = len(active)
    return active


def _frequency_templates(archive, counts):
    templates = {}
    required = {
        'trip_id', 'start_time', 'end_time', 'headway_secs', 'exact_times',
    }
    for number, row in _rows(archive, 'frequencies.txt', required):
        counts['frequency_rows'] += 1
        trip_id = row['trip_id']
        exact_times = row['exact_times'] or '0'
        try:
            headway = int(row['headway_secs'])
        except (TypeError, ValueError) as exc:
            raise ActiveServiceError(
                f'invalid frequency row {number}') from exc
        start = _gtfs_seconds(row['start_time'])
        end = _gtfs_seconds(row['end_time'])
        if (not trip_id or exact_times not in {'0', '1'}
                or headway <= 0 or start >= end):
            raise ActiveServiceError(f'invalid frequency row {number}')
        prior = templates.get(trip_id)
        if prior is not None and prior != exact_times:
            raise ActiveServiceError(
                f'contradictory exact_times for frequency trip {trip_id}')
        templates[trip_id] = exact_times
    counts['frequency_template_trip_ids'] = len(templates)
    return templates


def _create_database(path):
    database = sqlite3.connect(path)
    database.execute('PRAGMA page_size = 4096')
    database.execute('PRAGMA journal_mode = DELETE')
    database.execute('PRAGMA synchronous = FULL')
    database.execute('PRAGMA temp_store = FILE')
    database.execute('PRAGMA auto_vacuum = NONE')
    database.execute('PRAGMA application_id = 0x53504154')
    database.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
    database.executescript('''
        CREATE TABLE trips (
            trip_id TEXT PRIMARY KEY,
            route_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            schedule_type TEXT NOT NULL CHECK (schedule_type IN (
                'fixed_scheduled',
                'frequency_template_exact_times_0',
                'frequency_template_exact_times_1'
            ))
        ) WITHOUT ROWID;
        CREATE INDEX trips_service_id ON trips(service_id, trip_id);
        CREATE INDEX trips_route_id ON trips(route_id, trip_id);
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TEMP TABLE seen_trips (
            trip_id TEXT PRIMARY KEY
        ) WITHOUT ROWID;
    ''')
    return database


def _stream_trips(archive, database, active_services, templates, counts):
    active_with_trips = set()
    status_counts = {status: 0 for status in SCHEDULE_TYPES}
    referenced_templates = set()
    required = {'trip_id', 'route_id', 'service_id'}
    for number, row in _rows(archive, 'trips.txt', required):
        counts['trip_rows'] += 1
        trip_id = row['trip_id']
        route_id = row['route_id']
        service_id = row['service_id']
        if not trip_id or not route_id or not service_id:
            raise ActiveServiceError(
                f'incomplete trip metadata in trips.txt row {number}')
        try:
            database.execute(
                'INSERT INTO seen_trips(trip_id) VALUES (?)', (trip_id,))
        except sqlite3.IntegrityError as exc:
            raise ActiveServiceError(f'duplicate trip_id in trips.txt: {trip_id}') from exc
        exact_times = templates.get(trip_id)
        if exact_times is not None:
            referenced_templates.add(trip_id)
        if service_id not in active_services:
            counts['inactive_trip_rows'] += 1
            continue
        schedule_type = ('fixed_scheduled' if exact_times is None else
                         f'frequency_template_exact_times_{exact_times}')
        database.execute(
            'INSERT INTO trips(trip_id, route_id, service_id, schedule_type) '
            'VALUES (?, ?, ?, ?)',
            (trip_id, route_id, service_id, schedule_type))
        counts['active_trip_ids'] += 1
        status_counts[schedule_type] += 1
        active_with_trips.add(service_id)

    orphaned = sorted(set(templates) - referenced_templates)
    if orphaned:
        raise ActiveServiceError(
            f'frequency template references unknown trip: {orphaned[0]}')
    counts['active_services_with_trips'] = len(active_with_trips)
    counts['active_frequency_templates'] = (
        status_counts['frequency_template_exact_times_0']
        + status_counts['frequency_template_exact_times_1'])
    return status_counts


def _check_expected(counts, expected_active_trips, expected_active_services,
                    expected_frequency_templates):
    checks = (
        ('active trip', expected_active_trips, counts['active_trip_ids']),
        ('active service', expected_active_services,
         counts['active_services_with_trips']),
        ('active frequency template', expected_frequency_templates,
         counts['active_frequency_templates']),
    )
    for label, expected, actual in checks:
        if expected is not None and actual != expected:
            raise ActiveServiceError(
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
    """Publish both files, restoring the previous pair on handled failures."""
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


def build_active_trip_manifest(
        feed_path, expected_sha256, service_day, output_path, *,
        expected_active_trips=None, expected_active_services=None,
        expected_frequency_templates=None):
    """Write an atomic SQLite active-trip index and deterministic JSON manifest."""
    if not isinstance(service_day, dt.date) or isinstance(service_day, dt.datetime):
        raise ActiveServiceError('service day must be a date')
    feed_path = pathlib.Path(feed_path)
    output_path = pathlib.Path(output_path)
    manifest_path = pathlib.Path(f'{output_path}.manifest.json')
    snapshot_path, source_sha256, source_bytes = _snapshot_feed(
        feed_path, expected_sha256)

    counts = {
        'calendar_rows': 0,
        'calendar_date_rows': 0,
        'frequency_rows': 0,
        'frequency_template_trip_ids': 0,
        'trip_rows': 0,
        'inactive_trip_rows': 0,
        'resolved_active_services': 0,
        'active_trip_ids': 0,
        'active_services_with_trips': 0,
        'active_frequency_templates': 0,
    }
    database_path = _temporary_path(output_path)
    manifest_temporary = None
    database = None
    try:
        try:
            with zipfile.ZipFile(snapshot_path) as archive:
                active_services = _active_services(archive, service_day, counts)
                templates = _frequency_templates(archive, counts)
                database = _create_database(database_path)
                status_counts = _stream_trips(
                    archive, database, active_services, templates, counts)
        except (OSError, zipfile.BadZipFile) as exc:
            raise ActiveServiceError(f'unreadable GTFS archive: {exc}') from exc

        _check_expected(
            counts, expected_active_trips, expected_active_services,
            expected_frequency_templates)
        metadata = {
            'generator_version': GENERATOR_VERSION,
            'schema_version': str(SCHEMA_VERSION),
            'service_date': service_day.isoformat(),
            'source_sha256': source_sha256,
            **{f'count.{key}': str(value) for key, value in counts.items()},
            **{f'status.{key}': str(value)
               for key, value in status_counts.items()},
        }
        database.executemany(
            'INSERT INTO metadata(key, value) VALUES (?, ?)',
            sorted(metadata.items()))
        database.commit()
        database.execute('VACUUM')
        database.close()
        database = None

        output_sha256 = _sha256(database_path)
        output_bytes = database_path.stat().st_size
        manifest = {
            'counts': counts,
            'format': 'sqlite3',
            'generator_version': GENERATOR_VERSION,
            'output_bytes': output_bytes,
            'output_sha256': output_sha256,
            'schema_version': SCHEMA_VERSION,
            'service_date': service_day.isoformat(),
            'source_bytes': source_bytes,
            'source_sha256': source_sha256,
            'status_counts': status_counts,
        }
        manifest_temporary = _write_manifest(manifest_path, manifest)
        _publish_pair(
            database_path, output_path, manifest_temporary, manifest_path)
        manifest_temporary = None
        return manifest
    except BaseException:
        if database is not None:
            database.close()
        database_path.unlink(missing_ok=True)
        pathlib.Path(f'{database_path}-journal').unlink(missing_ok=True)
        if manifest_temporary is not None:
            manifest_temporary.unlink(missing_ok=True)
        raise
    finally:
        snapshot_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--service-date', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--expected-active-trips', type=int)
    parser.add_argument('--expected-active-services', type=int)
    parser.add_argument('--expected-frequency-templates', type=int)
    args = parser.parse_args()
    try:
        service_day = dt.date.fromisoformat(args.service_date)
    except ValueError as exc:
        raise ActiveServiceError(f'invalid service date: {exc}') from exc
    started = time.monotonic()
    manifest = build_active_trip_manifest(
        args.feed, args.expected_sha256, service_day, args.output,
        expected_active_trips=args.expected_active_trips,
        expected_active_services=args.expected_active_services,
        expected_frequency_templates=args.expected_frequency_templates)
    report = {
        **manifest,
        'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'wall_seconds': time.monotonic() - started,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
