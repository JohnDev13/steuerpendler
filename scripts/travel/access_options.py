"""Bounded adapter from evidenced external access to scheduled itineraries.

This slice consumes supplied access candidates, destination platforms, scheduled
GTFS events, and directed transfer minima. It never derives walking access,
station membership, or transfer edges. External access ends at the stop/station
entrance and is not a platform-finding penalty.

The current event parser rejects frequency and approximate-time rows that occur
in full Swiss GTFS feeds, and ``exact_itinerary`` supports at most one transfer.
Consequently this adapter is neither an exhaustive router nor Aarau acceptance.
"""
from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple

from exact_itinerary import Itinerary, find_itinerary
from gtfs_events import ScheduledEvent


MAX_SUPPORTED_WALK_MINUTES = 15
MAX_SUPPORTED_TRANSIT_MINUTES = 30
DEFAULT_START_TIME = '06:30:00'
DEFAULT_END_TIME = '08:30:00'


class AccessOptionError(ValueError):
    """Supplied access or destination evidence is invalid."""


@dataclass(frozen=True)
class AccessCandidate:
    """An evidenced external walk to one GTFS parent and its boardable platforms."""

    parent_stop_id: str
    platform_stop_ids: Tuple[str, ...]
    external_walk_seconds: int
    evidence_ref: str


@dataclass(frozen=True)
class DestinationTarget:
    """An evidenced destination parent and its eligible terminal platforms."""

    parent_stop_id: str
    platform_stop_ids: Tuple[str, ...]
    evidence_ref: str


@dataclass(frozen=True)
class AccessOption:
    external_walk_seconds: int
    transit_seconds: int
    origin_parent_id: str
    destination_parent_id: str
    first_board_seconds: int
    arrival_seconds: int
    boarded_platform_id: str
    access_evidence_ref: str
    destination_evidence_ref: str
    itinerary: Itinerary

    @property
    def transfer_seconds(self):
        return self.itinerary.transfer.seconds if self.itinerary.transfer else 0



def ceil_minutes(seconds):
    """Convert non-negative exact seconds to whole control/display minutes."""
    if type(seconds) is not int or seconds < 0:
        raise AccessOptionError('seconds must be a non-negative integer')
    return (seconds + 59) // 60



def _nonempty_string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise AccessOptionError(f'{field} must be a non-empty string')



def _platform_ids(value, field):
    if (not isinstance(value, tuple) or not value
            or any(not isinstance(item, str) or not item.strip() for item in value)):
        raise AccessOptionError(f'{field} must be a non-empty tuple of stop IDs')
    if len(set(value)) != len(value):
        raise AccessOptionError(f'{field} must not contain duplicate stop IDs')



def _validate_candidate(candidate):
    if not isinstance(candidate, AccessCandidate):
        raise AccessOptionError('access candidates must be AccessCandidate values')
    _nonempty_string(candidate.parent_stop_id, 'access parent_stop_id')
    _platform_ids(candidate.platform_stop_ids, 'access platform_stop_ids')
    if (type(candidate.external_walk_seconds) is not int
            or candidate.external_walk_seconds < 0):
        raise AccessOptionError(
            'external_walk_seconds must be a non-negative integer')
    _nonempty_string(candidate.evidence_ref, 'access evidence_ref')



def _validate_destination(destination):
    if not isinstance(destination, DestinationTarget):
        raise AccessOptionError('destination must be a DestinationTarget')
    _nonempty_string(destination.parent_stop_id, 'destination parent_stop_id')
    _platform_ids(destination.platform_stop_ids, 'destination platform_stop_ids')
    _nonempty_string(destination.evidence_ref, 'destination evidence_ref')



def _itinerary_ids(itinerary):
    return tuple(
        (leg.trip_id, leg.from_stop_id, leg.to_stop_id, leg.from_stop_sequence)
        for leg in itinerary.transit_legs)



def _stable_route_key(option):
    return (
        option.origin_parent_id,
        option.destination_parent_id,
        option.boarded_platform_id,
        _itinerary_ids(option.itinerary),
        option.arrival_seconds,
    )



def _frontier_sort_key(option):
    return (
        option.external_walk_seconds,
        option.transit_seconds,
        option.first_board_seconds,
        option.arrival_seconds,
        _stable_route_key(option),
    )



def _selection_key(option):
    return (
        option.external_walk_seconds + option.transit_seconds,
        option.transit_seconds,
        option.external_walk_seconds,
        option.first_board_seconds,
        _stable_route_key(option),
    )



