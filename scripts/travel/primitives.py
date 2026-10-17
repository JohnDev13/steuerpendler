"""Testable T3 primitives, NOT a router or full §6.7 release validator.

All IDs/geometry assignments supplied by a caller must come from independently
validated real inputs. These helpers neither download inputs nor emit site data.
"""
import math
import re


class ValidationError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ValidationError(message)


def _integer(value):
    return type(value) is int


def active_services(day, calendar, exceptions):
    """GTFS calendar + calendar_dates (not holiday-policy approval)."""
    date = day.strftime('%Y%m%d')
    weekday = ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')[day.weekday()]
    active, seen = set(), set()
    for row in calendar:
        service = row['service_id']
        _require(service not in seen, 'duplicate calendar service')
        seen.add(service)
        _require(row[weekday] in ('0','1'), 'invalid calendar weekday')
        if row['start_date'] <= date <= row['end_date'] and row[weekday] == '1':
            active.add(service)
    seen.clear()
    for row in exceptions:
        key = (row['service_id'], row['date'])
        _require(key not in seen, 'duplicate service/day exception')
        _require(row['exception_type'] in ('1','2'), 'invalid exception type')
        seen.add(key)
        if row['date'] == date:
            if row['exception_type'] == '1':
                active.add(row['service_id'])
            else:
                active.discard(row['service_id'])
    return active


def gtfs_seconds(value):
    """Support extended GTFS hours without wrapping to next reference day."""
    _require(isinstance(value, str) and bool(re.fullmatch(r'[0-9]{2,}:[0-5][0-9]:[0-5][0-9]', value)),
             'invalid GTFS HH:MM:SS')
    hours, minutes, seconds = map(int, value.split(':'))
    return hours * 3600 + minutes * 60 + seconds


def rank_stations(stops, trips, stop_times, services, inside_stop_ids):
    """Aggregate active platform departures inside one preassigned polygon.

    Caller supplies validated spatial membership (not inferred from parent location).
    Counts each (trip, sequence) once, rejects conflicting duplicates, returns
    descending count/lexicographic station ID. Fallback/walk selection is not done.
    """
    from collections import Counter
    counts, seen = Counter(), {}
    _require(inside_stop_ids <= set(stops), 'unknown spatially assigned stop')
    for row in stop_times:
        trip, stop = row['trip_id'], row['stop_id']
        _require(trip in trips and stop in stops, 'unknown trip/stop')
        try:
            sequence = int(row['stop_sequence'])
        except (ValueError, TypeError):
            raise ValidationError('invalid stop_sequence') from None
        _require(sequence >= 0, 'invalid stop_sequence')
        key, value = (trip,sequence), (stop,row['departure_time'])
        if key in seen:
            _require(seen[key] == value, 'conflicting duplicate trip/stop_sequence')
            continue
        seen[key] = value
        seconds = gtfs_seconds(row['departure_time'])
        if trips[trip] not in services or stop not in inside_stop_ids or not 21600 <= seconds <= 32400:
            continue
        parent = stops[stop].get('parent_station') or stop
        _require(parent in stops, 'unknown parent station')
        counts[parent] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def pair_qa(origin_parent, destination_parent, distance_km, minutes):
    """§8 conservative speed policy; caller must measure WGS84 parent distance.

    Never suppresses rows or approves exceptions. 'review' still needs evidence;
    'blocked' requires independent pair/service/feed evidence + owner approval.
    """
    _require(type(distance_km) in (float,int) and math.isfinite(distance_km)
             and distance_km >= 0 and _integer(minutes) and minutes >= 0,
             'invalid distance/minutes')
    same = origin_parent == destination_parent
    if same or minutes == 0:
        _require(same and minutes == 0 and distance_km == 0,
                 'zero only for coincident shared-parent endpoints')
        return 'passed'
    speed = 60 * max(0, distance_km - 0.1) / (minutes + 1)
    return 'blocked' if speed > 150 else 'review' if speed > 100 else 'passed'


def reachable(walk, minutes, max_walk, max_time, count_walk):
    """Independent §8 filter oracle; no exemption for workplace/self zero."""
    return (walk is not None and minutes is not None and walk <= max_walk
            and (minutes + walk if count_walk else minutes) <= max_time)


def validate_dataset(access, workplaces, authority_ids, release_id):
    """Validate in-memory §6.4/6.5 structure, completeness and shared zeros.

    Does not establish provenance, routing accuracy, file sizes, manifest hashes,
    geodesic speeds, 95% coverage, named stations, or official acceptance.
    """
    _require(bool(authority_ids) and all(re.fullmatch(r'[1-9][0-9]*', x)
             for x in authority_ids), 'nonempty canonical BFS authority required')
    _require(isinstance(release_id, str) and bool(re.fullmatch(r'[0-9a-f]{64}', release_id)),
             'invalid expected release ID')
    expected_meta = {'schemaVersion': 1, 'releaseId': release_id}

    def metadata(value):
        _require(isinstance(value, dict), 'object required')
        meta = value.get('meta', {})
        _require(isinstance(meta, dict) and type(meta.get('schemaVersion')) is int
                 and all(meta.get(k) == v for k, v in expected_meta.items()),
                 'schema/release mismatch')

    metadata(access)
    entries = access.get('gemeinden')
    _require(isinstance(entries, dict) and set(entries) == authority_ids,
             'access IDs differ from authority')
    usable = set()
    for bfs, entry in entries.items():
        if entry is None:
            continue
        _require(isinstance(entry, list) and len(entry) == 3, 'invalid access row')
        station, name, walk = entry
        _require(isinstance(station, str) and bool(station) and isinstance(name, str)
                 and bool(name) and _integer(walk) and 0 <= walk <= 60, 'invalid access values')
        usable.add(bfs)
    _require(isinstance(workplaces, dict) and set(workplaces) == usable,
             'missing/extra workplace files (including null-access files)')
    for bfs, file in workplaces.items():
        metadata(file)
        _require(_integer(file.get('to')) and file['to'] == int(bfs), 'wrong workplace to')
        rows = file.get('rows')
        _require(isinstance(rows, list), 'rows array required')
        seen, ordered = set(), []
        for row in rows:
            _require(isinstance(row, list) and len(row) == 2, 'invalid travel row')
            home, minutes = row
            _require(_integer(home) and str(home) in usable and home not in seen,
                     'unknown, duplicate or null-access origin')
            _require(_integer(minutes) and 0 <= minutes <= 60, 'invalid integer minutes')
            same = entries[str(home)][0] == entries[bfs][0]
            _require((minutes == 0) == same, 'same-parent zeros required; other zeros forbidden')
            seen.add(home)
            ordered.append((minutes, home))
        _require(ordered == sorted(ordered), 'rows not sorted by minutes/BFS')
        shared = {int(k) for k in usable if entries[k][0] == entries[bfs][0]}
        _require(shared <= seen, 'missing self/shared-parent row')
