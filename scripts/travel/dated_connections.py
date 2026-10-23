"""Build hash-pinned dated adjacent ride connections and first-board events.

The source active-stop-call SQLite file is privately snapshotted and hashed before
it is opened. Every adjacent pair is evaluated in stop-sequence order. Unsupported
or inexact pairs are counted and never bridged; only exact fixed scheduled rides
inside the bounded morning horizon are materialized.
"""
import argparse
import hashlib
import json
import os
import pathlib
import resource
import shutil
import sqlite3
import tempfile
import time


SCHEMA_VERSION = 1
SCHEMA_ID = 'steuerpendler.dated-ride-connections.v1'
SOURCE_SCHEMA_ID = 'steuerpendler.dated-active-stop-calls.v1'
SOURCE_APPLICATION_ID = 0x53504556
APPLICATION_ID = 0x5350434E
GENERATOR_VERSION = '1'
MAX_SOURCE_BYTES = 2_000_000_000
COPY_CHUNK_BYTES = 1024 * 1024
HORIZON_START = 6 * 3600 + 30 * 60
FIRST_BOARD_END = 8 * 3600 + 30 * 60
HORIZON_END = 9 * 3600


class DatedConnectionsError(ValueError):
    """The dated ride-connection artifact cannot be produced safely."""


def _sha256(path):
    with open(path, 'rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _temporary_path(destination, marker=''):
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=f'.{destination.name}.{marker}',
        suffix='.tmp', delete=False)
    path = pathlib.Path(handle.name)
    handle.close()
    return path


def _snapshot(source_path, expected_sha256, destination_directory):
    source_path = pathlib.Path(source_path)
    destination = destination_directory / source_path.name
    snapshot = _temporary_path(destination, 'snapshot.')
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with open(source_path, 'rb') as source, open(snapshot, 'wb') as output:
            while chunk := source.read(COPY_CHUNK_BYTES):
                byte_count += len(chunk)
                if byte_count > MAX_SOURCE_BYTES:
                    raise DatedConnectionsError(
                        f'source exceeds {MAX_SOURCE_BYTES} byte limit')
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise DatedConnectionsError('source SHA-256 mismatch')
        return snapshot, actual, byte_count
    except OSError as exc:
        snapshot.unlink(missing_ok=True)
        raise DatedConnectionsError(f'unreadable source: {exc}') from exc
    except BaseException:
        snapshot.unlink(missing_ok=True)
        raise


def _readonly_database(path):
    uri = pathlib.Path(path).resolve().as_uri() + '?mode=ro&immutable=1'
    return sqlite3.connect(uri, uri=True)


