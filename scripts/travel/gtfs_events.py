"""Exact scheduled GTFS stop-to-stop event extraction prototype.

This module does not search routes, model transfers, or approve a reference day.
It rejects frequency-based or explicitly approximate times rather than inventing
exact departures.
"""
import csv
import datetime as dt
import io
from dataclasses import dataclass
import zipfile

from primitives import active_services, gtfs_seconds


class GtfsEventError(ValueError):
    """The feed cannot produce bounded exact scheduled events."""


class InexactFrequencyError(GtfsEventError):
    """A frequency row describes non-exact departures."""


class UnsupportedExactFrequencyError(GtfsEventError):
    """Exact frequency expansion is outside this prototype."""


class InexactStopTimeError(GtfsEventError):
    """A stop time is explicitly approximate."""


@dataclass(frozen=True)
class ScheduledEvent:
    trip_id: str
    from_stop_id: str
    to_stop_id: str
    from_stop_sequence: int
    to_stop_sequence: int
    departure_time: str
    arrival_time: str
    departure_seconds: int
    arrival_seconds: int


def _table(archive, name, required=False):
    if name not in archive.namelist():
        if required:
            raise GtfsEventError(f'missing {name}')
        return []
    text = archive.read(name).decode('utf-8-sig')
    try:
        return list(csv.DictReader(io.StringIO(text)))
    except csv.Error as exc:
        raise GtfsEventError(f'invalid {name}: {exc}') from exc


def _dated_service_exceptions(archive, day, service_ids):
    """Stream only exceptions that can affect selected trips on ``day``."""
    name = 'calendar_dates.txt'
    if name not in archive.namelist():
        return []
    date = day.strftime('%Y%m%d')
    try:
        with archive.open(name) as raw, io.TextIOWrapper(
                raw, encoding='utf-8-sig', newline='') as text:
            rows = csv.DictReader(text)
            required = {'service_id', 'date', 'exception_type'}
            if rows.fieldnames is not None and not required <= set(rows.fieldnames):
                missing = sorted(required - set(rows.fieldnames))
                raise GtfsEventError(
                    f'invalid {name}: missing field {missing[0]}')
            return [row for row in rows
                    if row.get('service_id') in service_ids and row.get('date') == date]
    except (csv.Error, UnicodeError) as exc:
        raise GtfsEventError(f'invalid {name}: {exc}') from exc


def _stream_selected_stop_times(archive, active_trips):
    """Retain parsed stop times only for active trips, while checking every row."""
    name = 'stop_times.txt'
    try:
        with archive.open(name) as raw, io.TextIOWrapper(
                raw, encoding='utf-8-sig', newline='') as text:
            for row in csv.DictReader(text):
                if row.get('timepoint') == '0':
                    raise InexactStopTimeError(
                        'stop_times timepoint=0 is not exact')
                trip_id = row.get('trip_id')
                if trip_id not in active_trips:
                    continue
                try:
                    sequence = int(row['stop_sequence'])
                    stop_id = row['stop_id']
                    arrival = row['arrival_time']
                    departure = row['departure_time']
                    arrival_seconds = gtfs_seconds(arrival)
                    departure_seconds = gtfs_seconds(departure)
                except (KeyError, TypeError, ValueError) as exc:
                    raise GtfsEventError(
                        f'invalid stop time for trip {trip_id}: {exc}') from exc
                active_trips[trip_id].append((
                    sequence, stop_id, arrival, departure,
                    arrival_seconds, departure_seconds))
    except csv.Error as exc:
        raise GtfsEventError(f'invalid {name}: {exc}') from exc


def _service_ids(day, calendar, exceptions):
    try:
        return active_services(day, calendar, exceptions)
    except (KeyError, TypeError, ValueError) as exc:
        raise GtfsEventError(f'invalid service calendar: {exc}') from exc


def scheduled_events(feed_path, service_day):
    """Return adjacent scheduled stop events for trips active on ``service_day``.

    GTFS clock strings are retained verbatim while numeric second fields support
    comparison without wrapping values above 24:00:00.
    """
    if not isinstance(service_day, dt.date):
        raise GtfsEventError('service_day must be a date')
    try:
        with zipfile.ZipFile(feed_path) as archive:
            calendar = _table(archive, 'calendar.txt')
            trips = _table(archive, 'trips.txt', required=True)
            trip_service_ids = {row.get('service_id') for row in trips}
            exceptions = _dated_service_exceptions(
                archive, service_day, trip_service_ids)
            if 'stop_times.txt' not in archive.namelist():
                raise GtfsEventError('missing stop_times.txt')
            frequencies = _table(archive, 'frequencies.txt')

            for row in frequencies:
                if row.get('exact_times') == '1':
                    raise UnsupportedExactFrequencyError(
                        'frequencies exact_times=1 expansion is unsupported')
                raise InexactFrequencyError(
                    'frequencies exact_times=0 is not exact')

            services = _service_ids(service_day, calendar, exceptions)
            active_trips = {}
            for row in trips:
                try:
                    trip_id, service_id = row['trip_id'], row['service_id']
                except KeyError as exc:
                    raise GtfsEventError(
                        f'missing trips field: {exc.args[0]}') from exc
                if trip_id in active_trips:
                    raise GtfsEventError(f'duplicate trip_id: {trip_id}')
                if service_id in services:
                    active_trips[trip_id] = []

            _stream_selected_stop_times(archive, active_trips)
    except (OSError, zipfile.BadZipFile, UnicodeError) as exc:
        raise GtfsEventError(f'invalid GTFS archive: {exc}') from exc

    events = []
    for trip_id, rows in active_trips.items():
        rows.sort(key=lambda row: row[0])
        if len({row[0] for row in rows}) != len(rows):
            raise GtfsEventError(f'duplicate stop_sequence for trip {trip_id}')
        for origin, destination in zip(rows, rows[1:]):
            if destination[4] < origin[5]:
                raise GtfsEventError(f'event arrives before departure for trip {trip_id}')
            events.append(ScheduledEvent(
                trip_id=trip_id,
                from_stop_id=origin[1],
                to_stop_id=destination[1],
                from_stop_sequence=origin[0],
                to_stop_sequence=destination[0],
                departure_time=origin[3],
                arrival_time=destination[2],
                departure_seconds=origin[5],
                arrival_seconds=destination[4],
            ))
    return events


def eligible_first_board_departures(events, origin_stop_ids,
                                      start_time='06:30:00', end_time='08:30:00'):
    """Select events departing eligible origin platforms in an inclusive window."""
    try:
        start, end = gtfs_seconds(start_time), gtfs_seconds(end_time)
    except ValueError as exc:
        raise GtfsEventError(f'invalid boarding window: {exc}') from exc
    if start > end:
        raise GtfsEventError('boarding window starts after it ends')
    origins = set(origin_stop_ids)
    return [event for event in events
            if event.from_stop_id in origins
            and start <= event.departure_seconds <= end]
