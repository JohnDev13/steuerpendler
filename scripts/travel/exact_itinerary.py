"""Bounded exact scheduled-itinerary search over synthetic GTFS events.

The search permits any number of vehicle changes over explicitly supplied
directed footpaths. It does not add origin access, destination egress, or pure
walking, and is not itself a source-complete timetable adapter.
"""
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from gtfs_events import GtfsEventError, ScheduledEvent, eligible_first_board_departures
from transfer_rules import TransferResult, resolve_transfer


@dataclass(frozen=True)
class TransferFootpath:
    from_stop_id: str
    to_stop_id: str
    seconds: int
    available_seconds: Optional[int] = None
    provenance: Optional[str] = None


@dataclass(frozen=True)
class DatedTransferResolver:
    """Resolve each exact trip change against the supplied dated GTFS context."""

    rows: Tuple[Mapping[str, object], ...]
    stop_parents: Mapping[str, str]
    trip_route_ids: Mapping[str, str]

    def __init__(self, rows: Iterable[Mapping[str, object]],
                 stop_parents: Mapping[str, str],
                 trip_route_ids: Mapping[str, str]):
        object.__setattr__(self, 'rows', tuple(rows))
        object.__setattr__(self, 'stop_parents', dict(stop_parents))
        object.__setattr__(self, 'trip_route_ids', dict(trip_route_ids))

    def resolve(self, arriving: ScheduledEvent,
                departing: ScheduledEvent) -> TransferResult:
        return resolve_transfer(
            self.rows, self.stop_parents,
            from_stop_id=arriving.to_stop_id,
            to_stop_id=departing.from_stop_id,
            from_trip_id=arriving.trip_id,
            to_trip_id=departing.trip_id,
            from_route_id=self.trip_route_ids.get(arriving.trip_id, ''),
            to_route_id=self.trip_route_ids.get(departing.trip_id, ''),
            arrival_seconds=arriving.arrival_seconds,
            departure_seconds=departing.departure_seconds)


@dataclass(frozen=True)
class Itinerary:
    first_board_seconds: int
    arrival_seconds: int
    transit_legs: Tuple[ScheduledEvent, ...]
    transfer: Optional[TransferFootpath] = None
    transfers: Tuple[TransferFootpath, ...] = ()

    def __post_init__(self):
        if self.transfer is not None and not self.transfers:
            object.__setattr__(self, 'transfers', (self.transfer,))
        elif self.transfer is None and len(self.transfers) == 1:
            object.__setattr__(self, 'transfer', self.transfers[0])
        elif self.transfer is not None and self.transfers != (self.transfer,):
            raise ValueError('transfer must match the sole transfers entry')

    @property
    def elapsed_seconds(self):
        return self.arrival_seconds - self.first_board_seconds

    @property
    def transfer_count(self):
        return len(self.transfers)


def _event_key(event):
    return (
        event.departure_seconds, event.arrival_seconds, event.trip_id,
        event.from_stop_sequence, event.to_stop_sequence,
        event.from_stop_id, event.to_stop_id)


def _validate_events(events):
    for event in events:
        if not isinstance(event, ScheduledEvent):
            raise GtfsEventError('events must be ScheduledEvent values')
        if (not all(isinstance(value, str) and value for value in (
                event.trip_id, event.from_stop_id, event.to_stop_id))
                or type(event.from_stop_sequence) is not int
                or type(event.to_stop_sequence) is not int
                or event.to_stop_sequence <= event.from_stop_sequence
                or type(event.departure_seconds) is not int
                or type(event.arrival_seconds) is not int
                or event.departure_seconds < 0
                or event.arrival_seconds < event.departure_seconds):
            raise GtfsEventError(f'invalid scheduled event for trip {event.trip_id!r}')


def _continuations(events, first):
    """Yield each reachable prefix while remaining aboard ``first``'s trip."""
    by_origin = {}
    for event in events:
        key = (event.trip_id, event.from_stop_sequence, event.from_stop_id)
        by_origin.setdefault(key, []).append(event)

    path = [first]
    seen = set()
    yield tuple(path)
    current = first
    while True:
        key = (current.trip_id, current.to_stop_sequence, current.to_stop_id)
        if key in seen:
            raise GtfsEventError(
                f'cyclic continuation for trip {current.trip_id}')
        seen.add(key)
        following = by_origin.get(key, [])
        if not following:
            return
        if len(following) != 1:
            raise GtfsEventError(
                f'ambiguous continuation for trip {current.trip_id} '
                f'at sequence {current.to_stop_sequence}')
        next_event = following[0]
        if next_event.departure_seconds < current.arrival_seconds:
            raise GtfsEventError(
                f'trip {current.trip_id} departs before its prior arrival')
        path.append(next_event)
        yield tuple(path)
        current = next_event


def _itinerary(path, transfers=()):
    return Itinerary(
        first_board_seconds=path[0].departure_seconds,
        arrival_seconds=path[-1].arrival_seconds,
        transit_legs=tuple(path),
        transfers=tuple(transfers))


def _choice_key(itinerary):
    return (
        itinerary.elapsed_seconds,
        itinerary.transfer_count,
        itinerary.first_board_seconds,
        itinerary.arrival_seconds,
        tuple((leg.trip_id, leg.from_stop_sequence, leg.to_stop_sequence)
              for leg in itinerary.transit_legs),
        tuple((transfer.from_stop_id, transfer.to_stop_id, transfer.seconds)
              for transfer in itinerary.transfers),
    )


def _state_key(itinerary):
    last = itinerary.transit_legs[-1]
    return (
        itinerary.first_board_seconds, last.trip_id, last.to_stop_sequence,
        last.to_stop_id, last.arrival_seconds)


