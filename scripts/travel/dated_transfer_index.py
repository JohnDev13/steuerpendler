"""Build a frozen, directed SQLite index of GTFS transfer rules.

The index preserves source order and selectors.  It deliberately does not resolve
journeys or infer that a producer-specific ``service_id`` is active on the
reference day.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import pathlib
import resource
import shutil
import sqlite3
import tempfile
import time
import zipfile


SCHEMA_VERSION = 1
SCHEMA_ID = 'steuerpendler.dated-directed-transfer-rules.v1'
APPLICATION_ID = 0x53505452
GENERATOR_VERSION = '1'
EXPECTED_GTFS_SHA256 = 'd5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e'
EXPECTED_TOTAL_ROWS = 1_124_239
EXPECTED_TYPE_COUNTS = {'1': 292, '2': 819_258, '4': 304_689}
MAX_GTFS_BYTES = 1_000_000_000
COPY_CHUNK_BYTES = 1024 * 1024
REQUIRED_FIELDS = {
    'from_stop_id', 'to_stop_id', 'from_route_id', 'to_route_id',
    'from_trip_id', 'to_trip_id', 'transfer_type', 'min_transfer_time',
    'service_id',
}


class DatedTransferIndexError(ValueError):
    """The directed transfer-rule index cannot be produced faithfully."""


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
                if byte_count > MAX_GTFS_BYTES:
                    raise DatedTransferIndexError(
                        f'GTFS exceeds {MAX_GTFS_BYTES} byte limit')
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise DatedTransferIndexError('GTFS SHA-256 mismatch')
        return snapshot, actual, byte_count
    except OSError as exc:
        snapshot.unlink(missing_ok=True)
        raise DatedTransferIndexError(f'unreadable GTFS: {exc}') from exc
    except BaseException:
        snapshot.unlink(missing_ok=True)
        raise


def _member(archive, name):
    members = [member for member in archive.infolist() if member.filename == name]
    if not members:
        raise DatedTransferIndexError(f'missing {name}')
    if len(members) != 1:
        raise DatedTransferIndexError(f'duplicate member in GTFS archive: {name}')
    return members[0]


def _rows(archive):
    member = _member(archive, 'transfers.txt')
    try:
        with archive.open(member) as raw, io.TextIOWrapper(
                raw, encoding='utf-8-sig', newline='') as text:
            reader = csv.DictReader(text, strict=True)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)):
                raise DatedTransferIndexError(
                    'invalid transfers.txt: duplicate field')
            missing = REQUIRED_FIELDS - set(fields)
            if missing:
                raise DatedTransferIndexError(
                    f'invalid transfers.txt: missing field {sorted(missing)[0]}')
            for source_row_number, row in enumerate(reader, 2):
                if None in row:
                    raise DatedTransferIndexError(
                        f'invalid transfers.txt row {source_row_number}: unexpected field')
                yield fields, source_row_number, row
    except DatedTransferIndexError:
        raise
    except (csv.Error, UnicodeError, KeyError) as exc:
        raise DatedTransferIndexError(f'invalid transfers.txt: {exc}') from exc


def _specificity(row):
    from_kind = 'trip' if row['from_trip_id'] else 'route' if row['from_route_id'] else None
    to_kind = 'trip' if row['to_trip_id'] else 'route' if row['to_route_id'] else None
    kinds = (from_kind, to_kind)
    if kinds == ('trip', 'trip'):
        return 6
    if set(kinds) == {'trip', 'route'}:
        return 5
    if 'trip' in kinds:
        return 4
    if kinds == ('route', 'route'):
        return 3
    if 'route' in kinds:
        return 2
    return 1


def _normalize(source_row_number, row):
    transfer_type = row['transfer_type']
    if transfer_type not in {'1', '2', '4'}:
        raise DatedTransferIndexError(
            f'unsupported transfer_type at transfers.txt row {source_row_number}: '
            f'{transfer_type!r}')
    for side in ('from', 'to'):
        if row[f'{side}_trip_id'] and not row[f'{side}_route_id']:
            raise DatedTransferIndexError(
                f'{side}_trip_id requires {side}_route_id at '
                f'transfers.txt row {source_row_number}')
    if transfer_type in {'1', '2'} and (
            not row['from_stop_id'] or not row['to_stop_id']):
        raise DatedTransferIndexError(
            f'transfer_type {transfer_type} requires directed stop selectors at '
            f'transfers.txt row {source_row_number}')
    if transfer_type in {'1', '4'} and (
            not row['from_trip_id'] or not row['to_trip_id']):
        raise DatedTransferIndexError(
            f'transfer_type {transfer_type} requires both trip selectors at '
            f'transfers.txt row {source_row_number}')

    minimum_text = row['min_transfer_time']
    if minimum_text:
        if not minimum_text.isdigit() or int(minimum_text) > 2_147_483_647:
            raise DatedTransferIndexError(
                f'invalid min_transfer_time at transfers.txt row {source_row_number}')
        minimum = int(minimum_text)
    else:
        minimum = None
    if transfer_type == '2' and minimum is None:
        raise DatedTransferIndexError(
            f'missing min_transfer_time at transfers.txt row {source_row_number}')
    if transfer_type != '2' and minimum is not None:
        raise DatedTransferIndexError(
            f'min_transfer_time must be empty for transfer_type {transfer_type} '
            f'at transfers.txt row {source_row_number}')

    service = row['service_id']
    unresolved = bool(service)
    semantics = {'1': 'timed', '2': 'minimum_time', '4': 'in_seat'}
    return (
        source_row_number - 1, source_row_number,
        row['from_stop_id'], row['to_stop_id'],
        row['from_route_id'], row['to_route_id'],
        row['from_trip_id'], row['to_trip_id'], int(transfer_type), minimum,
        service, semantics[transfer_type], _specificity(row),
        'unresolved' if unresolved else 'resolved',
        'unknown_custom_service_id' if unresolved else 'unrestricted_by_service_id',
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
    )


def _create_database(path):
    database = sqlite3.connect(path)
    database.execute('PRAGMA page_size = 4096')
    database.execute('PRAGMA journal_mode = DELETE')
    database.execute('PRAGMA synchronous = FULL')
    database.execute('PRAGMA temp_store = FILE')
    database.execute('PRAGMA cache_size = -131072')
    database.execute('PRAGMA auto_vacuum = NONE')
    database.execute(f'PRAGMA application_id = {APPLICATION_ID}')
    database.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
    database.executescript('''
        CREATE TABLE transfer_rules (
            rule_id INTEGER PRIMARY KEY,
            source_row_number INTEGER NOT NULL UNIQUE CHECK (source_row_number >= 2),
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
            selector_specificity INTEGER NOT NULL CHECK (
                selector_specificity BETWEEN 1 AND 6),
            scope_status TEXT NOT NULL CHECK (
                scope_status IN ('resolved', 'unresolved')),
            service_date_applicability TEXT NOT NULL CHECK (
                service_date_applicability IN (
                    'unrestricted_by_service_id', 'unknown_custom_service_id')),
            source_fields_json TEXT NOT NULL,
            CHECK ((transfer_type = 2) = (min_transfer_time IS NOT NULL))
        );
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;
    ''')
    return database


def _stream_rules(archive, database):
    counts = {
        'source_rows': 0,
        'transfer_type_1': 0,
        'transfer_type_2': 0,
        'transfer_type_4': 0,
        'scope_resolved': 0,
        'scope_unresolved': 0,
        'custom_service_unknown': 0,
    }
    fields_seen = None
    insert = '''
        INSERT INTO transfer_rules VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    for fields, source_row_number, source_row in _rows(archive):
        if fields_seen is None:
            fields_seen = fields
        normalized = _normalize(source_row_number, source_row)
        database.execute(insert, normalized)
        transfer_type = source_row['transfer_type']
        counts['source_rows'] += 1
        counts[f'transfer_type_{transfer_type}'] += 1
        status = normalized[13]
        counts[f'scope_{status}'] += 1
        if source_row['service_id']:
            counts['custom_service_unknown'] += 1
    if not counts['source_rows']:
        raise DatedTransferIndexError('transfers.txt is empty')
    return counts, fields_seen


def _check_expected(counts, expected_total_rows, expected_type_counts):
    if expected_total_rows is not None and counts['source_rows'] != expected_total_rows:
        raise DatedTransferIndexError(
            f'row count mismatch: expected {expected_total_rows}, '
            f'got {counts["source_rows"]}')
    if expected_type_counts is not None:
        for kind in ('1', '2', '4'):
            expected = expected_type_counts.get(kind, 0)
            actual = counts[f'transfer_type_{kind}']
            if expected != actual:
                raise DatedTransferIndexError(
                    f'transfer_type {kind} count mismatch: expected {expected}, '
                    f'got {actual}')


def _finalize(database, metadata):
    database.executemany(
        'INSERT INTO metadata(key, value) VALUES (?, ?)', sorted(metadata.items()))
    database.executescript('''
        CREATE INDEX transfer_rules_from_stop_idx ON transfer_rules(
            from_stop_id, to_stop_id, selector_specificity DESC, source_row_number);
        CREATE INDEX transfer_rules_to_stop_idx ON transfer_rules(
            to_stop_id, from_stop_id, selector_specificity DESC, source_row_number);
        CREATE INDEX transfer_rules_from_trip_idx ON transfer_rules(
            from_trip_id, to_trip_id, source_row_number);
        CREATE INDEX transfer_rules_to_trip_idx ON transfer_rules(
            to_trip_id, from_trip_id, source_row_number);
        CREATE INDEX transfer_rules_from_route_idx ON transfer_rules(
            from_route_id, to_route_id, source_row_number);
        CREATE INDEX transfer_rules_to_route_idx ON transfer_rules(
            to_route_id, from_route_id, source_row_number);
    ''')
    database.commit()
    database.execute('VACUUM')
    if database.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise DatedTransferIndexError('output SQLite integrity check failed')


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
        database_temporary.unlink(missing_ok=True)
        manifest_temporary.unlink(missing_ok=True)
        if database_backup is not None:
            database_backup.unlink(missing_ok=True)
        if manifest_backup is not None:
            manifest_backup.unlink(missing_ok=True)


def build_dated_transfer_index(
        feed_path, expected_feed_sha256, output_path, *, service_date,
        expected_total_rows=None, expected_type_counts=None):
    """Write an atomic transfer-rule SQLite index and deterministic manifest."""
    if not isinstance(service_date, str) or len(service_date) != 10:
        raise DatedTransferIndexError('service_date must be YYYY-MM-DD')
    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = pathlib.Path(f'{output_path}.manifest.json')
    snapshot = database_path = manifest_temporary = None
    database = None
    try:
        snapshot, source_sha256, source_bytes = _snapshot(
            feed_path, expected_feed_sha256, output_path.parent)
        database_path = _temporary_path(output_path)
        database = _create_database(database_path)
        try:
            with zipfile.ZipFile(snapshot) as archive:
                counts, fields = _stream_rules(archive, database)
        except (OSError, zipfile.BadZipFile) as exc:
            raise DatedTransferIndexError(f'unreadable GTFS archive: {exc}') from exc
        _check_expected(counts, expected_total_rows, expected_type_counts)
        metadata = {
            'generator_version': GENERATOR_VERSION,
            'schema_id': SCHEMA_ID,
            'schema_version': str(SCHEMA_VERSION),
            'service_date': service_date,
            'service_date_semantics': 'custom service_id applicability unresolved',
            'source_fields': json.dumps(fields, ensure_ascii=False, separators=(',', ':')),
            'source_sha256': source_sha256,
            **{f'count.{key}': str(value) for key, value in counts.items()},
        }
        _finalize(database, metadata)
        database.close()
        database = None
        manifest = {
            'counts': counts,
            'format': 'sqlite3',
            'generator_version': GENERATOR_VERSION,
            'limitations': [
                'This artifact indexes directed source rules; it does not resolve journeys.',
                'Producer-specific service_id applicability on the reference date is unresolved.',
                'Timed and in-seat rules are preserved as distinct semantics, not walking transfers.',
                'An absent rule is not negative reachability evidence.',
            ],
            'output_bytes': database_path.stat().st_size,
            'output_sha256': _sha256(database_path),
            'schema_id': SCHEMA_ID,
            'schema_version': SCHEMA_VERSION,
            'service_date': service_date,
            'source_bytes': source_bytes,
            'source_fields': fields,
            'source_sha256': source_sha256,
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
            pathlib.Path(f'{database_path}-journal').unlink(missing_ok=True)
        if manifest_temporary is not None:
            manifest_temporary.unlink(missing_ok=True)
        raise
    finally:
        if snapshot is not None:
            snapshot.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', required=True)
    parser.add_argument('--expected-feed-sha256', default=EXPECTED_GTFS_SHA256)
    parser.add_argument('--service-date', default='2026-10-27')
    parser.add_argument('--output', required=True)
    parser.add_argument('--expected-total-rows', type=int, default=EXPECTED_TOTAL_ROWS)
    args = parser.parse_args()
    started = time.monotonic()
    manifest = build_dated_transfer_index(
        args.feed, args.expected_feed_sha256, args.output,
        service_date=args.service_date,
        expected_total_rows=args.expected_total_rows,
        expected_type_counts=EXPECTED_TYPE_COUNTS)
    print(json.dumps({
        **manifest,
        'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'wall_seconds': time.monotonic() - started,
    }, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
