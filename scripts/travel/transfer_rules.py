"""Directed GTFS transfer-rule resolution for supplied scheduled events.

This module resolves one arriving/departing trip pair.  It does not infer
station geometry, add entrance/platform walking, or implement timed and
in-seat transfer service semantics.
"""
from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Optional


@dataclass(frozen=True)
class TransferResult:
    """Explicit transfer outcome; ``unresolved`` must never be treated as false/zero."""

    status: str
    minimum_seconds: Optional[int]
    available_seconds: Optional[int]
    provenance: str


_SELECTOR_FIELDS = ('from_trip_id', 'to_trip_id', 'from_route_id', 'to_route_id')


def _valid_id(value):
    return isinstance(value, str) and bool(value)


def _field(row, name):
    value = row.get(name, '')
    return value if isinstance(value, str) else None


def _stop_match(rule_stop, child_stop, parent_stop, allow_blank=False):
    if allow_blank and rule_stop == '':
        return -1
    if rule_stop == child_stop:
        return 1
    if parent_stop is not None and rule_stop == parent_stop:
        return 0
    return None


def _specificity(row):
    """Return the six-level specificity required by the GTFS Schedule spec."""
    from_kind = 'trip' if row['from_trip_id'] else 'route' if row['from_route_id'] else None
    to_kind = 'trip' if row['to_trip_id'] else 'route' if row['to_route_id'] else None
    kinds = (from_kind, to_kind)
    if kinds == ('trip', 'trip'):
        return 6, 'both_trips'
    if set(kinds) == {'trip', 'route'}:
        return 5, 'trip_route'
    if 'trip' in kinds:
        return 4, 'one_trip'
    if kinds == ('route', 'route'):
        return 3, 'both_routes'
    if 'route' in kinds:
        return 2, 'one_route'
    return 1, 'stop_pair'


def _selector_applies(row, context):
    return all(not row[field] or row[field] == context[field]
               for field in _SELECTOR_FIELDS)


def _semantic(row):
    if row['service_id']:
        return 'unresolved', None, 'transfer_service_id'

    transfer_type = row['transfer_type']
    if transfer_type == '2':
        value = row['min_transfer_time']
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]+', value):
            return 'unresolved', None, 'invalid_min_transfer_time'
        minimum = int(value)
        return 'minimum', minimum, None
    if transfer_type == '3':
        return 'prohibited', None, 'prohibited_type_3'
    if transfer_type == '1':
        return 'unresolved', None, 'timed_transfer_type_1'
    if transfer_type == '4':
        return 'unresolved', None, 'in_seat_transfer_type_4'
    return 'unresolved', None, f'unsupported_transfer_type_{transfer_type or "blank"}'


def _outcome_for_minimum(minimum, available, provenance):
    status = 'allowed' if available >= minimum else 'insufficient_time'
    return TransferResult(status, minimum, available, provenance)


