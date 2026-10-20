"""Synthetic GTFS event extraction tests; no Swiss timetable data."""
import csv
import datetime as dt
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'travel'))
import gtfs_events as ge
from metric_probe import fixture


def rewrite_feed(source, target, changes):
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, 'w') as new:
        names = set(old.namelist()) | set(changes)
        for name in sorted(names):
            value = changes.get(name, old.read(name).decode() if name in old.namelist() else '')
            new.writestr(name, value)


class ScheduledEventTests(unittest.TestCase):
    day = dt.date(2027, 1, 12)  # synthetic service day only

    def _write_minimal_feed(self, path, calendar, trips, stop_times):
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('calendar.txt', calendar)
            archive.writestr('trips.txt', trips)
            archive.writestr('stop_times.txt', stop_times)

    def test_fixture_events_and_inclusive_first_board_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed, _ = fixture(pathlib.Path(tmp))
            events = ge.scheduled_events(feed, self.day)

        direct = {event.trip_id: event for event in events
                  if event.from_stop_id in {'A1', 'A2'} and event.to_stop_id == 'B1'}
        selected = ge.eligible_first_board_departures(events, {'A1', 'A2'})
        selected_ids = {event.trip_id for event in selected}
        self.assertEqual(direct['rare-second'].departure_time, '07:13:17')
        self.assertEqual(direct['rare-second'].arrival_time, '07:15:18')
        self.assertIn('lower-inclusive', selected_ids)
        self.assertIn('upper-inclusive', selected_ids)
        self.assertIn('rare-second', selected_ids)
        self.assertNotIn('outside-before', selected_ids)
        self.assertNotIn('outside-after', selected_ids)

    def test_extended_hours_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            feed, _ = fixture(directory)
            changed = directory / 'extended.gtfs.zip'
            with zipfile.ZipFile(feed) as archive:
                trips = archive.read('trips.txt').decode() + 'DIRECT,SYN,after-midnight\n'
                stop_times = archive.read('stop_times.txt').decode()
            stop_times += ('after-midnight,25:00:00,25:00:00,A1,1\n'
                           'after-midnight,25:05:00,25:05:00,B1,2\n')
            rewrite_feed(feed, changed, {'trips.txt': trips, 'stop_times.txt': stop_times})
            event = next(e for e in ge.scheduled_events(changed, self.day)
                         if e.trip_id == 'after-midnight')
        self.assertEqual((event.departure_time, event.arrival_time), ('25:00:00', '25:05:00'))
        self.assertEqual((event.departure_seconds, event.arrival_seconds), (90000, 90300))

    def test_calendar_dates_are_streamed_and_scoped_to_selected_services_and_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = pathlib.Path(tmp) / 'large-calendar-dates.gtfs.zip'
            calendar = (
                'service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n'
                'BASE,0,1,0,0,0,0,0,20270101,20270131\n'
                'ADD,0,0,0,0,0,0,0,20270101,20270131\n'
                'REMOVE,0,1,0,0,0,0,0,20270101,20270131\n'
                'INACTIVE,0,0,0,0,0,0,0,20270101,20270131\n'
            )
            trips = 'route_id,service_id,trip_id\n' + ''.join(
                f'R,{service},{service.lower()}-trip\n'
                for service in ('BASE', 'ADD', 'REMOVE', 'INACTIVE'))
            stop_times = 'trip_id,arrival_time,departure_time,stop_id,stop_sequence\n' + ''.join(
                f'{service.lower()}-trip,07:00:00,07:00:00,A,1\n'
                f'{service.lower()}-trip,07:05:00,07:05:00,B,2\n'
                for service in ('BASE', 'ADD', 'REMOVE', 'INACTIVE'))
            unrelated = ''.join(
                f'OTHER-{index},20270111,1\nOTHER-{index},20270113,2\n'
                for index in range(10_000))
            calendar_dates = (
                'service_id,date,exception_type\n'
                f'{unrelated}'
                'ADD,20270112,1\n'
                'REMOVE,20270112,2\n'
            )
            with zipfile.ZipFile(feed, 'w') as archive:
                archive.writestr('calendar.txt', calendar)
                archive.writestr('calendar_dates.txt', calendar_dates)
                archive.writestr('trips.txt', trips)
                archive.writestr('stop_times.txt', stop_times)

            original = ge.active_services
            exception_counts = []

            def recording_active_services(day, rows, exceptions):
                exception_counts.append(len(exceptions))
                return original(day, rows, exceptions)

            with mock.patch.object(ge, 'active_services', recording_active_services):
                events = ge.scheduled_events(feed, self.day)

        self.assertEqual(exception_counts, [2])
        self.assertEqual({event.trip_id for event in events}, {'base-trip', 'add-trip'})

    def test_stop_times_are_streamed_and_only_active_rows_are_processed(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = pathlib.Path(tmp) / 'large-stop-times.gtfs.zip'
            calendar = (
                'service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n'
                'ACTIVE,0,1,0,0,0,0,0,20270101,20270131\n'
                'INACTIVE,0,0,0,0,0,0,0,20270101,20270131\n'
            )
            trips = (
                'route_id,service_id,trip_id\n'
                'R,ACTIVE,active-trip\n'
                'R,INACTIVE,inactive-trip\n'
            )
            unrelated = ''.join(
                f'inactive-trip,08:00:00,08:00:00,U{index},{index + 1}\n'
                for index in range(10_000))
            stop_times = (
                'trip_id,arrival_time,departure_time,stop_id,stop_sequence\n'
                f'{unrelated}'
                'active-trip,07:13:17,07:13:17,001,1\n'
                'active-trip,25:05:19,25:05:19,002,2\n'
            )
            self._write_minimal_feed(feed, calendar, trips, stop_times)

            original_table = ge._table
            table_names = []
            parsed_clocks = []

            def recording_table(archive, name, required=False):
                table_names.append(name)
                return original_table(archive, name, required)

            original_seconds = ge.gtfs_seconds

            def recording_seconds(value):
                parsed_clocks.append(value)
                return original_seconds(value)

            with mock.patch.object(ge, '_table', recording_table), \
                    mock.patch.object(ge, 'gtfs_seconds', recording_seconds):
                events = ge.scheduled_events(feed, self.day)

        self.assertNotIn('stop_times.txt', table_names)
        self.assertEqual(parsed_clocks,
                         ['07:13:17', '07:13:17', '25:05:19', '25:05:19'])
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].from_stop_id, events[0].to_stop_id), ('001', '002'))
        self.assertEqual((events[0].departure_seconds, events[0].arrival_seconds),
                         (25997, 90319))

    def test_inactive_timepoint_zero_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = pathlib.Path(tmp) / 'inactive-inexact.gtfs.zip'
            calendar = (
                'service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n'
                'ACTIVE,0,1,0,0,0,0,0,20270101,20270131\n'
                'INACTIVE,0,0,0,0,0,0,0,20270101,20270131\n'
            )
            trips = (
                'route_id,service_id,trip_id\n'
                'R,ACTIVE,active-trip\n'
                'R,INACTIVE,inactive-trip\n'
            )
            stop_times = (
                'trip_id,arrival_time,departure_time,stop_id,stop_sequence,timepoint\n'
                'active-trip,07:00:00,07:00:00,A,1,1\n'
                'active-trip,07:05:00,07:05:00,B,2,1\n'
                'inactive-trip,08:00:00,08:00:00,U,1,0\n'
            )
            self._write_minimal_feed(feed, calendar, trips, stop_times)

            with self.assertRaises(ge.InexactStopTimeError):
                ge.scheduled_events(feed, self.day)

    def test_no_active_trip_yields_no_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = pathlib.Path(tmp) / 'no-active-trip.gtfs.zip'
            calendar = (
                'service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n'
                'INACTIVE,0,0,0,0,0,0,0,20270101,20270131\n'
            )
            trips = 'route_id,service_id,trip_id\nR,INACTIVE,inactive-trip\n'
            stop_times = (
                'trip_id,arrival_time,departure_time,stop_id,stop_sequence\n'
                'inactive-trip,08:00:00,08:00:00,A,1\n'
                'inactive-trip,08:05:00,08:05:00,B,2\n'
            )
            self._write_minimal_feed(feed, calendar, trips, stop_times)

            self.assertEqual(ge.scheduled_events(feed, self.day), [])

    def test_inexact_frequency_and_stop_time_rows_fail_closed(self):
        cases = [
            ('frequencies.txt', 'trip_id,start_time,end_time,headway_secs,exact_times\nslow-7-0,07:00:00,08:00:00,600,0\n',
             ge.InexactFrequencyError),
            ('frequencies.txt', 'trip_id,start_time,end_time,headway_secs,exact_times\nslow-7-0,07:00:00,08:00:00,600,1\n',
             ge.UnsupportedExactFrequencyError),
            ('stop_times.txt', None, ge.InexactStopTimeError),
        ]
        for filename, value, error in cases:
            with self.subTest(filename=filename, error=error.__name__), tempfile.TemporaryDirectory() as tmp:
                directory = pathlib.Path(tmp)
                feed, _ = fixture(directory)
                changed = directory / 'changed.gtfs.zip'
                if filename == 'stop_times.txt':
                    with zipfile.ZipFile(feed) as archive:
                        rows = list(csv.reader(io.StringIO(archive.read(filename).decode())))
                    rows[0].append('timepoint')
                    rows[1].append('0')
                    output = io.StringIO(newline='')
                    csv.writer(output, lineterminator='\n').writerows(rows)
                    value = output.getvalue()
                rewrite_feed(feed, changed, {filename: value})
                with self.assertRaises(error):
                    ge.scheduled_events(changed, self.day)


if __name__ == '__main__':
    unittest.main()
