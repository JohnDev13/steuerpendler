"""Tests for the frozen directed GTFS transfer-rule index."""
import hashlib
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'travel'))
import dated_transfer_index as transfer_index


HEADER = ('from_stop_id,to_stop_id,from_route_id,to_route_id,from_trip_id,'
          'to_trip_id,transfer_type,min_transfer_time,service_id\n')


def feed(path, rows, *, duplicate=False, header=HEADER):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('transfers.txt', header + ''.join(rows))
        if duplicate:
            archive.writestr('transfers.txt', header + ''.join(rows))
    return hashlib.sha256(path.read_bytes()).hexdigest()


ROWS = [
    'BUS,RAIL,,,,,2,240,\n',
    'RAIL,BUS,,,,,2,999,\n',
    'BUS,RAIL,R1,R2,,,2,300,\n',
    'BUS,RAIL,R1,R2,T1,,2,360,\n',
    'BUS,RAIL,R1,R2,T1,T2,1,,\n',
    ',,R1,R2,T1,T2,4,,S-DATED\n',
]


class DatedTransferIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = pathlib.Path(self.temporary.name)
        self.source = self.directory / 'feed.zip'
        self.output = self.directory / 'rules.sqlite'
        self.sha = feed(self.source, ROWS)

    def build(self, **changes):
        expected = {'1': 1, '2': 4, '4': 1}
        expected.update(changes.pop('expected_type_counts', {}))
        return transfer_index.build_dated_transfer_index(
            self.source, self.sha, self.output,
            service_date='2026-10-27', expected_total_rows=6,
            expected_type_counts=expected, **changes)

    def query(self, sql, parameters=()):
        database = sqlite3.connect(self.output)
        try:
            return database.execute(sql, parameters).fetchall()
        finally:
            database.close()

    def test_streams_directed_rules_and_preserves_precedence_and_source(self):
        manifest = self.build()
        forward = self.query('''
            SELECT source_row_number, transfer_type, min_transfer_time,
                   selector_specificity, semantic_class
            FROM transfer_rules WHERE from_stop_id=? AND to_stop_id=?
            ORDER BY selector_specificity DESC, source_row_number
        ''', ('BUS', 'RAIL'))
        reverse = self.query('''
            SELECT min_transfer_time FROM transfer_rules
            WHERE from_stop_id=? AND to_stop_id=?
        ''', ('RAIL', 'BUS'))
        self.assertEqual(forward, [
            (6, 1, None, 6, 'timed'),
            (5, 2, 360, 5, 'minimum_time'),
            (4, 2, 300, 3, 'minimum_time'),
            (2, 2, 240, 1, 'minimum_time'),
        ])
        self.assertEqual(reverse, [(999,)])
        self.assertEqual(manifest['counts'], {
            'source_rows': 6, 'transfer_type_1': 1,
            'transfer_type_2': 4, 'transfer_type_4': 1,
            'scope_resolved': 5, 'scope_unresolved': 1,
            'custom_service_unknown': 1,
        })
        source = json.loads(self.query(
            'SELECT source_fields_json FROM transfer_rules WHERE source_row_number=7')[0][0])
        self.assertEqual(source['service_id'], 'S-DATED')
        self.assertEqual(source['transfer_type'], '4')

    def test_service_status_unknown_and_type4_is_in_seat_not_walk(self):
        self.build()
        row = self.query('''
            SELECT semantic_class, service_date_applicability, scope_status,
                   from_trip_id, to_trip_id
            FROM transfer_rules WHERE transfer_type=4
        ''')[0]
        self.assertEqual(row, ('in_seat', 'unknown_custom_service_id',
                               'unresolved', 'T1', 'T2'))
        self.assertNotIn('walk', row)

    def test_staufen_direction_has_exact_240_second_rule(self):
        self.build()
        self.assertEqual(self.query('''
            SELECT min_transfer_time FROM transfer_rules
            WHERE from_stop_id='BUS' AND to_stop_id='RAIL'
              AND transfer_type=2 AND selector_specificity=1
        '''), [(240,)])
        self.assertEqual(self.query('''
            SELECT min_transfer_time FROM transfer_rules
            WHERE from_stop_id='RAIL' AND to_stop_id='BUS'
              AND min_transfer_time=240
        '''), [])

    def test_rejects_malformed_rows_headers_members_classes_numbers_and_selectors(self):
        cases = [
            (['A,B,,,,,3,,\n'], HEADER, 'unsupported transfer_type'),
            (['A,B,,,,,2,-1,\n'], HEADER, 'invalid min_transfer_time'),
            (['A,B,,,T1,,2,10,\n'], HEADER, 'from_trip_id requires from_route_id'),
            (['A,B,R1,R2,T1,T2,1,10,\n'], HEADER,
             'must be empty for transfer_type 1'),
            (['A,B,,,,,2,10,,EXTRA\n'], HEADER, 'unexpected field'),
            (['A,B,,,,,2,10,\n'], HEADER.replace('service_id', 'from_stop_id'), 'duplicate field'),
        ]
        for rows, header, message in cases:
            with self.subTest(message=message):
                source = self.directory / (str(len(message)) + '.zip')
                sha = feed(source, rows, header=header)
                with self.assertRaisesRegex(transfer_index.DatedTransferIndexError, message):
                    transfer_index.build_dated_transfer_index(
                        source, sha, self.output, service_date='2026-10-27')
        duplicate = self.directory / 'duplicate.zip'
        sha = feed(duplicate, ROWS, duplicate=True)
        with self.assertRaisesRegex(transfer_index.DatedTransferIndexError, 'duplicate member'):
            transfer_index.build_dated_transfer_index(
                duplicate, sha, self.output, service_date='2026-10-27')

    def test_count_pin_deterministic_bytes_and_atomic_rollback(self):
        first = self.build()
        old_database = self.output.read_bytes()
        sidecar = pathlib.Path(f'{self.output}.manifest.json')
        old_manifest = sidecar.read_bytes()
        second = self.build()
        self.assertEqual(second, first)
        self.assertEqual(self.output.read_bytes(), old_database)
        self.assertEqual(sidecar.read_bytes(), old_manifest)
        with self.assertRaisesRegex(transfer_index.DatedTransferIndexError, 'row count mismatch'):
            transfer_index.build_dated_transfer_index(
                self.source, self.sha, self.output, service_date='2026-10-27',
                expected_total_rows=7)
        self.assertEqual(self.output.read_bytes(), old_database)
        self.assertEqual(sidecar.read_bytes(), old_manifest)

        real_replace = transfer_index.os.replace
        def fail_manifest(source, destination):
            if pathlib.Path(destination) == sidecar:
                raise OSError('injected publish failure')
            return real_replace(source, destination)
        with mock.patch.object(transfer_index.os, 'replace', side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, 'injected publish failure'):
                self.build()
        self.assertEqual(self.output.read_bytes(), old_database)
        self.assertEqual(sidecar.read_bytes(), old_manifest)
        self.assertEqual(list(self.directory.glob('.*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
