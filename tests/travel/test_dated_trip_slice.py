"""Bounded dated-trip slice tests using only tiny synthetic GTFS feeds."""
import csv
import datetime as dt
import hashlib
import io
import pathlib
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'travel'))


DAY = dt.date(2026, 10, 27)


def _csv(fieldnames, rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def fixture(path, *, changes=None):
    tables = {
        'stops.txt': _csv(
            ['stop_id', 'stop_name', 'location_type', 'parent_station'], [
                {'stop_id': 'PO', 'stop_name': 'Origin parent', 'location_type': '1', 'parent_station': ''},
                {'stop_id': 'O', 'stop_name': 'Origin child', 'location_type': '0', 'parent_station': 'PO'},
                {'stop_id': 'M', 'stop_name': 'Intermediate', 'location_type': '0', 'parent_station': 'PM'},
                {'stop_id': 'X', 'stop_name': 'Bus', 'location_type': '0', 'parent_station': 'PX'},
                {'stop_id': 'Y', 'stop_name': 'Rail', 'location_type': '0', 'parent_station': 'PY'},
                {'stop_id': 'D', 'stop_name': 'Destination', 'location_type': '0', 'parent_station': 'PD'},
                {'stop_id': 'PM', 'stop_name': 'Middle parent', 'location_type': '1', 'parent_station': ''},
                {'stop_id': 'PX', 'stop_name': 'Bus parent', 'location_type': '1', 'parent_station': ''},
                {'stop_id': 'PY', 'stop_name': 'Rail parent', 'location_type': '1', 'parent_station': ''},
                {'stop_id': 'PD', 'stop_name': 'Destination parent', 'location_type': '1', 'parent_station': ''},
            ]),
        'trips.txt': _csv(['route_id', 'service_id', 'trip_id', 'direction_id'], [
            {'route_id': 'R1', 'service_id': 'S', 'trip_id': 'T1', 'direction_id': '0'},
            {'route_id': 'R2', 'service_id': 'S', 'trip_id': 'T2', 'direction_id': '1'},
        ]),
        'calendar.txt': _csv(
            ['service_id', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
             'saturday', 'sunday', 'start_date', 'end_date'], [
                {'service_id': 'S', 'monday': '0', 'tuesday': '1', 'wednesday': '0',
                 'thursday': '0', 'friday': '0', 'saturday': '0', 'sunday': '0',
                 'start_date': '20260101', 'end_date': '20261231'},
            ]),
        'calendar_dates.txt': _csv(['service_id', 'date', 'exception_type'], []),
        'frequencies.txt': _csv(
            ['trip_id', 'start_time', 'end_time', 'headway_secs', 'exact_times'], []),
        'stop_times.txt': _csv(
            ['trip_id', 'arrival_time', 'departure_time', 'stop_id', 'stop_sequence',
             'pickup_type', 'drop_off_type', 'timepoint'], [
                {'trip_id': 'T1', 'arrival_time': '06:47:00', 'departure_time': '06:47:00',
                 'stop_id': 'O', 'stop_sequence': '1', 'pickup_type': '0', 'drop_off_type': '0', 'timepoint': '1'},
                {'trip_id': 'T1', 'arrival_time': '06:49:00', 'departure_time': '06:50:00',
                 'stop_id': 'M', 'stop_sequence': '2', 'pickup_type': '0', 'drop_off_type': '0', 'timepoint': '1'},
                {'trip_id': 'T1', 'arrival_time': '06:53:00', 'departure_time': '06:53:00',
                 'stop_id': 'X', 'stop_sequence': '3', 'pickup_type': '0', 'drop_off_type': '0', 'timepoint': '1'},
                {'trip_id': 'T2', 'arrival_time': '06:58:00', 'departure_time': '06:58:00',
                 'stop_id': 'Y', 'stop_sequence': '1', 'pickup_type': '0', 'drop_off_type': '0', 'timepoint': '1'},
                {'trip_id': 'T2', 'arrival_time': '07:05:00', 'departure_time': '07:05:00',
                 'stop_id': 'D', 'stop_sequence': '2', 'pickup_type': '0', 'drop_off_type': '0', 'timepoint': '1'},
            ]),
        'transfers.txt': _csv(
            ['from_stop_id', 'to_stop_id', 'transfer_type', 'min_transfer_time',
             'from_route_id', 'to_route_id', 'from_trip_id', 'to_trip_id', 'service_id'], [
                {'from_stop_id': 'X', 'to_stop_id': 'Y', 'transfer_type': '2',
                 'min_transfer_time': '240', 'from_route_id': '', 'to_route_id': '',
                 'from_trip_id': '', 'to_trip_id': '', 'service_id': ''},
            ]),
    }
    if changes:
        changes(tables)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in tables.items():
            archive.writestr(name, text)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(feed, pin, **kwargs):
    import dated_trip_slice as dts
    return dts.extract_dated_trip_slice(
        feed, pin, DAY, ['T1', 'T2'], origin_stop_id='O',
        destination_stop_id='D', max_elapsed_seconds=1200, **kwargs)


class DatedTripSliceTests(unittest.TestCase):
    def make_feed(self, changes=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = pathlib.Path(temporary.name) / 'feed.zip'
        return path, fixture(path, changes=changes)

    def test_source_backed_transfer_with_intermediate_call_is_deterministic(self):
        feed, pin = self.make_feed()
        first = run(feed, pin)
        second = run(feed, pin)
        self.assertEqual(first, second)
        self.assertEqual(first['source_sha256'], pin)
        self.assertEqual(first['itinerary']['elapsed_seconds'], 1080)
        self.assertEqual(first['itinerary']['transfer_count'], 1)
        self.assertEqual(first['itinerary']['trip_ids'], ['T1', 'T1', 'T2'])
        self.assertEqual(first['selected_trips']['T1']['service_provenance'], 'base_calendar')
        self.assertEqual(first['transfer_rows'][0]['source_row_number'], 1)
        self.assertEqual(first['source_table_counts']['stop_times'], 5)
        self.assertEqual(set(first['source_table_counts']), {
            'stops', 'trips', 'calendar', 'calendar_dates', 'frequencies',
            'stop_times', 'transfers'})
        self.assertIsNone(run(feed, pin, direct_only=True)['itinerary'])

    def test_calendar_exception_addition_and_removal_are_exact_date_scoped(self):
        def addition(tables):
            tables['calendar.txt'] = _csv(
                ['service_id', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                 'saturday', 'sunday', 'start_date', 'end_date'], [])
            tables['calendar_dates.txt'] = _csv(
                ['service_id', 'date', 'exception_type'],
                [{'service_id': 'S', 'date': '20261027', 'exception_type': '1'}])
        feed, pin = self.make_feed(addition)
        self.assertEqual(run(feed, pin)['selected_trips']['T1']['service_provenance'],
                         'exception_added')

        def removal(tables):
            tables['calendar_dates.txt'] = _csv(
                ['service_id', 'date', 'exception_type'],
                [{'service_id': 'S', 'date': '20261027', 'exception_type': '2'}])
        feed, pin = self.make_feed(removal)
        import dated_trip_slice as dts
        with self.assertRaisesRegex(dts.DatedTripSliceError, 'inactive selected trip'):
            run(feed, pin)

    def test_wrong_pin_duplicate_or_missing_trip_id_is_rejected(self):
        feed, pin = self.make_feed()
        import dated_trip_slice as dts
        with self.assertRaisesRegex(dts.DatedTripSliceError, 'SHA-256 mismatch'):
            run(feed, '0' * 64)
        with self.assertRaisesRegex(dts.DatedTripSliceError, 'duplicate trip ID'):
            dts.extract_dated_trip_slice(feed, pin, DAY, ['T1', 'T1'],
                                         origin_stop_id='O', destination_stop_id='D')
        with self.assertRaisesRegex(dts.DatedTripSliceError, 'missing selected trip'):
            dts.extract_dated_trip_slice(feed, pin, DAY, ['T1', 'NOPE'],
                                         origin_stop_id='O', destination_stop_id='D')

    def test_frequency_template_and_inexact_timepoint_are_rejected(self):
        def frequency(tables):
            tables['frequencies.txt'] = _csv(
                ['trip_id', 'start_time', 'end_time', 'headway_secs', 'exact_times'],
                [{'trip_id': 'T1', 'start_time': '06:00:00', 'end_time': '07:00:00',
                  'headway_secs': '600', 'exact_times': '0'}])
        feed, pin = self.make_feed(frequency)
        import dated_trip_slice as dts
        with self.assertRaisesRegex(dts.DatedTripSliceError, 'frequency template'):
            run(feed, pin)

        def approximate(tables):
            tables['stop_times.txt'] = tables['stop_times.txt'].replace(
                'T1,06:49:00,06:50:00,M,2,0,0,1',
                'T1,06:49:00,06:50:00,M,2,0,0,0')
        feed, pin = self.make_feed(approximate)
        with self.assertRaisesRegex(dts.DatedTripSliceError, 'timepoint=0'):
            run(feed, pin)

    def test_unknown_stop_and_conditional_pickup_are_rejected(self):
        def unknown(tables):
            tables['stop_times.txt'] = tables['stop_times.txt'].replace(',M,2,', ',UNKNOWN,2,')
        feed, pin = self.make_feed(unknown)
        import dated_trip_slice as dts
        with self.assertRaisesRegex(dts.DatedTripSliceError, 'unknown stop'):
            run(feed, pin)

        def conditional(tables):
            tables['stop_times.txt'] = tables['stop_times.txt'].replace(
                'T2,06:58:00,06:58:00,Y,1,0,0,1',
                'T2,06:58:00,06:58:00,Y,1,2,0,1')
        feed, pin = self.make_feed(conditional)
        with self.assertRaisesRegex(dts.DatedTripSliceError, 'conditional pickup/drop-off'):
            run(feed, pin)

    def test_duplicate_parent_stop_id_is_rejected(self):
        def duplicate_parent(tables):
            tables['stops.txt'] += 'PX,Duplicate bus parent,1,\n'
        feed, pin = self.make_feed(duplicate_parent)
        import dated_trip_slice as dts
        with self.assertRaisesRegex(dts.DatedTripSliceError, 'duplicate stop_id'):
            run(feed, pin)

    def test_alight_only_stop_is_never_used_as_a_departure(self):
        def alight_only(tables):
            tables['stop_times.txt'] = tables['stop_times.txt'].replace(
                'T2,06:58:00,06:58:00,Y,1,0,0,1',
                'T2,06:58:00,06:58:00,Y,1,1,0,1')
        feed, pin = self.make_feed(alight_only)
        payload = run(feed, pin)
        self.assertIsNone(payload['itinerary'])
        departure = next(event for event in payload['events']
                         if event['trip_id'] == 'T2' and event['from_stop_id'] == 'Y')
        self.assertFalse(departure['board_allowed'])

    def test_initial_pickup_and_final_dropoff_permissions_are_required(self):
        cases = (
            ('T1,06:47:00,06:47:00,O,1,0,0,1',
             'T1,06:47:00,06:47:00,O,1,1,0,1'),
            ('T2,07:05:00,07:05:00,D,2,0,0,1',
             'T2,07:05:00,07:05:00,D,2,0,1,1'),
        )
        for old, new in cases:
            with self.subTest(stop_time=new):
                def forbidden_endpoint(tables, old=old, new=new):
                    tables['stop_times.txt'] = tables['stop_times.txt'].replace(old, new)
                feed, pin = self.make_feed(forbidden_endpoint)
                self.assertIsNone(run(feed, pin)['itinerary'])

    def test_transfer_at_no_dropoff_stop_is_forbidden(self):
        def no_dropoff(tables):
            tables['stop_times.txt'] = tables['stop_times.txt'].replace(
                'T1,06:53:00,06:53:00,X,3,0,0,1',
                'T1,06:53:00,06:53:00,X,3,0,1,1')
        feed, pin = self.make_feed(no_dropoff)
        self.assertIsNone(run(feed, pin)['itinerary'])

    def test_no_pickup_at_intermediate_still_allows_through_rider(self):
        def no_pickup(tables):
            tables['stop_times.txt'] = tables['stop_times.txt'].replace(
                'T1,06:49:00,06:50:00,M,2,0,0,1',
                'T1,06:49:00,06:50:00,M,2,1,0,1')
        feed, pin = self.make_feed(no_pickup)
        itinerary = run(feed, pin)['itinerary']
        self.assertIsNotNone(itinerary, 'through rider must stay aboard past no-pickup stop')
        self.assertEqual(itinerary['elapsed_seconds'], 1080)

    def test_no_dropoff_at_intermediate_still_allows_through_rider(self):
        def no_dropoff(tables):
            tables['stop_times.txt'] = tables['stop_times.txt'].replace(
                'T1,06:49:00,06:50:00,M,2,0,0,1',
                'T1,06:49:00,06:50:00,M,2,0,1,1')
        feed, pin = self.make_feed(no_dropoff)
        itinerary = run(feed, pin)['itinerary']
        self.assertIsNotNone(itinerary, 'through rider must stay aboard past no-dropoff stop')
        self.assertEqual(itinerary['elapsed_seconds'], 1080)

    def test_forbidden_transfer_is_directed(self):
        def forbidden(tables):
            tables['transfers.txt'] = tables['transfers.txt'].replace('X,Y,2,240', 'X,Y,3,240')
        feed, pin = self.make_feed(forbidden)
        self.assertIsNone(run(feed, pin)['itinerary'])

        def reverse_only(tables):
            tables['transfers.txt'] += 'Y,X,3,240,,,,,\n'
        feed, pin = self.make_feed(reverse_only)
        self.assertEqual(run(feed, pin)['itinerary']['elapsed_seconds'], 1080)

    def test_conflicting_equally_specific_route_rules_are_unresolved(self):
        def conflict(tables):
            tables['transfers.txt'] += 'X,Y,3,,R1,R2,,,\nX,Y,2,10,R1,R2,,,\n'
        feed, pin = self.make_feed(conflict)
        import dated_trip_slice as dts
        with self.assertRaisesRegex(dts.DatedTripSliceError,
                                    'conflicting equally specific'):
            run(feed, pin)


if __name__ == '__main__':
    unittest.main()