def nondominated_frontier(options):
    """Return the stable exact ``(walk, transit)`` nondominated frontier."""
    stable = sorted(options, key=_frontier_sort_key)
    unique_metrics = {}
    for option in stable:
        metric = (option.external_walk_seconds, option.transit_seconds)
        unique_metrics.setdefault(metric, option)

    unique = tuple(unique_metrics.values())
    frontier = []
    for candidate in unique:
        dominated = any(
            other.external_walk_seconds <= candidate.external_walk_seconds
            and other.transit_seconds <= candidate.transit_seconds
            and (other.external_walk_seconds < candidate.external_walk_seconds
                 or other.transit_seconds < candidate.transit_seconds)
            for other in unique
        )
        if not dominated:
            frontier.append(candidate)
    return tuple(sorted(frontier, key=_frontier_sort_key))



def build_access_options(
        events: Sequence[ScheduledEvent],
        directed_transfer_minimums: Mapping[Tuple[str, str], int],
        access_candidates: Sequence[AccessCandidate],
        destination: DestinationTarget,
        start_time=DEFAULT_START_TIME,
        end_time=DEFAULT_END_TIME):
    """Build the supported exact frontier from explicit evidenced inputs.

    Each access candidate is searched independently so an out-of-Gemeinde rail
    hub and a local bus stop can both survive. ``find_itinerary`` receives only
    caller-supplied directed transfer minima. Options outside the supported
    15-minute external-walk or 30-minute transit bounds are removed by ceiling.
    """
    _validate_destination(destination)
    candidates = tuple(access_candidates)
    for candidate in candidates:
        _validate_candidate(candidate)

    options = []
    for candidate in candidates:
        if ceil_minutes(candidate.external_walk_seconds) > MAX_SUPPORTED_WALK_MINUTES:
            continue
        itinerary = find_itinerary(
            events,
            directed_transfer_minimums,
            candidate.platform_stop_ids,
            destination.platform_stop_ids,
            start_time=start_time,
            end_time=end_time,
        )
        if itinerary is None:
            continue
        transit_seconds = itinerary.elapsed_seconds
        if ceil_minutes(transit_seconds) > MAX_SUPPORTED_TRANSIT_MINUTES:
            continue
        options.append(AccessOption(
            external_walk_seconds=candidate.external_walk_seconds,
            transit_seconds=transit_seconds,
            origin_parent_id=candidate.parent_stop_id,
            destination_parent_id=destination.parent_stop_id,
            first_board_seconds=itinerary.first_board_seconds,
            arrival_seconds=itinerary.arrival_seconds,
            boarded_platform_id=itinerary.transit_legs[0].from_stop_id,
            access_evidence_ref=candidate.evidence_ref,
            destination_evidence_ref=destination.evidence_ref,
            itinerary=itinerary,
        ))
    return nondominated_frontier(options)



def eligible_options(options, max_walk_minutes, max_transit_minutes,
                     count_walk=False):
    """Return options satisfying separate caps and the optional combined cap."""
    for value, field, supported_maximum in (
            (max_walk_minutes, 'max_walk_minutes', MAX_SUPPORTED_WALK_MINUTES),
            (max_transit_minutes, 'max_transit_minutes',
             MAX_SUPPORTED_TRANSIT_MINUTES)):
        if type(value) is not int or value < 0:
            raise AccessOptionError(f'{field} must be a non-negative integer')
        if value > supported_maximum:
            raise AccessOptionError(
                f'{field} must not exceed {supported_maximum}')
    if type(count_walk) is not bool:
        raise AccessOptionError('count_walk must be a boolean')

    eligible = []
    for option in options:
        walk = ceil_minutes(option.external_walk_seconds)
        transit = ceil_minutes(option.transit_seconds)
        if walk > max_walk_minutes or transit > max_transit_minutes:
            continue
        if count_walk and walk + transit > max_transit_minutes:
            continue
        eligible.append(option)
    return tuple(sorted(eligible, key=_frontier_sort_key))



def select_option(options, max_walk_minutes, max_transit_minutes,
                  count_walk=False):
    """Select the eligible option by the contract's exact stable ordering."""
    eligible = eligible_options(
        options, max_walk_minutes, max_transit_minutes, count_walk=count_walk)
    return min(eligible, key=_selection_key) if eligible else None