def _validate_source(path, expected_service_date):
    required_columns = {
        'trip_id', 'stop_sequence', 'source_row_number', 'arrival_seconds',
        'departure_seconds', 'stop_id', 'pickup_type', 'drop_off_type',
        'timepoint', 'event_time_status', 'route_id', 'service_id',
        'schedule_type',
    }
    try:
        database = _readonly_database(path)
        try:
            if database.execute('PRAGMA application_id').fetchone()[0] != SOURCE_APPLICATION_ID:
                raise DatedConnectionsError('invalid source application_id')
            if database.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise DatedConnectionsError('unsupported source schema version')
            if database.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise DatedConnectionsError('source SQLite integrity check failed')
            tables = {row[0] for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not {'metadata', 'stop_calls'} <= tables:
                raise DatedConnectionsError('source SQLite missing required table')
            columns = {row[1] for row in database.execute(
                "PRAGMA table_info('stop_calls')")}
            missing = required_columns - columns
            if missing:
                raise DatedConnectionsError(
                    f'source stop_calls missing column {sorted(missing)[0]}')
            metadata = dict(database.execute('SELECT key, value FROM metadata'))
            required_metadata = {
                'schema_id', 'schema_version', 'service_date',
                'parsed_source_sha256',
            }
            missing = required_metadata - set(metadata)
            if missing:
                raise DatedConnectionsError(
                    f'source metadata missing {sorted(missing)[0]}')
            if metadata['schema_id'] != SOURCE_SCHEMA_ID:
                raise DatedConnectionsError('source schema_id mismatch')
            if metadata['schema_version'] != '1':
                raise DatedConnectionsError('unsupported source metadata schema')
            if (expected_service_date is not None
                    and metadata['service_date'] != expected_service_date):
                raise DatedConnectionsError('source service date mismatch')
            invalid = database.execute('''
                SELECT COUNT(*) FROM stop_calls
                WHERE trip_id = '' OR stop_id = '' OR route_id = '' OR service_id = ''
                   OR stop_sequence < 0 OR source_row_number < 2
                   OR pickup_type NOT BETWEEN 0 AND 3
                   OR drop_off_type NOT BETWEEN 0 AND 3
                   OR timepoint NOT IN (0, 1)
                   OR event_time_status NOT IN
                      ('exact', 'non_exact', 'frequency_template')
                   OR schedule_type NOT IN
                      ('fixed_scheduled',
                       'frequency_template_exact_times_0',
                       'frequency_template_exact_times_1')
                   OR (schedule_type = 'fixed_scheduled'
                       AND event_time_status = 'frequency_template')
                   OR (schedule_type != 'fixed_scheduled'
                       AND event_time_status != 'frequency_template')
            ''').fetchone()[0]
            if invalid:
                raise DatedConnectionsError(
                    f'source contains {invalid} invalid stop-call row(s)')
            stop_call_count = database.execute(
                'SELECT COUNT(*) FROM stop_calls').fetchone()[0]
            if stop_call_count == 0:
                raise DatedConnectionsError('source stop_calls is empty')
            return metadata, stop_call_count
        finally:
            database.close()
    except DatedConnectionsError:
        raise
    except (OSError, sqlite3.DatabaseError) as exc:
        raise DatedConnectionsError(f'invalid source SQLite: {exc}') from exc


def _create_database(path):
    database = sqlite3.connect(path)
    database.execute('PRAGMA page_size = 4096')
    database.execute('PRAGMA journal_mode = DELETE')
    database.execute('PRAGMA synchronous = FULL')
    database.execute('PRAGMA temp_store = FILE')
    database.execute('PRAGMA cache_size = -131072')
    database.execute(f'PRAGMA application_id = {APPLICATION_ID}')
    database.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
    database.executescript('''
        CREATE TABLE ride_connections (
            connection_id INTEGER PRIMARY KEY,
            trip_id TEXT NOT NULL,
            route_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            from_stop_sequence INTEGER NOT NULL,
            to_stop_sequence INTEGER NOT NULL,
            from_source_row_number INTEGER NOT NULL,
            to_source_row_number INTEGER NOT NULL,
            departure_seconds INTEGER NOT NULL,
            arrival_seconds INTEGER NOT NULL,
            from_stop_id TEXT NOT NULL,
            to_stop_id TEXT NOT NULL,
            from_pickup_type INTEGER NOT NULL CHECK (from_pickup_type BETWEEN 0 AND 3),
            from_drop_off_type INTEGER NOT NULL CHECK (from_drop_off_type BETWEEN 0 AND 3),
            to_pickup_type INTEGER NOT NULL CHECK (to_pickup_type BETWEEN 0 AND 3),
            to_drop_off_type INTEGER NOT NULL CHECK (to_drop_off_type BETWEEN 0 AND 3),
            CHECK (from_stop_sequence < to_stop_sequence),
            CHECK (departure_seconds <= arrival_seconds)
        );
        CREATE TABLE first_board_events (
            event_id INTEGER PRIMARY KEY,
            connection_id INTEGER NOT NULL UNIQUE
                REFERENCES ride_connections(connection_id)
        );
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;
    ''')
    return database


def _materialize_adjacent(database, source_path):
    database.execute('ATTACH DATABASE ? AS source', (str(source_path),))
    database.execute('''
        CREATE TEMP TABLE adjacent AS
        SELECT
            trip_id,
            route_id,
            service_id,
            stop_sequence AS from_stop_sequence,
            LEAD(stop_sequence) OVER trip_order AS to_stop_sequence,
            source_row_number AS from_source_row_number,
            LEAD(source_row_number) OVER trip_order AS to_source_row_number,
            departure_seconds,
            LEAD(arrival_seconds) OVER trip_order AS arrival_seconds,
            stop_id AS from_stop_id,
            LEAD(stop_id) OVER trip_order AS to_stop_id,
            pickup_type AS from_pickup_type,
            drop_off_type AS from_drop_off_type,
            LEAD(pickup_type) OVER trip_order AS to_pickup_type,
            LEAD(drop_off_type) OVER trip_order AS to_drop_off_type,
            event_time_status AS from_event_time_status,
            LEAD(event_time_status) OVER trip_order AS to_event_time_status,
            schedule_type AS from_schedule_type,
            LEAD(schedule_type) OVER trip_order AS to_schedule_type,
            LEAD(route_id) OVER trip_order AS to_route_id,
            LEAD(service_id) OVER trip_order AS to_service_id
        FROM source.stop_calls
        WINDOW trip_order AS (PARTITION BY trip_id ORDER BY stop_sequence)
    ''')
    database.execute('DELETE FROM adjacent WHERE to_stop_sequence IS NULL')
    inconsistent = database.execute('''
        SELECT COUNT(*) FROM adjacent
        WHERE route_id != to_route_id OR service_id != to_service_id
           OR from_schedule_type != to_schedule_type
    ''').fetchone()[0]
    if inconsistent:
        raise DatedConnectionsError(
            f'source contains {inconsistent} trip metadata transition(s)')


def _category_sql():
    return f'''
        CASE
          WHEN from_schedule_type != 'fixed_scheduled'
            OR to_schedule_type != 'fixed_scheduled'
            OR from_event_time_status = 'frequency_template'
            OR to_event_time_status = 'frequency_template'
            THEN 'frequency'
          WHEN departure_seconds IS NULL OR arrival_seconds IS NULL
            THEN 'missing_time'
          WHEN from_event_time_status != 'exact'
            OR to_event_time_status != 'exact'
            THEN 'non_exact'
          WHEN departure_seconds > arrival_seconds THEN 'chronology'
          WHEN departure_seconds < {HORIZON_START}
            OR arrival_seconds > {HORIZON_END}
            THEN 'outside_horizon'
          ELSE 'ride'
        END
    '''


def _build_rows(database, stop_call_count):
    category = _category_sql()
    grouped = dict(database.execute(f'''
        SELECT category, COUNT(*) FROM (
            SELECT {category} AS category FROM adjacent
        ) GROUP BY category
    '''))
    counts = {
        'source_stop_calls': stop_call_count,
        'source_adjacent_pairs': sum(grouped.values()),
        'ride_connections': grouped.get('ride', 0),
        'quarantined_frequency_pairs': grouped.get('frequency', 0),
        'quarantined_missing_time_pairs': grouped.get('missing_time', 0),
        'quarantined_non_exact_pairs': grouped.get('non_exact', 0),
        'quarantined_chronology_pairs': grouped.get('chronology', 0),
        'outside_horizon_pairs': grouped.get('outside_horizon', 0),
    }
    database.execute(f'''
        INSERT INTO ride_connections (
            connection_id, trip_id, route_id, service_id,
            from_stop_sequence, to_stop_sequence,
            from_source_row_number, to_source_row_number,
            departure_seconds, arrival_seconds, from_stop_id, to_stop_id,
            from_pickup_type, from_drop_off_type,
            to_pickup_type, to_drop_off_type
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY trip_id, from_stop_sequence),
            trip_id, route_id, service_id,
            from_stop_sequence, to_stop_sequence,
            from_source_row_number, to_source_row_number,
            departure_seconds, arrival_seconds, from_stop_id, to_stop_id,
            from_pickup_type, from_drop_off_type,
            to_pickup_type, to_drop_off_type
        FROM adjacent
        WHERE {category} = 'ride'
        ORDER BY trip_id, from_stop_sequence
    ''')
    board_counts = dict(database.execute(f'''
        SELECT
          CASE
            WHEN from_pickup_type = 0 THEN 'candidate'
            WHEN from_pickup_type = 1 THEN 'prohibited'
            ELSE 'conditional'
          END,
          COUNT(*)
        FROM ride_connections
        WHERE departure_seconds BETWEEN {HORIZON_START} AND {FIRST_BOARD_END}
        GROUP BY 1
    '''))
    database.execute(f'''
        INSERT INTO first_board_events(event_id, connection_id)
        SELECT ROW_NUMBER() OVER (ORDER BY connection_id), connection_id
        FROM ride_connections
        WHERE departure_seconds BETWEEN {HORIZON_START} AND {FIRST_BOARD_END}
          AND from_pickup_type = 0
        ORDER BY connection_id
    ''')
    counts.update({
        'candidate_first_board_events': board_counts.get('candidate', 0),
        'first_board_pickup_prohibited': board_counts.get('prohibited', 0),
        'first_board_conditional_unresolved': board_counts.get('conditional', 0),
    })
    database.executescript('''
        CREATE INDEX ride_connections_departure_from_idx
            ON ride_connections(departure_seconds, from_stop_id, connection_id);
        CREATE INDEX ride_connections_trip_sequence_idx
            ON ride_connections(trip_id, from_stop_sequence, to_stop_sequence);
        CREATE INDEX first_board_events_connection_idx
            ON first_board_events(connection_id);
    ''')
    return counts


def _write_manifest(path, payload):
    temporary = _temporary_path(path)
    data = (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':')) + '\n').encode('utf-8')
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
    try:
        shutil.copyfile(path, backup)
        with open(backup, 'rb') as handle:
            os.fsync(handle.fileno())
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
    database_started = False
    manifest_started = False
    database_rollback_complete = False
    manifest_rollback_complete = False
    publication_complete = False
    try:
        database_started = True
        os.replace(database_temporary, output_path)
        manifest_started = True
        os.replace(manifest_temporary, manifest_path)
        directory_fd = os.open(output_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        publication_complete = True
    except BaseException:
        rollback_errors = []
        if manifest_started:
            if manifest_temporary.exists():
                # Replacement did not happen, so the previous target is intact.
                manifest_rollback_complete = True
            else:
                try:
                    if manifest_backup is None:
                        manifest_path.unlink(missing_ok=True)
                    else:
                        os.replace(manifest_backup, manifest_path)
                    manifest_rollback_complete = True
                except BaseException as exc:
                    rollback_errors.append(('manifest', manifest_backup, exc))
        if database_started and not database_temporary.exists():
            try:
                if database_backup is None:
                    output_path.unlink(missing_ok=True)
                else:
                    os.replace(database_backup, output_path)
                database_rollback_complete = True
            except BaseException as exc:
                rollback_errors.append(('database', database_backup, exc))
        if rollback_errors:
            label, backup, error = rollback_errors[0]
            raise DatedConnectionsError(
                f'{label} rollback failed; recovery backup retained: {backup}') from error
        raise
    finally:
        database_temporary.unlink(missing_ok=True)
        manifest_temporary.unlink(missing_ok=True)
        if database_backup is not None and (
                publication_complete or database_rollback_complete
                or not database_started):
            database_backup.unlink(missing_ok=True)
        if manifest_backup is not None and (
                publication_complete or manifest_rollback_complete
                or not manifest_started):
            manifest_backup.unlink(missing_ok=True)


def build_dated_connections(source_path, expected_source_sha256, output_path, *,
                            expected_service_date=None,
                            expected_ride_connections=None,
                            expected_first_board_events=None):
    """Write an atomic SQLite ride primitive and deterministic JSON manifest."""
    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = pathlib.Path(f'{output_path}.manifest.json')
    snapshot = None
    database_path = None
    manifest_temporary = None
    database = None
    try:
        snapshot, source_sha256, source_bytes = _snapshot(
            source_path, expected_source_sha256, output_path.parent)
        source_metadata, stop_call_count = _validate_source(
            snapshot, expected_service_date)
        database_path = _temporary_path(output_path)
        database = _create_database(database_path)
        _materialize_adjacent(database, snapshot)
        counts = _build_rows(database, stop_call_count)
        checks = (
            ('ride connection', expected_ride_connections,
             counts['ride_connections']),
            ('first-board event', expected_first_board_events,
             counts['candidate_first_board_events']),
        )
        for label, expected, actual in checks:
            if expected is not None and expected != actual:
                raise DatedConnectionsError(
                    f'{label} count mismatch: expected {expected}, got {actual}')
        metadata = {
            'generator_version': GENERATOR_VERSION,
            'horizon_end_seconds_inclusive': str(HORIZON_END),
            'horizon_start_seconds_inclusive': str(HORIZON_START),
            'first_board_end_seconds_inclusive': str(FIRST_BOARD_END),
            'schema_id': SCHEMA_ID,
            'schema_version': str(SCHEMA_VERSION),
            'service_date': source_metadata['service_date'],
            'source_schema_id': source_metadata['schema_id'],
            'source_sha256': source_sha256,
            **{f'count.{key}': str(value) for key, value in counts.items()},
        }
        database.executemany(
            'INSERT INTO metadata(key, value) VALUES (?, ?)',
            sorted(metadata.items()))
        database.execute('DROP TABLE adjacent')
        database.commit()
        database.execute('VACUUM')
        if database.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise DatedConnectionsError('output SQLite integrity check failed')
        database.close()
        database = None

        output_sha256 = _sha256(database_path)
        manifest = {
            'counts': counts,
            'first_board_window_seconds_inclusive': [
                HORIZON_START, FIRST_BOARD_END],
            'format': 'sqlite3',
            'generator_version': GENERATOR_VERSION,
            'limitations': [
                'This artifact contains adjacent ride primitives, not complete journeys.',
                'It does not evaluate transfers, residential access, destination groups, or fastest routes.',
                'Quarantined or absent pairs are unresolved and are not negative reachability evidence.',
            ],
            'output_bytes': database_path.stat().st_size,
            'output_sha256': output_sha256,
            'ride_horizon_seconds_inclusive': [HORIZON_START, HORIZON_END],
            'schema_id': SCHEMA_ID,
            'schema_version': SCHEMA_VERSION,
            'service_date': source_metadata['service_date'],
            'source_bytes': source_bytes,
            'source_schema_id': source_metadata['schema_id'],
            'source_sha256': source_sha256,
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
        if snapshot is not None:
            snapshot.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--expected-source-sha256', required=True)
    parser.add_argument('--service-date', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--expected-ride-connections', type=int)
    parser.add_argument('--expected-first-board-events', type=int)
    args = parser.parse_args()
    started = time.monotonic()
    manifest = build_dated_connections(
        args.source, args.expected_source_sha256, args.output,
        expected_service_date=args.service_date,
        expected_ride_connections=args.expected_ride_connections,
        expected_first_board_events=args.expected_first_board_events)
    report = {
        **manifest,
        'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'wall_seconds': time.monotonic() - started,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
