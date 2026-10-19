"""Synthetic GTFS event extraction tests; no Swiss timetable data."""
import csv
import datetime as dt
import io
import pathlib
import sys
import tempfile
import unittest
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
