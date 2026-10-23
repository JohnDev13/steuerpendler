"""Tests for exact dated adjacent ride connections and first-board events."""
import hashlib
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'travel'))

import dated_connections as connections


SERVICE_DATE = '2026-10-27'


def input_database(path, rows=None, *, schema_id='steuerpendler.dated-active-stop-calls.v1',
                   service_date=SERVICE_DATE):
    if rows is None:
        rows = [
            # A trip beginning before the horizon retains its later adjacent edge.
            ('START', 1, 2, 22500, 22500, 'PRE', 0, 0, 1, 'exact', 'R0', 'S', 'fixed_scheduled'),
            ('START', 5, 3, 23400, 23400, 'START', 0, 0, 1, 'exact', 'R0', 'S', 'fixed_scheduled'),
            ('START', 9, 4, 24000, 24000, 'AFTER', 0, 0, 1, 'exact', 'R0', 'S', 'fixed_scheduled'),
            # Sequence gaps and no-pickup/no-drop-off calls do not break through riding.
            ('THROUGH', 10, 5, 23400, 23400, 'A', 0, 0, 1, 'exact', 'R1', 'S', 'fixed_scheduled'),
            ('THROUGH', 30, 6, 23700, 23760, 'B', 1, 1, 1, 'exact', 'R1', 'S', 'fixed_scheduled'),
            ('THROUGH', 80, 7, 24000, 24000, 'C', 0, 0, 1, 'exact', 'R1', 'S', 'fixed_scheduled'),
            # Inclusive latest first board and horizon arrival.
            ('BOUND', 1, 8, 30600, 30600, 'D', 0, 0, 1, 'exact', 'R2', 'S', 'fixed_scheduled'),
            ('BOUND', 2, 9, 32400, 32400, 'E', 0, 0, 1, 'exact', 'R2', 'S', 'fixed_scheduled'),
            # Conditional pickup connections remain rides but not candidate boards.
            ('COND2', 1, 10, 25200, 25200, 'P2', 2, 0, 1, 'exact', 'R3', 'S', 'fixed_scheduled'),
            ('COND2', 2, 11, 25500, 25500, 'P2X', 0, 0, 1, 'exact', 'R3', 'S', 'fixed_scheduled'),
            ('COND3', 1, 12, 25800, 25800, 'P3', 3, 0, 1, 'exact', 'R4', 'S', 'fixed_scheduled'),
            ('COND3', 2, 13, 26100, 26100, 'P3X', 0, 0, 1, 'exact', 'R4', 'S', 'fixed_scheduled'),
            # Each unresolved pair is quarantined rather than bridged.
            ('INEXACT', 1, 14, 25200, 25200, 'I', 0, 0, 0, 'non_exact', 'R5', 'S', 'fixed_scheduled'),
            ('INEXACT', 2, 15, 25500, 25500, 'IX', 0, 0, 1, 'exact', 'R5', 'S', 'fixed_scheduled'),
            ('FREQ', 1, 16, 25200, 25200, 'F', 0, 0, 1, 'frequency_template', 'R6', 'S', 'frequency_template_exact_times_0'),
            ('FREQ', 2, 17, 25500, 25500, 'FX', 0, 0, 1, 'frequency_template', 'R6', 'S', 'frequency_template_exact_times_0'),
            ('MISSING', 1, 18, 25200, None, 'M', 0, 0, 0, 'non_exact', 'R7', 'S', 'fixed_scheduled'),
            ('MISSING', 2, 19, 25500, 25500, 'MX', 0, 0, 1, 'exact', 'R7', 'S', 'fixed_scheduled'),
            ('BACKWARD', 1, 20, 25200, 25800, 'Z', 0, 0, 1, 'exact', 'R8', 'S', 'fixed_scheduled'),
            ('BACKWARD', 2, 21, 25500, 25500, 'ZX', 0, 0, 1, 'exact', 'R8', 'S', 'fixed_scheduled'),
        ]
    database = sqlite3.connect(path)
    database.executescript('''
        PRAGMA application_id = 0x53504556;
        PRAGMA user_version = 1;
        CREATE TABLE stop_calls (
            trip_id TEXT NOT NULL,
            stop_sequence INTEGER NOT NULL,
            source_row_number INTEGER NOT NULL UNIQUE,
            arrival_seconds INTEGER,
            departure_seconds INTEGER,
            stop_id TEXT NOT NULL,
            pickup_type INTEGER NOT NULL,
            drop_off_type INTEGER NOT NULL,
            timepoint INTEGER NOT NULL,
            event_time_status TEXT NOT NULL,
            route_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            schedule_type TEXT NOT NULL,
            PRIMARY KEY (trip_id, stop_sequence)
        ) WITHOUT ROWID;
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;
    ''')
    database.executemany('INSERT INTO stop_calls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)
    database.executemany('INSERT INTO metadata VALUES (?, ?)', [
        ('schema_id', schema_id),
        ('schema_version', '1'),
        ('service_date', service_date),
        ('parsed_source_sha256', 'feed-' + 'a' * 59),
    ])
    database.commit()
    database.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DatedConnectionsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = pathlib.Path(self.temporary.name)
        self.source = self.directory / 'calls.sqlite'
        self.output = self.directory / 'connections.sqlite'
        self.source_sha = input_database(self.source)

    def build(self, **kwargs):
        return connections.build_dated_connections(
            self.source, self.source_sha, self.output,
            expected_service_date=SERVICE_DATE, **kwargs)

    def query(self, sql):
        database = sqlite3.connect(self.output)
        try:
            return database.execute(sql).fetchall()
        finally:
            database.close()

    def test_builds_adjacent_exact_rides_and_candidate_first_boards(self):
        manifest = self.build()
        rides = self.query('''
            SELECT trip_id, from_stop_sequence, to_stop_sequence,
                   from_source_row_number, to_source_row_number,
                   departure_seconds, arrival_seconds, from_stop_id, to_stop_id,
                   from_pickup_type, from_drop_off_type,
                   to_pickup_type, to_drop_off_type, route_id
            FROM ride_connections ORDER BY trip_id, from_stop_sequence
        ''')
        self.assertEqual(rides, [
            ('BOUND', 1, 2, 8, 9, 30600, 32400, 'D', 'E', 0, 0, 0, 0, 'R2'),
            ('COND2', 1, 2, 10, 11, 25200, 25500, 'P2', 'P2X', 2, 0, 0, 0, 'R3'),
            ('COND3', 1, 2, 12, 13, 25800, 26100, 'P3', 'P3X', 3, 0, 0, 0, 'R4'),
            ('START', 5, 9, 3, 4, 23400, 24000, 'START', 'AFTER', 0, 0, 0, 0, 'R0'),
            ('THROUGH', 10, 30, 5, 6, 23400, 23700, 'A', 'B', 0, 0, 1, 1, 'R1'),
            ('THROUGH', 30, 80, 6, 7, 23760, 24000, 'B', 'C', 1, 1, 0, 0, 'R1'),
        ])
        boards = self.query('''
            SELECT c.trip_id, c.from_stop_sequence, c.departure_seconds, c.from_stop_id
            FROM first_board_events AS b
            JOIN ride_connections AS c ON c.connection_id = b.connection_id
            ORDER BY c.trip_id, c.from_stop_sequence
        ''')
        self.assertEqual(boards, [
            ('BOUND', 1, 30600, 'D'),
            ('START', 5, 23400, 'START'),
            ('THROUGH', 10, 23400, 'A'),
        ])
        self.assertEqual(manifest['counts'], {
            'candidate_first_board_events': 3,
            'first_board_conditional_unresolved': 2,
            'first_board_pickup_prohibited': 1,
            'outside_horizon_pairs': 1,
            'quarantined_chronology_pairs': 1,
            'quarantined_frequency_pairs': 1,
            'quarantined_missing_time_pairs': 1,
            'quarantined_non_exact_pairs': 1,
            'ride_connections': 6,
            'source_adjacent_pairs': 11,
            'source_stop_calls': 20,
        })
        self.assertEqual(manifest['source_sha256'], self.source_sha)
        self.assertEqual(manifest['service_date'], SERVICE_DATE)
        self.assertEqual(manifest['schema_id'], connections.SCHEMA_ID)
        self.assertEqual(
            manifest['output_sha256'], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(
            json.loads(pathlib.Path(f'{self.output}.manifest.json').read_text()), manifest)

    def test_indexes_metadata_integrity_and_deterministic_bytes(self):
        first = self.build()
        output_bytes = self.output.read_bytes()
        manifest_bytes = pathlib.Path(f'{self.output}.manifest.json').read_bytes()
        second = self.build()
        self.assertEqual(second, first)
        self.assertEqual(self.output.read_bytes(), output_bytes)
        self.assertEqual(pathlib.Path(f'{self.output}.manifest.json').read_bytes(), manifest_bytes)
        database = sqlite3.connect(self.output)
        try:
            self.assertEqual(database.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            indexes = {row[1] for row in database.execute("PRAGMA index_list('ride_connections')")}
            metadata = dict(database.execute('SELECT key, value FROM metadata'))
        finally:
            database.close()
        self.assertIn('ride_connections_departure_from_idx', indexes)
        self.assertIn('ride_connections_trip_sequence_idx', indexes)
        self.assertEqual(metadata['source_sha256'], self.source_sha)
        self.assertEqual(metadata['schema_id'], connections.SCHEMA_ID)

    def test_wrong_pin_metadata_and_corrupt_sqlite_are_rejected(self):
        with self.assertRaisesRegex(connections.DatedConnectionsError, 'SHA-256 mismatch'):
            connections.build_dated_connections(
                self.source, '0' * 64, self.output,
                expected_service_date=SERVICE_DATE)
        self.assertFalse(self.output.exists())

        wrong = self.directory / 'wrong.sqlite'
        wrong_sha = input_database(wrong, schema_id='wrong')
        with self.assertRaisesRegex(connections.DatedConnectionsError, 'schema_id mismatch'):
            connections.build_dated_connections(
                wrong, wrong_sha, self.output, expected_service_date=SERVICE_DATE)
        wrong.unlink()
        wrong_sha = input_database(wrong, service_date='2026-10-28')
        with self.assertRaisesRegex(connections.DatedConnectionsError, 'service date mismatch'):
            connections.build_dated_connections(
                wrong, wrong_sha, self.output, expected_service_date=SERVICE_DATE)

        corrupt = self.directory / 'corrupt.sqlite'
        corrupt.write_bytes(b'not sqlite')
        corrupt_sha = hashlib.sha256(corrupt.read_bytes()).hexdigest()
        with self.assertRaisesRegex(connections.DatedConnectionsError, 'invalid source SQLite'):
            connections.build_dated_connections(
                corrupt, corrupt_sha, self.output, expected_service_date=SERVICE_DATE)

    def test_publish_failure_restores_previous_database_and_manifest(self):
        self.build()
        old_database = self.output.read_bytes()
        sidecar = pathlib.Path(f'{self.output}.manifest.json')
        old_manifest = sidecar.read_bytes()
        real_replace = connections.os.replace

        def fail_manifest(source, destination):
            if pathlib.Path(destination) == sidecar:
                raise OSError('injected manifest publish failure')
            return real_replace(source, destination)

        with mock.patch.object(connections.os, 'replace', side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, 'injected manifest publish failure'):
                self.build()
        self.assertEqual(self.output.read_bytes(), old_database)
        self.assertEqual(sidecar.read_bytes(), old_manifest)
        self.assertEqual(list(self.directory.glob('.*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