def _state_rank(itinerary):
    return (
        itinerary.transfer_count,
        tuple((leg.trip_id, leg.from_stop_sequence, leg.to_stop_sequence)
              for leg in itinerary.transit_legs),
        tuple((transfer.from_stop_id, transfer.to_stop_id, transfer.seconds)
              for transfer in itinerary.transfers),
    )


def find_itinerary(events: Sequence[ScheduledEvent],
                   footpath_seconds: Mapping[Tuple[str, str], int],
                   origin_stop_ids, destination_stop_ids,
                   start_time='06:30:00', end_time='08:30:00',
                   max_elapsed_seconds=1800, direct_only=False,
                   transfer_resolver: Optional[DatedTransferResolver] = None):
    """Return the minimum-elapsed scheduled itinerary, or ``None``.

    The first transit boarding must depart an origin platform inside the
    inclusive window. A transfer is possible only when ``footpath_seconds``
    explicitly provides its directed stop pair and pre-resolved applicable
    minimum. Its walk and subsequent wait are included once because elapsed
    time ends at the final transit arrival. ``max_elapsed_seconds`` is exact
    and inclusive. ``direct_only`` permits intermediate calls on one trip but
    no vehicle change. When ``transfer_resolver`` is supplied, it is consulted
    for every temporally possible different-trip boarding. Only its ``allowed``
    results become edges; ``footpath_seconds`` is then deliberately not used as
    a fallback for rejected or unresolved rule outcomes.
    """
    if (type(max_elapsed_seconds) is not int
            or not 0 <= max_elapsed_seconds <= 1800):
        raise GtfsEventError('maximum elapsed seconds must be an integer from 0 to 1800')
    if type(direct_only) is not bool:
        raise GtfsEventError('direct_only must be a boolean')

    events = tuple(events)
    _validate_events(events)
    events = tuple(sorted(events, key=_event_key))
    destinations = set(destination_stop_ids)
    footpaths = []
    for stops, seconds in footpath_seconds.items():
        if (not isinstance(stops, tuple) or len(stops) != 2
                or not all(isinstance(stop, str) for stop in stops)):
            raise GtfsEventError('footpath keys must be (from_stop_id, to_stop_id)')
        if type(seconds) is not int or seconds < 0:
            raise GtfsEventError('footpath seconds must be non-negative integers')
        footpaths.append(TransferFootpath(stops[0], stops[1], seconds))
    footpaths.sort(key=lambda transfer: (
        transfer.from_stop_id, transfer.to_stop_id, transfer.seconds))

    footpaths_by_origin = {}
    for transfer in footpaths:
        footpaths_by_origin.setdefault(transfer.from_stop_id, []).append(transfer)
    departures_by_origin = {}
    for event in events:
        departures_by_origin.setdefault(event.from_stop_id, []).append(event)

    continuation_cache = {}

    def continuations(first):
        if first not in continuation_cache:
            continuation_cache[first] = tuple(_continuations(events, first))
        return continuation_cache[first]

    first_boards = eligible_first_board_departures(
        events, origin_stop_ids, start_time=start_time, end_time=end_time)
    candidates = []
    queue = []
    best_states = {}

    def enqueue(itinerary):
        if itinerary.elapsed_seconds > max_elapsed_seconds:
            return
        key = _state_key(itinerary)
        rank = _state_rank(itinerary)
        if key in best_states and best_states[key] <= rank:
            return
        best_states[key] = rank
        queue.append(itinerary)

    for first in first_boards:
        for first_ride in continuations(first):
            enqueue(_itinerary(first_ride))

    position = 0
    while position < len(queue):
        itinerary = queue[position]
        position += 1
        if best_states.get(_state_key(itinerary)) != _state_rank(itinerary):
            continue
        alighting = itinerary.transit_legs[-1]
        if alighting.to_stop_id in destinations:
            candidates.append(itinerary)
        if direct_only:
            continue

        deadline = itinerary.first_board_seconds + max_elapsed_seconds
        if transfer_resolver is not None:
            for next_event in events:
                if next_event.departure_seconds > deadline:
                    break
                if (next_event.trip_id == alighting.trip_id
                        or next_event.departure_seconds < alighting.arrival_seconds):
                    continue
                result = transfer_resolver.resolve(alighting, next_event)
                if not isinstance(result, TransferResult):
                    raise GtfsEventError(
                        'transfer resolver must return TransferResult values')
                if result.status != 'allowed':
                    continue
                available = next_event.departure_seconds - alighting.arrival_seconds
                if (type(result.minimum_seconds) is not int
                        or result.minimum_seconds < 0
                        or result.available_seconds != available
                        or not isinstance(result.provenance, str)
                        or not result.provenance):
                    raise GtfsEventError('invalid allowed transfer resolution')
                transfer = TransferFootpath(
                    alighting.to_stop_id, next_event.from_stop_id,
                    result.minimum_seconds, result.available_seconds,
                    result.provenance)
                for next_ride in continuations(next_event):
                    enqueue(_itinerary(
                        itinerary.transit_legs + next_ride,
                        itinerary.transfers + (transfer,)))
            continue

        for transfer in footpaths_by_origin.get(alighting.to_stop_id, ()):
            ready = alighting.arrival_seconds + transfer.seconds
            if ready > deadline:
                continue
            for next_event in departures_by_origin.get(transfer.to_stop_id, ()):
                if next_event.departure_seconds > deadline:
                    break
                if (next_event.trip_id == alighting.trip_id
                        or next_event.departure_seconds < ready):
                    continue
                for next_ride in continuations(next_event):
                    enqueue(_itinerary(
                        itinerary.transit_legs + next_ride,
                        itinerary.transfers + (transfer,)))

    return min(candidates, key=_choice_key) if candidates else None
