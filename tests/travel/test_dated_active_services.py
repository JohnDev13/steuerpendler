"""Tests for the bounded, dated active-trip manifest builder."""
import csv
import datetime as dt
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

import dated_active_services as active


DAY = dt.date(2026, 10, 27)


def _csv(fields, rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def fixture(path, change=None):
    calendar_fields = [
        'service_id', 'monday', 'tuesday', 'wednesday', 'thursday',
        'friday', 'saturday', 'sunday', 'start_date', 'end_date',
    ]
    tables = {
        'calendar.txt': _csv(calendar_fields, [
            {'service_id': 'BASE', 'monday': '0', 'tuesday': '1',
             'wednesday': '0', 'thursday': '0', 'friday': '0',
             'saturday': '0', 'sunday': '0', 'start_date': '20260101',
             'end_date': '20261231'},
            {'service_id': 'REMOVED', 'monday': '0', 'tuesday': '1',
             'wednesday': '0', 'thursday': '0', 'friday': '0',
             'saturday': '0', 'sunday': '0', 'start_date': '20260101',
             'end_date': '20261231'},
            {'service_id': 'OUTSIDE', 'monday': '0', 'tuesday': '1',
             'wednesday': '0', 'thursday': '0', 'friday': '0',
             'saturday': '0', 'sunday': '0', 'start_date': '20250101',
             'end_date': '20251231'},
        ]),
        'calendar_dates.txt': _csv(
            ['service_id', 'date', 'exception_type'], [
                {'service_id': 'ADDED', 'date': '20261027', 'exception_type': '1'},
                {'service_id': 'REMOVED', 'date': '20261027', 'exception_type': '2'},
                {'service_id': 'OUTSIDE', 'date': '20261028', 'exception_type': '1'},
            ]),
        'trips.txt': _csv(['route_id', 'service_id', 'trip_id'], [
            {'route_id': 'R2', 'service_id': 'ADDED', 'trip_id': 'T2'},
            {'route_id': 'RX', 'service_id': 'OUTSIDE', 'trip_id': 'TX'},
            {'route_id': 'R1', 'service_id': 'BASE', 'trip_id': 'T1'},
            {'route_id': 'RR', 'service_id': 'REMOVED', 'trip_id': 'TR'},
            {'route_id': 'R3', 'service_id': 'BASE', 'trip_id': 'T3'},
        ]),
        'frequencies.txt': _csv(
            ['trip_id', 'start_time', 'end_time', 'headway_secs', 'exact_times'], [
                {'trip_id': 'T2', 'start_time': '06:00:00', 'end_time': '07:00:00',
                 'headway_secs': '600', 'exact_times': '0'},
                {'trip_id': 'T3', 'start_time': '07:00:00', 'end_time': '08:00:00',
                 'headway_secs': '900', 'exact_times': '1'},
            ]),
    }
    if change:
        change(tables)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in tables.items():
            archive.writestr(name, text)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ActiveServicesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = pathlib.Path(self.temporary.name)
        self.feed = self.directory / 'feed.zip'
        self.output = self.directory / 'active.sqlite'

    def build(self, change=None, **kwargs):
        pin = fixture(self.feed, change)
        manifest = active.build_active_trip_manifest(
            self.feed, pin, DAY, self.output,
            expected_active_trips=3,
            expected_active_services=2,
            expected_frequency_templates=2,
            **kwargs)
        return manifest, pin

    def rows(self):
        database = sqlite3.connect(self.output)
        try:
            return database.execute(
                'SELECT trip_id, route_id, service_id, schedule_type '
                'FROM trips ORDER BY trip_id').fetchall()
        finally:
            database.close()

    def test_exact_date_exceptions_inactive_trips_and_frequency_types(self):
        manifest, pin = self.build()
        self.assertEqual(self.rows(), [
            ('T1', 'R1', 'BASE', 'fixed_scheduled'),
            ('T2', 'R2', 'ADDED', 'frequency_template_exact_times_0'),
            ('T3', 'R3', 'BASE', 'frequency_template_exact_times_1'),
        ])
        self.assertEqual(manifest['source_sha256'], pin)
        self.assertEqual(manifest['service_date'], '2026-10-27')
        self.assertEqual(manifest['counts']['active_trip_ids'], 3)
        self.assertEqual(manifest['counts']['active_services_with_trips'], 2)
        self.assertEqual(manifest['counts']['active_frequency_templates'], 2)
        self.assertEqual(manifest['counts']['inactive_trip_rows'], 2)
        self.assertEqual(manifest['status_counts'], {
            'fixed_scheduled': 1,
            'frequency_template_exact_times_0': 1,
            'frequency_template_exact_times_1': 1,
        })
        self.assertEqual(manifest['schema_version'], 1)
        self.assertEqual(manifest['generator_version'], active.GENERATOR_VERSION)
        self.assertEqual(manifest['output_bytes'], self.output.stat().st_size)
        self.assertEqual(manifest['output_sha256'], hashlib.sha256(self.output.read_bytes()).hexdigest())
        sidecar = json.loads(self.output.with_suffix('.sqlite.manifest.json').read_text())
        self.assertEqual(sidecar, manifest)

    def test_output_bytes_are_deterministic(self):
        first, _ = self.build()
        first_bytes = self.output.read_bytes()
        first_manifest = self.output.with_suffix('.sqlite.manifest.json').read_bytes()
        second, _ = self.build()
        self.assertEqual(self.output.read_bytes(), first_bytes)
        self.assertEqual(self.output.with_suffix('.sqlite.manifest.json').read_bytes(), first_manifest)
        self.assertEqual(second, first)

    def test_wrong_source_pin_is_rejected_without_output(self):
        pin = fixture(self.feed)
        with self.assertRaisesRegex(active.ActiveServiceError, 'SHA-256 mismatch'):
            active.build_active_trip_manifest(self.feed, '0' * 64, DAY, self.output)
        self.assertFalse(self.output.exists())
        self.assertNotEqual(pin, '0' * 64)

    def test_source_snapshot_has_an_explicit_size_limit(self):
        pin = fixture(self.feed)
        with mock.patch.object(active, 'MAX_SOURCE_BYTES', self.feed.stat().st_size - 1):
            with self.assertRaisesRegex(active.ActiveServiceError, 'byte limit'):
                active.build_active_trip_manifest(self.feed, pin, DAY, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.directory.glob('.*.snapshot.*')), [])

    def test_replacing_source_after_snapshot_does_not_change_parsed_bytes(self):
        pin = fixture(self.feed)
        replacement = self.directory / 'replacement.zip'

        def replace_trips(tables):
            tables['trips.txt'] = tables['trips.txt'].replace('R1,BASE,T1', 'R9,BASE,T9')

        fixture(replacement, replace_trips)
        real_zip_file = zipfile.ZipFile

        def mutate_original_before_parse(path, *args, **kwargs):
            replacement.replace(self.feed)
            return real_zip_file(path, *args, **kwargs)

        with mock.patch.object(active.zipfile, 'ZipFile', side_effect=mutate_original_before_parse):
            manifest = active.build_active_trip_manifest(
                self.feed, pin, DAY, self.output,
                expected_active_trips=3,
                expected_active_services=2,
                expected_frequency_templates=2)

        self.assertEqual(manifest['source_sha256'], pin)
        self.assertEqual([row[0] for row in self.rows()], ['T1', 'T2', 'T3'])
        self.assertEqual(list(self.directory.glob('.*.snapshot.*')), [])

    def test_duplicate_selected_exception_and_calendar_service_are_rejected(self):
        def duplicate_exception(tables):
            tables['calendar_dates.txt'] += 'ADDED,20261027,2\n'
        with self.assertRaisesRegex(active.ActiveServiceError, 'duplicate service/date'):
            self.build(duplicate_exception)

        def duplicate_calendar(tables):
            tables['calendar.txt'] += tables['calendar.txt'].splitlines(True)[1]
        with self.assertRaisesRegex(active.ActiveServiceError, 'duplicate service'):
            self.build(duplicate_calendar)

    def test_malformed_irrelevant_trip_and_contradictory_frequency_are_rejected(self):
        def malformed_inactive(tables):
            tables['trips.txt'] = tables['trips.txt'].replace('RX,OUTSIDE,TX', ',OUTSIDE,TX')
        with self.assertRaisesRegex(active.ActiveServiceError, 'incomplete trip metadata'):
            self.build(malformed_inactive)

        def contradictory_frequency(tables):
            tables['frequencies.txt'] += 'T2,08:00:00,09:00:00,600,1\n'
        with self.assertRaisesRegex(active.ActiveServiceError, 'contradictory exact_times'):
            self.build(contradictory_frequency)

    def test_duplicate_trip_and_orphan_frequency_are_rejected(self):
        def duplicate_trip(tables):
            tables['trips.txt'] += 'R9,BASE,T1\n'
        with self.assertRaisesRegex(active.ActiveServiceError, 'duplicate trip_id'):
            self.build(duplicate_trip)

        def orphan_frequency(tables):
            tables['frequencies.txt'] += 'MISSING,08:00:00,09:00:00,600,0\n'
        with self.assertRaisesRegex(active.ActiveServiceError, 'unknown trip'):
            self.build(orphan_frequency)

    def test_missing_table_and_malformed_source_rows_are_rejected(self):
        def no_calendar_dates(tables):
            del tables['calendar_dates.txt']
        with self.assertRaisesRegex(active.ActiveServiceError, 'missing calendar_dates.txt'):
            self.build(no_calendar_dates)

        def bad_calendar_date(tables):
            tables['calendar.txt'] = tables['calendar.txt'].replace('20260101', 'bad', 1)
        with self.assertRaisesRegex(active.ActiveServiceError, 'invalid calendar date'):
            self.build(bad_calendar_date)

        def bad_frequency(tables):
            tables['frequencies.txt'] = tables['frequencies.txt'].replace(',600,0', ',0,0', 1)
        with self.assertRaisesRegex(active.ActiveServiceError, 'invalid frequency row'):
            self.build(bad_frequency)

    def test_count_disagreement_rolls_back_existing_outputs(self):
        self.output.write_bytes(b'previous output')
        sidecar = self.output.with_suffix('.sqlite.manifest.json')
        sidecar.write_bytes(b'previous manifest')
        pin = fixture(self.feed)
        with self.assertRaisesRegex(active.ActiveServiceError, 'active trip count mismatch'):
            active.build_active_trip_manifest(
                self.feed, pin, DAY, self.output,
                expected_active_trips=999,
                expected_active_services=2,
                expected_frequency_templates=2)
        self.assertEqual(self.output.read_bytes(), b'previous output')
        self.assertEqual(sidecar.read_bytes(), b'previous manifest')
        self.assertEqual(list(self.directory.glob('.*.tmp')), [])

    def test_manifest_publish_failure_preserves_previous_pair(self):
        previous_manifest, _ = self.build()
        previous_database = self.output.read_bytes()
        sidecar = self.output.with_suffix('.sqlite.manifest.json')
        previous_sidecar = sidecar.read_bytes()

        def change_route(tables):
            tables['trips.txt'] = tables['trips.txt'].replace('R1,BASE,T1', 'R9,BASE,T1')

        pin = fixture(self.feed, change_route)
        real_replace = active.os.replace

        def fail_manifest_publish(source, destination):
            if pathlib.Path(destination) == sidecar:
                raise OSError('injected manifest publish failure')
            return real_replace(source, destination)

        with mock.patch.object(active.os, 'replace', side_effect=fail_manifest_publish):
            with self.assertRaisesRegex(OSError, 'injected manifest publish failure'):
                active.build_active_trip_manifest(
                    self.feed, pin, DAY, self.output,
                    expected_active_trips=3,
                    expected_active_services=2,
                    expected_frequency_templates=2)

        self.assertEqual(self.output.read_bytes(), previous_database)
        self.assertEqual(sidecar.read_bytes(), previous_sidecar)
        self.assertEqual(json.loads(previous_sidecar), previous_manifest)
        self.assertEqual(list(self.directory.glob('.*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
