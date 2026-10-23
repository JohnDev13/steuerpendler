"""Hash-pinned, bounded GTFS adapter for a tiny exact-trip whitelist.

This diagnostic proves only an itinerary over caller-selected trips on one date.
It is not a route authority, a complete timetable search, or a fastest-route
proof. Large GTFS tables are streamed and only selected stop-time rows are kept.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import pathlib
import resource
import time
import zipfile

from exact_itinerary import DatedTransferResolver, find_itinerary
from gtfs_events import ScheduledEvent
from primitives import gtfs_seconds


MAX_TRIPS = 4


class DatedTripSliceError(ValueError):
    """The selected source slice cannot be resolved exactly and safely."""


def _sha256(path):
    with open(path, 'rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _rows(archive, name, required_fields, *, optional=False):
    if name not in archive.namelist():
        if optional:
            return
        raise DatedTripSliceError(f'missing {name}')
    try:
        with archive.open(name) as raw, io.TextIOWrapper(
                raw, encoding='utf-8-sig', newline='') as text:
            reader = csv.DictReader(text)
            fields = set(reader.fieldnames or ())
            missing = required_fields - fields
            if missing:
                raise DatedTripSliceError(
                    f'invalid {name}: missing field {sorted(missing)[0]}')
            yield from reader
    except (csv.Error, UnicodeError, KeyError) as exc:
        raise DatedTripSliceError(f'invalid {name}: {exc}') from exc


def _validate_inputs(service_day, trip_ids, origin_stop_id, destination_stop_id,
                     max_elapsed_seconds, direct_only):
    if not isinstance(service_day, dt.date):
        raise DatedTripSliceError('service day must be a date')
    if not isinstance(trip_ids, (list, tuple)) or not trip_ids:
        raise DatedTripSliceError('one to four exact trip IDs are required')
    if len(trip_ids) > MAX_TRIPS:
        raise DatedTripSliceError(f'at most {MAX_TRIPS} trip IDs are allowed')
    if any(not isinstance(value, str) or not value for value in trip_ids):
        raise DatedTripSliceError('trip IDs must be nonempty strings')
    if len(set(trip_ids)) != len(trip_ids):
        raise DatedTripSliceError('duplicate trip ID in whitelist')
    if not all(isinstance(value, str) and value
               for value in (origin_stop_id, destination_stop_id)):
        raise DatedTripSliceError('origin and destination child stop IDs are required')
    if (type(max_elapsed_seconds) is not int
            or not 0 <= max_elapsed_seconds <= 1800):
        raise DatedTripSliceError('maximum elapsed seconds must be from 0 to 1800')
    if type(direct_only) is not bool:
        raise DatedTripSliceError('direct_only must be a boolean')


def _selected_trips(archive, wanted, counts):
    selected = {}
    required = {'trip_id', 'service_id', 'route_id'}
    for row in _rows(archive, 'trips.txt', required):
        counts['trips'] += 1
        trip_id = row['trip_id']
        if trip_id not in wanted:
            continue
        if trip_id in selected:
            raise DatedTripSliceError(f'duplicate selected trip in trips.txt: {trip_id}')
        if not row['service_id'] or not row['route_id']:
            raise DatedTripSliceError(f'incomplete metadata for selected trip: {trip_id}')
        selected[trip_id] = {
            'route_id': row['route_id'],
            'service_id': row['service_id'],
            'direction_id': row.get('direction_id', ''),
        }
    missing = sorted(wanted - set(selected))
    if missing:
        raise DatedTripSliceError(f'missing selected trip in trips.txt: {missing[0]}')
    return selected


def _active_services(archive, day, service_ids, counts):
    date = day.strftime('%Y%m%d')
    weekday = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday',
               'saturday', 'sunday')[day.weekday()]
    active = set()
    base_seen = set()
    required = {'service_id', weekday, 'start_date', 'end_date'}
    for row in _rows(archive, 'calendar.txt', required, optional=True) or ():
        counts['calendar'] += 1
        service = row['service_id']
        if service not in service_ids:
            continue
        if service in base_seen:
            raise DatedTripSliceError(f'duplicate selected service in calendar.txt: {service}')
        base_seen.add(service)
        if row[weekday] not in {'0', '1'}:
            raise DatedTripSliceError(f'invalid weekday for selected service: {service}')
        try:
            start = dt.datetime.strptime(row['start_date'], '%Y%m%d').date()
            end = dt.datetime.strptime(row['end_date'], '%Y%m%d').date()
        except ValueError as exc:
            raise DatedTripSliceError(f'invalid calendar date for service {service}') from exc
        if start > end:
            raise DatedTripSliceError(f'inverted calendar range for service {service}')
        if start <= day <= end and row[weekday] == '1':
            active.add(service)

    provenance = {service: 'base_calendar' for service in active}
    exception_seen = set()
    required = {'service_id', 'date', 'exception_type'}
    for row in _rows(archive, 'calendar_dates.txt', required, optional=True) or ():
        counts['calendar_dates'] += 1
        service = row['service_id']
        if service not in service_ids or row['date'] != date:
            continue
        key = (service, date)
        if key in exception_seen:
            raise DatedTripSliceError(
                f'duplicate selected service/date in calendar_dates.txt: {service}')
        exception_seen.add(key)
        if row['exception_type'] == '1':
            active.add(service)
            provenance[service] = 'exception_added'
        elif row['exception_type'] == '2':
            active.discard(service)
            provenance.pop(service, None)
        else:
            raise DatedTripSliceError(
                f'invalid exception_type for selected service: {service}')
    return active, provenance


def _reject_frequencies(archive, wanted, counts):
    required = {'trip_id', 'start_time', 'end_time', 'headway_secs', 'exact_times'}
    for row in _rows(archive, 'frequencies.txt', required, optional=True) or ():
        counts['frequencies'] += 1
        if row['trip_id'] in wanted:
            exact = row['exact_times'] or '0'
            if exact not in {'0', '1'}:
                raise DatedTripSliceError(
                    f'invalid frequency exact_times for selected trip {row["trip_id"]}')
            raise DatedTripSliceError(
                f'frequency template for selected trip {row["trip_id"]} '
                f'(exact_times={exact}) is unresolved')


def _selected_stop_times(archive, wanted, counts):
    selected = {trip_id: [] for trip_id in wanted}
    required = {'trip_id', 'arrival_time', 'departure_time', 'stop_id', 'stop_sequence'}
    for row in _rows(archive, 'stop_times.txt', required):
        counts['stop_times'] += 1
        trip_id = row['trip_id']
        if trip_id not in selected:
            continue
        try:
            sequence = int(row['stop_sequence'])
            arrival_seconds = gtfs_seconds(row['arrival_time'])
            departure_seconds = gtfs_seconds(row['departure_time'])
        except (TypeError, ValueError) as exc:
            raise DatedTripSliceError(
                f'malformed stop time for selected trip {trip_id}') from exc
        if sequence < 0 or not row['stop_id']:
            raise DatedTripSliceError(f'malformed stop time for selected trip {trip_id}')
        pickup = row.get('pickup_type', '') or '0'
        drop_off = row.get('drop_off_type', '') or '0'
        if pickup not in {'0', '1', '2', '3'} or drop_off not in {'0', '1', '2', '3'}:
            raise DatedTripSliceError(f'invalid pickup/drop-off for selected trip {trip_id}')
        if pickup in {'2', '3'} or drop_off in {'2', '3'}:
            raise DatedTripSliceError(
                f'conditional pickup/drop-off is unresolved for selected trip {trip_id}')
        if row.get('timepoint', '') == '0':
            raise DatedTripSliceError(f'timepoint=0 for selected trip {trip_id}')
        selected[trip_id].append({
            'arrival_time': row['arrival_time'],
            'arrival_seconds': arrival_seconds,
            'departure_time': row['departure_time'],
            'departure_seconds': departure_seconds,
            'drop_off_type': drop_off,
            'pickup_type': pickup,
            'stop_id': row['stop_id'],
            'stop_sequence': sequence,
        })

    for trip_id, rows in selected.items():
        if len(rows) < 2:
            raise DatedTripSliceError(f'selected trip has fewer than two stops: {trip_id}')
        rows.sort(key=lambda row: row['stop_sequence'])
        if len({row['stop_sequence'] for row in rows}) != len(rows):
            raise DatedTripSliceError(f'duplicate stop_sequence for selected trip {trip_id}')
        prior_departure = None
        for row in rows:
            if row['arrival_seconds'] > row['departure_seconds']:
                raise DatedTripSliceError(f'arrival after departure for selected trip {trip_id}')
            if prior_departure is not None and row['arrival_seconds'] < prior_departure:
                raise DatedTripSliceError(f'nonmonotonic chronology for selected trip {trip_id}')
            prior_departure = row['departure_seconds']
    return selected


def _selected_stops(archive, stop_ids, counts):
    selected = {}
    parent_rows = {}
    seen_ids = set()
    required = {'stop_id', 'stop_name', 'location_type', 'parent_station'}
    for row in _rows(archive, 'stops.txt', required):
        counts['stops'] += 1
        stop_id = row['stop_id']
        if not stop_id:
            raise DatedTripSliceError('empty stop_id in stops.txt')
        if stop_id in seen_ids:
            raise DatedTripSliceError(f'duplicate stop_id in stops.txt: {stop_id}')
        seen_ids.add(stop_id)
        if stop_id in stop_ids:
            selected[stop_id] = {
                'stop_name': row['stop_name'],
                'location_type': row['location_type'] or '0',
                'parent_station': row['parent_station'],
            }
        if stop_id in {value.get('parent_station') for value in selected.values()}:
            parent_rows[stop_id] = row
        # Parents may precede their children, so retain only station rows cheaply.
        if (row['location_type'] or '0') == '1':
            parent_rows[stop_id] = row
    missing = sorted(stop_ids - set(selected))
    if missing:
        raise DatedTripSliceError(f'unknown stop in selected stop_times: {missing[0]}')
    for stop_id, row in selected.items():
        if row['location_type'] != '0':
            raise DatedTripSliceError(f'selected stop is not a child stop: {stop_id}')
        parent = row['parent_station']
        if not parent or parent not in parent_rows:
            raise DatedTripSliceError(f'unresolved parent mapping for selected stop: {stop_id}')
        parent = parent_rows[parent]
        if (parent['location_type'] or '0') != '1' or parent['parent_station']:
            raise DatedTripSliceError(f'invalid parent mapping for selected stop: {stop_id}')
    return selected


def _transfer_rows(archive, counts, endpoint_ids, trip_ids, route_ids):
    rows = []
    required = {'from_stop_id', 'to_stop_id', 'transfer_type'}
    for number, row in enumerate(_rows(archive, 'transfers.txt', required), 1):
        counts['transfers'] += 1
        stop_optional = row['transfer_type'] in {'4', '5'}
        from_stop = row.get('from_stop_id', '')
        to_stop = row.get('to_stop_id', '')
        if ((from_stop not in endpoint_ids and not (stop_optional and not from_stop))
                or (to_stop not in endpoint_ids and not (stop_optional and not to_stop))):
            continue
        if (row.get('from_trip_id', '') not in {'', *trip_ids}
                or row.get('to_trip_id', '') not in {'', *trip_ids}
                or row.get('from_route_id', '') not in {'', *route_ids}
                or row.get('to_route_id', '') not in {'', *route_ids}):
            continue
        normalized = dict(row)
        normalized['source_row_number'] = number
        rows.append(normalized)
    return rows


def _events(stop_times):
    events = []
    for trip_id in sorted(stop_times):
        rows = stop_times[trip_id]
        for origin, destination in zip(rows, rows[1:]):
            events.append(ScheduledEvent(
                trip_id=trip_id,
                from_stop_id=origin['stop_id'],
                to_stop_id=destination['stop_id'],
                from_stop_sequence=origin['stop_sequence'],
                to_stop_sequence=destination['stop_sequence'],
                departure_time=origin['departure_time'],
                arrival_time=destination['arrival_time'],
                departure_seconds=origin['departure_seconds'],
                arrival_seconds=destination['arrival_seconds'],
                board_allowed=origin['pickup_type'] != '1',
                alight_allowed=destination['drop_off_type'] != '1',
            ))
    return events


def _event_payload(event):
    return {
        'alight_allowed': event.alight_allowed,
        'arrival_seconds': event.arrival_seconds,
        'arrival_time': event.arrival_time,
        'departure_seconds': event.departure_seconds,
        'departure_time': event.departure_time,
        'board_allowed': event.board_allowed,
        'from_stop_id': event.from_stop_id,
        'from_stop_sequence': event.from_stop_sequence,
        'to_stop_id': event.to_stop_id,
        'to_stop_sequence': event.to_stop_sequence,
        'trip_id': event.trip_id,
    }


def _source_provenance(provenance, source_row_numbers):
    marker = 'transfers.txt row '
    if not provenance or marker not in provenance:
        return provenance
    prefix, tail = provenance.split(marker, 1)
    number, separator, rest = tail.partition(' ')
    if not number.isdigit() or int(number) not in source_row_numbers:
        return provenance
    return (f'{prefix}{marker}{source_row_numbers[int(number)]}'
            f'{separator}{rest}')


def _itinerary_payload(itinerary, source_row_numbers):
    if itinerary is None:
        return None
    return {
        'arrival_seconds': itinerary.arrival_seconds,
        'elapsed_seconds': itinerary.elapsed_seconds,
        'first_board_seconds': itinerary.first_board_seconds,
        'transfer_count': itinerary.transfer_count,
        'transfers': [{
            'available_seconds': transfer.available_seconds,
            'from_stop_id': transfer.from_stop_id,
            'minimum_seconds': transfer.seconds,
            'provenance': _source_provenance(
                transfer.provenance, source_row_numbers),
            'to_stop_id': transfer.to_stop_id,
        } for transfer in itinerary.transfers],
        'trip_ids': [event.trip_id for event in itinerary.transit_legs],
        'events': [_event_payload(event) for event in itinerary.transit_legs],
    }


def extract_dated_trip_slice(feed_path, expected_sha256, service_day, trip_ids, *,
                             origin_stop_id, destination_stop_id,
                             max_elapsed_seconds=1200, direct_only=False):
    """Extract selected dated trips and search only their exact scheduled events."""
    _validate_inputs(service_day, trip_ids, origin_stop_id, destination_stop_id,
                     max_elapsed_seconds, direct_only)
    feed_path = pathlib.Path(feed_path)
    source_hash = _sha256(feed_path)
    if source_hash != expected_sha256:
        raise DatedTripSliceError('GTFS SHA-256 mismatch')

    wanted = set(trip_ids)
    counts = {name: 0 for name in (
        'stops', 'trips', 'calendar', 'calendar_dates', 'frequencies',
        'stop_times', 'transfers')}
    try:
        with zipfile.ZipFile(feed_path) as archive:
            trips = _selected_trips(archive, wanted, counts)
            active, provenance = _active_services(
                archive, service_day,
                {row['service_id'] for row in trips.values()}, counts)
            inactive = sorted(trip_id for trip_id, row in trips.items()
                              if row['service_id'] not in active)
            if inactive:
                raise DatedTripSliceError(f'inactive selected trip: {inactive[0]}')
            _reject_frequencies(archive, wanted, counts)
            stop_times = _selected_stop_times(archive, wanted, counts)
            stop_ids = {row['stop_id'] for rows in stop_times.values() for row in rows}
            stops = _selected_stops(archive, stop_ids, counts)
            endpoint_ids = stop_ids | {
                row['parent_station'] for row in stops.values()
            }
            transfer_rows = _transfer_rows(
                archive, counts, endpoint_ids, wanted,
                {row['route_id'] for row in trips.values()})
    except (OSError, zipfile.BadZipFile) as exc:
        raise DatedTripSliceError(f'unreadable GTFS archive: {exc}') from exc

    if origin_stop_id not in stop_ids:
        raise DatedTripSliceError('origin child is absent from selected trips')
    if destination_stop_id not in stop_ids:
        raise DatedTripSliceError('destination child is absent from selected trips')

    for trip_id, row in trips.items():
        row['service_provenance'] = provenance[row['service_id']]
    events = _events(stop_times)
    stop_parents = {stop_id: row['parent_station'] for stop_id, row in stops.items()}
    resolver_rows = [
        {key: value for key, value in row.items() if key != 'source_row_number'}
        for row in transfer_rows
    ]
    source_row_numbers = {
        index: row['source_row_number']
        for index, row in enumerate(transfer_rows, 1)
    }
    resolver = DatedTransferResolver(
        resolver_rows, stop_parents,
        {trip_id: row['route_id'] for trip_id, row in trips.items()})

    # Fail rather than silently treating an unresolved selected trip change as
    # forbidden. Prohibited and insufficient rules are resolved negative edges.
    for arriving in events:
        for departing in events:
            if (arriving.trip_id == departing.trip_id
                    or not arriving.alight_allowed
                    or not departing.board_allowed
                    or departing.departure_seconds < arriving.arrival_seconds
                    or departing.departure_seconds - arriving.arrival_seconds
                    > max_elapsed_seconds):
                continue
            result = resolver.resolve(arriving, departing)
            if (result.status == 'unresolved'
                    and result.provenance not in {
                        'no_applicable_rule_for_distinct_parents',
                        'stop_parent_identity_not_evidenced',
                    }):
                raise DatedTripSliceError(
                    f'unresolved transfer {arriving.trip_id}->{departing.trip_id}: '
                    f'{_source_provenance(result.provenance, source_row_numbers)}')

    itinerary = find_itinerary(
        events, {}, {origin_stop_id}, {destination_stop_id},
        max_elapsed_seconds=max_elapsed_seconds, direct_only=direct_only,
        transfer_resolver=resolver)
    return {
        'direct_only': direct_only,
        'events': [_event_payload(event) for event in events],
        'itinerary': _itinerary_payload(itinerary, source_row_numbers),
        'limitations': [
            'Only the caller-provided exact trip whitelist was searched.',
            'No residential access, destination egress, or national coverage was evaluated.',
            'A positive is feasible source-backed evidence, not a fastest-route proof.',
            'A missing itinerary is not evidence that the municipality is unreachable.',
        ],
        'max_elapsed_seconds': max_elapsed_seconds,
        'origin_stop_id': origin_stop_id,
        'destination_stop_id': destination_stop_id,
        'selected_stop_times': stop_times,
        'selected_stops': stops,
        'selected_trips': dict(sorted(trips.items())),
        'service_date': service_day.isoformat(),
        'source_sha256': source_hash,
        'source_table_counts': counts,
        'transfer_rows': transfer_rows,
        'trip_whitelist': list(trip_ids),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--service-date', required=True)
    parser.add_argument('--trip-id', action='append', required=True)
    parser.add_argument('--origin-stop-id', required=True)
    parser.add_argument('--destination-stop-id', required=True)
    parser.add_argument('--max-elapsed-seconds', type=int, default=1200)
    parser.add_argument('--direct-only', action='store_true')
    parser.add_argument('--result')
    args = parser.parse_args()
    try:
        day = dt.date.fromisoformat(args.service_date)
    except ValueError as exc:
        raise DatedTripSliceError(f'invalid service date: {exc}') from exc
    started = time.monotonic()
    payload = extract_dated_trip_slice(
        args.feed, args.expected_sha256, day, args.trip_id,
        origin_stop_id=args.origin_stop_id,
        destination_stop_id=args.destination_stop_id,
        max_elapsed_seconds=args.max_elapsed_seconds,
        direct_only=args.direct_only)
    if args.result:
        result_path = pathlib.Path(args.result)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + '\n',
            encoding='utf-8')
    itinerary = payload['itinerary']
    report = {
        'direct_only': args.direct_only,
        'elapsed_seconds': None if itinerary is None else itinerary['elapsed_seconds'],
        'itinerary_found': itinerary is not None,
        'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'source_sha256': payload['source_sha256'],
        'source_table_counts': payload['source_table_counts'],
        'transfer_count': None if itinerary is None else itinerary['transfer_count'],
        'trip_ids': None if itinerary is None else itinerary['trip_ids'],
        'wall_seconds': time.monotonic() - started,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
