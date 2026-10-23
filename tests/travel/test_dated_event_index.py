"""Tests for the bounded, dated active stop-call index builder."""
import csv
import hashlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'travel'))

import dated_event_index as events


SOURCE_SHA = 'a' * 64
SERVICE_DATE = '2026-10-27'


def _csv(fields, rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def active_database(path):
    database = sqlite3.connect(path)
    database.executescript('''
        PRAGMA application_id = 0x53504154;
        PRAGMA user_version = 1;
        CREATE TABLE trips (
            trip_id TEXT PRIMARY KEY,
            route_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            schedule_type TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;
    ''')
    database.executemany('INSERT INTO trips VALUES (?, ?, ?, ?)', [
        ('FIXED', 'R1', 'S1', 'fixed_scheduled'),
        ('FREQ', 'R2', 'S2', 'frequency_template_exact_times_0'),
    ])
    database.executemany('INSERT INTO metadata VALUES (?, ?)', [
        ('schema_version', '1'),
        ('service_date', SERVICE_DATE),
        ('source_sha256', SOURCE_SHA),
    ])
    database.commit()
    database.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def feed(path, change=None, *, include_timepoint=True):
    rows = [
        {'trip_id': 'INACTIVE', 'arrival_time': '01:00:00',
         'departure_time': '01:00:00', 'stop_id': 'X', 'stop_sequence': '1',
         'pickup_type': '0', 'drop_off_type': '0', 'timepoint': '1'},
        {'trip_id': 'FIXED', 'arrival_time': '06:30:00',
         'departure_time': '06:30:00', 'stop_id': 'A', 'stop_sequence': '1',
         'pickup_type': '1', 'drop_off_type': '0', 'timepoint': '1'},
        {'trip_id': 'FIXED', 'arrival_time': '', 'departure_time': '',
         'stop_id': 'B', 'stop_sequence': '2', 'pickup_type': '0',
         'drop_off_type': '1', 'timepoint': '0'},
        {'trip_id': 'FIXED', 'arrival_time': '06:40:00',
         'departure_time': '06:41:00', 'stop_id': 'C', 'stop_sequence': '3',
         'pickup_type': '0', 'drop_off_type': '0', 'timepoint': ''},
        {'trip_id': 'FREQ', 'arrival_time': '07:00:00',
         'departure_time': '07:00:00', 'stop_id': 'D', 'stop_sequence': '1',
         'pickup_type': '', 'drop_off_type': '', 'timepoint': '1'},
        {'trip_id': 'FREQ', 'arrival_time': '07:10:00',
         'departure_time': '07:10:00', 'stop_id': 'E', 'stop_sequence': '2',
         'pickup_type': '0', 'drop_off_type': '0', 'timepoint': '1'},
    ]
    if change:
        change(rows)
    fields = [
        'trip_id', 'arrival_time', 'departure_time', 'stop_id',
        'stop_sequence', 'pickup_type', 'drop_off_type',
    ]
    if include_timepoint:
        fields.append('timepoint')
    else:
        for row in rows:
            row.pop('timepoint')
    text = _csv(fields, rows)
    member = zipfile.ZipInfo('stop_times.txt', date_time=(2026, 10, 23, 0, 0, 0))
    member.compress_type = zipfile.ZIP_DEFLATED
    member.external_attr = 0o600 << 16
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(member, text)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DatedEventIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = pathlib.Path(self.temporary.name)
        self.feed = self.directory / 'feed.zip'
        self.active = self.directory / 'active.sqlite'
        self.output = self.directory / 'events.sqlite'
        self.active_sha = active_database(self.active)

    def build(self, change=None, **kwargs):
        feed_sha = feed(self.feed, change)
        database = sqlite3.connect(self.active)
        database.execute(
            "UPDATE metadata SET value = ? WHERE key = 'source_sha256'",
            (feed_sha,))
        database.commit()
        database.close()
        self.active_sha = hashlib.sha256(self.active.read_bytes()).hexdigest()
        manifest = events.build_dated_event_index(
            self.feed, feed_sha, self.active, self.active_sha, self.output,
            expected_source_rows=6, expected_active_stop_calls=5,
            **kwargs)
        return manifest, feed_sha

    def rows(self):
        database = sqlite3.connect(self.output)
        try:
            return database.execute('''
                SELECT source_row_number, trip_id, stop_sequence,
                       arrival_seconds, departure_seconds, stop_id,
                       pickup_type, drop_off_type, timepoint,
                       event_time_status, route_id, service_id, schedule_type
                FROM stop_calls ORDER BY source_row_number
            ''').fetchall()
        finally:
            database.close()

    def test_retains_every_active_call_permissions_and_source_classes(self):
        manifest, feed_sha = self.build()
        self.assertEqual(self.rows(), [
            (3, 'FIXED', 1, 23400, 23400, 'A', 1, 0, 1,
             'exact', 'R1', 'S1', 'fixed_scheduled'),
            (4, 'FIXED', 2, None, None, 'B', 0, 1, 0,
             'non_exact', 'R1', 'S1', 'fixed_scheduled'),
            (5, 'FIXED', 3, 24000, 24060, 'C', 0, 0, 1,
             'exact', 'R1', 'S1', 'fixed_scheduled'),
            (6, 'FREQ', 1, 25200, 25200, 'D', 0, 0, 1,
             'frequency_template', 'R2', 'S2',
             'frequency_template_exact_times_0'),
            (7, 'FREQ', 2, 25800, 25800, 'E', 0, 0, 1,
             'frequency_template', 'R2', 'S2',
             'frequency_template_exact_times_0'),
        ])
        self.assertEqual(manifest['parsed_source_sha256'], feed_sha)
        self.assertEqual(manifest['active_trip_source_sha256'], self.active_sha)
        self.assertEqual(manifest['schema_id'], events.SCHEMA_ID)
        self.assertEqual(manifest['counts'], {
            'active_stop_calls': 5,
            'active_trips': 2,
            'active_trips_with_stop_calls': 2,
            'exact_stop_calls': 2,
            'fixed_scheduled_stop_calls': 3,
            'frequency_template_stop_calls': 2,
            'non_exact_stop_calls': 1,
            'source_stop_time_rows': 6,
        })
        sidecar = pathlib.Path(f'{self.output}.manifest.json')
        self.assertEqual(json.loads(sidecar.read_text()), manifest)
        self.assertEqual(manifest['output_sha256'], hashlib.sha256(self.output.read_bytes()).hexdigest())
        database = sqlite3.connect(self.output)
        try:
            self.assertEqual(database.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            metadata = dict(database.execute('SELECT key, value FROM metadata'))
        finally:
            database.close()
        self.assertEqual(metadata['schema_id'], events.SCHEMA_ID)
        self.assertEqual(metadata['parsed_source_sha256'], feed_sha)

    def test_source_shape_without_timepoint_defaults_fixed_calls_to_exact(self):
        # The frozen Swiss source has no optional timepoint column. GTFS defines
        # its omitted value as 1; frequency clocks must still remain templates.
        def supply_all_clocks(rows):
            rows[2] = {
                **rows[2], 'arrival_time': '06:35:00',
                'departure_time': '06:35:00',
            }

        feed_sha = feed(
            self.feed, supply_all_clocks, include_timepoint=False)
        database = sqlite3.connect(self.active)
        database.execute(
            "UPDATE metadata SET value = ? WHERE key = 'source_sha256'",
            (feed_sha,))
        database.commit()
        database.close()
        self.active_sha = hashlib.sha256(self.active.read_bytes()).hexdigest()

        manifest = events.build_dated_event_index(
            self.feed, feed_sha, self.active, self.active_sha, self.output,
            expected_source_rows=6, expected_active_stop_calls=5)

        rows = self.rows()
        self.assertEqual([row[8] for row in rows], [1, 1, 1, 1, 1])
        self.assertEqual(
            [row[9] for row in rows],
            ['exact', 'exact', 'exact',
             'frequency_template', 'frequency_template'])
        self.assertEqual(manifest['counts']['non_exact_stop_calls'], 0)
        self.assertEqual(manifest['counts']['exact_stop_calls'], 3)

    def test_bytes_are_deterministic(self):
        first, _ = self.build()
        database_bytes = self.output.read_bytes()
        manifest_bytes = pathlib.Path(f'{self.output}.manifest.json').read_bytes()
        second, _ = self.build()
        self.assertEqual(second, first)
        self.assertEqual(self.output.read_bytes(), database_bytes)
        self.assertEqual(pathlib.Path(f'{self.output}.manifest.json').read_bytes(), manifest_bytes)

    def test_hashes_and_active_metadata_must_match(self):
        feed_sha = feed(self.feed)
        with self.assertRaisesRegex(events.DatedEventIndexError, 'active-trip SHA-256 mismatch'):
            events.build_dated_event_index(
                self.feed, feed_sha, self.active, '0' * 64, self.output)
        self.assertFalse(self.output.exists())

        with self.assertRaisesRegex(events.DatedEventIndexError, 'GTFS SHA-256 mismatch'):
            events.build_dated_event_index(
                self.feed, '0' * 64, self.active, self.active_sha, self.output)
        self.assertFalse(self.output.exists())

    def test_duplicate_sequence_invalid_time_permission_and_source_class_fail(self):
        cases = [
            (lambda rows: rows.__setitem__(2, {**rows[2], 'stop_sequence': '1'}),
             'duplicate stop_sequence'),
            (lambda rows: rows.__setitem__(1, {**rows[1], 'arrival_time': 'bad'}),
             'invalid arrival_time'),
            (lambda rows: rows.__setitem__(1, {**rows[1], 'pickup_type': '4'}),
             'invalid pickup_type'),
        ]
        for change, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(events.DatedEventIndexError, message):
                    self.build(change)
                self.assertFalse(self.output.exists())

        database = sqlite3.connect(self.active)
        database.execute("UPDATE trips SET schedule_type = 'invented' WHERE trip_id = 'FIXED'")
        database.commit()
        database.close()
        self.active_sha = hashlib.sha256(self.active.read_bytes()).hexdigest()
        with self.assertRaisesRegex(events.DatedEventIndexError, 'invalid schedule_type'):
            self.build()

    def test_nonmonotonic_chronology_and_exact_missing_clock_fail(self):
        def backwards(rows):
            rows[3] = {**rows[3], 'arrival_time': '06:20:00',
                       'departure_time': '06:20:00'}
        with self.assertRaisesRegex(events.DatedEventIndexError, 'nonmonotonic chronology'):
            self.build(backwards)

        def missing_exact(rows):
            rows[1] = {**rows[1], 'arrival_time': ''}
        with self.assertRaisesRegex(events.DatedEventIndexError, 'exact stop call has missing time'):
            self.build(missing_exact)

    def test_count_or_missing_trip_disagreement_preserves_previous_pair(self):
        self.build()
        old_database = self.output.read_bytes()
        sidecar = pathlib.Path(f'{self.output}.manifest.json')
        old_manifest = sidecar.read_bytes()
        feed_sha = feed(self.feed)
        with self.assertRaisesRegex(events.DatedEventIndexError, 'active stop-call count mismatch'):
            events.build_dated_event_index(
                self.feed, feed_sha, self.active, self.active_sha, self.output,
                expected_source_rows=6, expected_active_stop_calls=99)
        self.assertEqual(self.output.read_bytes(), old_database)
        self.assertEqual(sidecar.read_bytes(), old_manifest)

        def remove_frequency(rows):
            rows[:] = [row for row in rows if row['trip_id'] != 'FREQ']
        feed_sha = feed(self.feed, remove_frequency)
        database = sqlite3.connect(self.active)
        database.execute(
            "UPDATE metadata SET value = ? WHERE key = 'source_sha256'",
            (feed_sha,))
        database.commit()
        database.close()
        self.active_sha = hashlib.sha256(self.active.read_bytes()).hexdigest()
        with self.assertRaisesRegex(events.DatedEventIndexError, 'active trip has fewer than two stop calls'):
            events.build_dated_event_index(
                self.feed, feed_sha, self.active, self.active_sha, self.output,
                expected_source_rows=4)
        self.assertEqual(self.output.read_bytes(), old_database)
        self.assertEqual(sidecar.read_bytes(), old_manifest)

    def test_duplicate_stop_times_member_preserves_previous_pair(self):
        self.build()
        old_database = self.output.read_bytes()
        sidecar = pathlib.Path(f'{self.output}.manifest.json')
        old_manifest = sidecar.read_bytes()

        with zipfile.ZipFile(self.feed) as archive:
            original = archive.read('stop_times.txt')
        conflicting = original.replace(b'INACTIVE', b'CONFLICT', 1)
        with zipfile.ZipFile(self.feed, 'a') as archive:
            archive.writestr('stop_times.txt', conflicting)
        feed_sha = hashlib.sha256(self.feed.read_bytes()).hexdigest()
        database = sqlite3.connect(self.active)
        database.execute(
            "UPDATE metadata SET value = ? WHERE key = 'source_sha256'",
            (feed_sha,))
        database.commit()
        database.close()
        self.active_sha = hashlib.sha256(self.active.read_bytes()).hexdigest()

        with self.assertRaisesRegex(
                events.DatedEventIndexError, 'duplicate member.*stop_times.txt'):
            events.build_dated_event_index(
                self.feed, feed_sha, self.active, self.active_sha, self.output)
        self.assertEqual(self.output.read_bytes(), old_database)
        self.assertEqual(sidecar.read_bytes(), old_manifest)
        self.assertEqual(list(self.directory.glob('.*.tmp')), [])

    def test_capped_snapshot_and_publish_failure_leave_no_partial_artifact(self):
        feed_sha = feed(self.feed)
        with mock.patch.object(events, 'MAX_GTFS_BYTES', self.feed.stat().st_size - 1):
            with self.assertRaisesRegex(events.DatedEventIndexError, 'byte limit'):
                events.build_dated_event_index(
                    self.feed, feed_sha, self.active, self.active_sha, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.directory.glob('.*.snapshot.*')), [])

        self.build()
        old_database = self.output.read_bytes()
        sidecar = pathlib.Path(f'{self.output}.manifest.json')
        old_manifest = sidecar.read_bytes()
        real_replace = events.os.replace

        def fail_sidecar(source, destination):
            if pathlib.Path(destination) == sidecar:
                raise OSError('injected publish failure')
            return real_replace(source, destination)

        with mock.patch.object(events.os, 'replace', side_effect=fail_sidecar):
            with self.assertRaisesRegex(OSError, 'injected publish failure'):
                self.build(lambda rows: rows.__setitem__(1, {
                    **rows[1], 'stop_id': 'CHANGED'}))
        self.assertEqual(self.output.read_bytes(), old_database)
        self.assertEqual(sidecar.read_bytes(), old_manifest)


if __name__ == '__main__':
    unittest.main()