def resolve_transfer(rows: Iterable[Mapping[str, object]],
                     stop_parents: Mapping[str, str], *,
                     from_stop_id: str, to_stop_id: str,
                     from_trip_id: str, to_trip_id: str,
                     from_route_id: str, to_route_id: str,
                     arrival_seconds: int, departure_seconds: int):
    """Resolve a directed transfer for one exact pair of scheduled trip events.

    ``rows`` is consumed once and only equally best candidates are retained.
    Parent-station fallback is possible only for endpoint mappings explicitly
    present in ``stop_parents``.  The Swiss 120-second default likewise requires
    both child stops to have the same evidenced parent.
    """
    identifiers = (from_stop_id, to_stop_id, from_trip_id, to_trip_id,
                   from_route_id, to_route_id)
    if not all(_valid_id(value) for value in identifiers):
        return TransferResult('unresolved', None, None, 'invalid_transfer_context')
    if (type(arrival_seconds) is not int or type(departure_seconds) is not int
            or arrival_seconds < 0 or departure_seconds < arrival_seconds):
        return TransferResult('unresolved', None, None, 'invalid_scheduled_times')
    available = departure_seconds - arrival_seconds

    from_parent = stop_parents.get(from_stop_id)
    to_parent = stop_parents.get(to_stop_id)
    from_parent = from_parent if _valid_id(from_parent) else None
    to_parent = to_parent if _valid_id(to_parent) else None
    context = {
        'from_trip_id': from_trip_id,
        'to_trip_id': to_trip_id,
        'from_route_id': from_route_id,
        'to_route_id': to_route_id,
    }

    # Trip/route rank and child-vs-parent rank are distinct specificity axes.
    # A tradeoff between them is unresolved rather than silently choosing a
    # shorter minimum via a lexicographic ordering not specified by the feed.
    frontier = []
    for row_number, source_row in enumerate(rows, 1):
        if not isinstance(source_row, Mapping):
            return TransferResult(
                'unresolved', None, available,
                f'transfers.txt row {row_number}: malformed_transfer_row')
        source_type = _field(source_row, 'transfer_type')
        stop_optional = source_type in ('4', '5')
        from_match = _stop_match(
            _field(source_row, 'from_stop_id'), from_stop_id, from_parent,
            allow_blank=stop_optional)
        to_match = _stop_match(
            _field(source_row, 'to_stop_id'), to_stop_id, to_parent,
            allow_blank=stop_optional)
        if from_match is None or to_match is None:
            continue

        normalized: dict[str, object] = {
            field: _field(source_row, field) for field in _SELECTOR_FIELDS
        }
        normalized.update({
            'service_id': _field(source_row, 'service_id'),
            'transfer_type': _field(source_row, 'transfer_type'),
            'min_transfer_time': source_row.get('min_transfer_time', ''),
        })
        if any(normalized[field] is None
               for field in (*_SELECTOR_FIELDS, 'service_id', 'transfer_type')):
            return TransferResult(
                'unresolved', None, available,
                f'transfers.txt row {row_number}: malformed_transfer_row')
        if not _selector_applies(normalized, context):
            continue

        rule_rank, rule_scope = _specificity(normalized)
        stop_rank = from_match + to_match
        stop_scope = ('child_pair' if stop_rank == 2 else
                      'parent_pair' if stop_rank == 0 else
                      'trip_only' if stop_rank == -2 else 'mixed_pair')
        key = (rule_rank, stop_rank)
        candidate = (row_number, normalized, rule_scope, stop_scope)
        if any(existing[0] >= rule_rank and existing[1] >= stop_rank
               and existing != key for existing, _ in frontier):
            continue
        frontier = [
            (existing, prior) for existing, prior in frontier
            if not (rule_rank >= existing[0] and stop_rank >= existing[1]
                    and key != existing)
        ]
        frontier.append((key, candidate))

    if not frontier:
        if from_parent is None or to_parent is None:
            return TransferResult(
                'unresolved', None, available, 'stop_parent_identity_not_evidenced')
        if from_parent != to_parent:
            return TransferResult(
                'unresolved', None, available,
                'no_applicable_rule_for_distinct_parents')
        return _outcome_for_minimum(
            120, available, 'swiss_same_parent_default')

    if len({key for key, _ in frontier}) > 1:
        numbers = ','.join(str(candidate[0]) for _, candidate in frontier)
        return TransferResult('unresolved', None, available,
                              f'competing_stop_selector_specificity rows {numbers}')
    best = [candidate for _, candidate in frontier]
    semantics = [_semantic(candidate[1]) for candidate in best]
    if any(semantic != semantics[0] for semantic in semantics[1:]):
        numbers = ','.join(str(candidate[0]) for candidate in best)
        return TransferResult(
            'unresolved', None, available,
            f'conflicting equally specific transfers.txt rows {numbers}')

    row_number, _, rule_scope, stop_scope = best[0]
    kind, minimum, detail = semantics[0]
    provenance = f'transfers.txt row {row_number} ({rule_scope}, {stop_scope})'
    if kind == 'minimum':
        return _outcome_for_minimum(minimum, available, provenance)
    return TransferResult(kind, None, available, f'{provenance}: {detail}')
