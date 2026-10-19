"""Bounded exact scheduled-itinerary prototype for synthetic GTFS events.

The search permits a direct ride or one transfer over an explicitly supplied
footpath. It does not add origin access, destination egress, or pure walking.
"""
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from gtfs_events import GtfsEventError, ScheduledEvent, eligible_first_board_departures


@dataclass(frozen=True)
class TransferFootpath:
    from_stop_id: str
    to_stop_id: str
    seconds: int


@dataclass(frozen=True)
class Itinerary:
    first_board_seconds: int
    arrival_seconds: int
    transit_legs: Tuple[ScheduledEvent, ...]
    transfer: Optional[TransferFootpath] = None

    @property
    def elapsed_seconds(self):
        return self.arrival_seconds - self.first_board_seconds


def _continuations(events, first):
    """Yield each reachable prefix while remaining aboard ``first``'s trip."""
    by_origin = {}
    for event in events:
        key = (event.trip_id, event.from_stop_sequence, event.from_stop_id)
        by_origin.setdefault(key, []).append(event)

    path = [first]
    yield tuple(path)
    current = first
    while True:
        key = (current.trip_id, current.to_stop_sequence, current.to_stop_id)
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


def _itinerary(path, transfer=None):
    return Itinerary(
        first_board_seconds=path[0].departure_seconds,
        arrival_seconds=path[-1].arrival_seconds,
        transit_legs=tuple(path),
        transfer=transfer)


def _choice_key(itinerary):
    return (
        itinerary.elapsed_seconds,
        itinerary.first_board_seconds,
        itinerary.arrival_seconds,
        tuple((leg.trip_id, leg.from_stop_sequence) for leg in itinerary.transit_legs),
    )


def find_itinerary(events: Sequence[ScheduledEvent],
                   footpath_seconds: Mapping[Tuple[str, str], int],
                   origin_stop_ids, destination_stop_ids,
                   start_time='06:30:00', end_time='08:30:00'):
    """Return the minimum-elapsed scheduled itinerary, or ``None``.

    The first transit boarding must depart an origin platform inside the
    inclusive window. A transfer is possible only when ``footpath_seconds``
    explicitly provides its directed stop pair; its walk and subsequent wait
    are included because elapsed time ends at the final transit arrival.
    """
    events = tuple(events)
    destinations = set(destination_stop_ids)
    footpaths = []
    for stops, seconds in footpath_seconds.items():
        if (not isinstance(stops, tuple) or len(stops) != 2
                or not all(isinstance(stop, str) for stop in stops)):
            raise GtfsEventError('footpath keys must be (from_stop_id, to_stop_id)')
        if type(seconds) is not int or seconds < 0:
            raise GtfsEventError('footpath seconds must be non-negative integers')
        footpaths.append(TransferFootpath(stops[0], stops[1], seconds))

    first_boards = eligible_first_board_departures(
        events, origin_stop_ids, start_time=start_time, end_time=end_time)
    candidates = []
    for first in first_boards:
        for first_ride in _continuations(events, first):
            alighting = first_ride[-1]
            if alighting.to_stop_id in destinations:
                candidates.append(_itinerary(first_ride))

            for transfer in footpaths:
                if transfer.from_stop_id != alighting.to_stop_id:
                    continue
                ready = alighting.arrival_seconds + transfer.seconds
                for second in events:
                    if (second.trip_id == first.trip_id
                            or second.from_stop_id != transfer.to_stop_id
                            or second.departure_seconds < ready):
                        continue
                    for second_ride in _continuations(events, second):
                        if second_ride[-1].to_stop_id in destinations:
                            candidates.append(_itinerary(
                                first_ride + second_ride, transfer))

    return min(candidates, key=_choice_key) if candidates else None
