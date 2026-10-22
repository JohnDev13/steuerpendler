"""Assess one Aarau feeder candidate against directed GTFS transfer rules.

The function in this module is deliberately pure: callers provide one raw
necessary-only candidate, exact trip-to-route metadata, stop parents, relevant
``transfers.txt`` rows, and source lineage.  It neither opens the GTFS archive
nor turns a positive transfer into a fastest-route or municipality claim.
"""
from dataclasses import dataclass
import datetime as dt
import re
from types import MappingProxyType
from typing import Iterable, Mapping, Optional

from transfer_rules import resolve_transfer


EXPECTED_CANDIDATE_STREAM_SHA256 = (
    "1a1173576d2f9873ca25eee057ed85fa1c9e6a949661a0a39d8eb94d9e4009ee"
)
EXPECTED_SERVICE_DAY = "2026-10-27"
EXPECTED_STREAM_STATUS = "necessary_only"
WINDOW_START_SECONDS = 6 * 60 * 60 + 30 * 60
WINDOW_END_SECONDS = 8 * 60 * 60 + 30 * 60
CAP_SECONDS = 30 * 60
_REQUIRED_CANDIDATE_FIELDS = (
    "first_board_seconds",
    "first_board_stop_id",
    "first_leg_trip_id",
    "hub_stop_id",
    "hub_arrival_seconds",
    "hub_drop_off_type",
    "first_board_pickup_type",
    "second_leg_trip_id",
    "second_leg_boarding_seconds",
    "second_leg_arrival_seconds",
    "total_transit_seconds",
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class CandidateTransferError(ValueError):
    """The supplied candidate or its exact source metadata is contradictory."""


@dataclass(frozen=True)
class CandidateSourceLineage:
    """Hash-pinned lineage carried unchanged into an assessment result."""

    candidate_stream_sha256: str
    source_gtfs_sha256: str
    service_day: str
    stream_status: str


@dataclass(frozen=True)
class CandidateTransferAssessment:
    """One transfer outcome, without route-optimality or reachability claims."""

    status: str
    minimum_seconds: Optional[int]
    available_seconds: Optional[int]
    provenance: str
    from_route_id: str
    to_route_id: str
    total_transit_seconds: int
    candidate_evidence: Mapping[str, object]
    source_lineage: CandidateSourceLineage


def _identifier(candidate: Mapping[str, object], field: str) -> str:
    value = candidate[field]
    if not isinstance(value, str) or not value:
        raise CandidateTransferError(f"{field} must be a non-empty string")
    return value


def _seconds(candidate: Mapping[str, object], field: str) -> int:
    value = candidate[field]
    if type(value) is not int or value < 0:
        raise CandidateTransferError(f"{field} must be a nonnegative integer")
    return value


def _validate_lineage(lineage: object) -> CandidateSourceLineage:
    if not isinstance(lineage, CandidateSourceLineage):
        raise CandidateTransferError("source_lineage must be CandidateSourceLineage")
    for field in ("candidate_stream_sha256", "source_gtfs_sha256"):
        value = getattr(lineage, field)
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise CandidateTransferError(f"{field} must be a lowercase SHA-256")
    if lineage.candidate_stream_sha256 != EXPECTED_CANDIDATE_STREAM_SHA256:
        raise CandidateTransferError("candidate stream SHA-256 does not match the pinned stream")
    try:
        parsed_day = dt.date.fromisoformat(lineage.service_day)
    except (TypeError, ValueError) as exc:
        raise CandidateTransferError("service_day must be an ISO calendar date") from exc
    if parsed_day.isoformat() != EXPECTED_SERVICE_DAY:
        raise CandidateTransferError(
            f"service_day must be the pinned {EXPECTED_SERVICE_DAY} service day")
    if lineage.stream_status != EXPECTED_STREAM_STATUS:
        raise CandidateTransferError("stream_status must be necessary_only")
    return lineage


def _validate_routes(route_ids_by_trip: object, first_trip: str,
                     second_trip: str) -> tuple[str, str]:
    if not isinstance(route_ids_by_trip, Mapping):
        raise CandidateTransferError("route_ids_by_trip must be a mapping")
    expected = {first_trip, second_trip}
    if set(route_ids_by_trip) != expected:
        raise CandidateTransferError(
            "route_ids_by_trip must contain exactly the two candidate trip IDs")
    routes = []
    for trip_id in (first_trip, second_trip):
        route_id = route_ids_by_trip[trip_id]
        if not isinstance(route_id, str) or not route_id:
            raise CandidateTransferError(
                f"route_id for trip {trip_id!r} must be a non-empty string")
        routes.append(route_id)
    return routes[0], routes[1]


def assess_candidate_transfer(
        candidate: Mapping[str, object],
        route_ids_by_trip: Mapping[str, str],
        stop_parents: Mapping[str, str],
        transfer_rows: Iterable[Mapping[str, object]], *,
        source_lineage: CandidateSourceLineage) -> CandidateTransferAssessment:
    """Validate and assess one exact same-child transfer candidate.

    Only ``resolve_transfer`` decides GTFS rule precedence.  Its ``allowed``
    status is promoted to ``feasible_one_transfer_positive``; prohibited,
    insufficient-time, and unresolved outcomes retain their distinct meaning.
    """
    if not isinstance(candidate, Mapping):
        raise CandidateTransferError("candidate must be a mapping")
    missing = [field for field in _REQUIRED_CANDIDATE_FIELDS if field not in candidate]
    if missing:
        raise CandidateTransferError(f"candidate is missing required field {missing[0]}")
    lineage = _validate_lineage(source_lineage)

    first_board_stop = _identifier(candidate, "first_board_stop_id")
    first_trip = _identifier(candidate, "first_leg_trip_id")
    hub_stop = _identifier(candidate, "hub_stop_id")
    second_trip = _identifier(candidate, "second_leg_trip_id")
    if first_trip == second_trip:
        raise CandidateTransferError("first and second legs must use distinct trips")

    first_board = _seconds(candidate, "first_board_seconds")
    hub_arrival = _seconds(candidate, "hub_arrival_seconds")
    second_board = _seconds(candidate, "second_leg_boarding_seconds")
    second_arrival = _seconds(candidate, "second_leg_arrival_seconds")
    declared_total = _seconds(candidate, "total_transit_seconds")
    if not WINDOW_START_SECONDS <= first_board <= WINDOW_END_SECONDS:
        raise CandidateTransferError(
            "first_board_seconds must be within 06:30-08:30 inclusive")
    if not first_board <= hub_arrival <= second_board <= second_arrival:
        raise CandidateTransferError(
            "candidate chronology must satisfy first board <= hub arrival <= "
            "second board <= second arrival")
    elapsed = second_arrival - first_board
    if declared_total != elapsed:
        raise CandidateTransferError(
            "total_transit_seconds must equal second-leg arrival minus first boarding")
    if elapsed > CAP_SECONDS:
        raise CandidateTransferError("elapsed transit time must be at most 1,800 seconds")

    for field in ("first_board_pickup_type", "hub_drop_off_type"):
        value = candidate[field]
        if value not in ("", "0"):
            raise CandidateTransferError(
                f"{field} must explicitly permit boarding/alighting (blank or '0')")

    from_route, to_route = _validate_routes(
        route_ids_by_trip, first_trip, second_trip)
    if not isinstance(stop_parents, Mapping):
        raise CandidateTransferError("stop_parents must be a mapping")

    transfer = resolve_transfer(
        transfer_rows,
        stop_parents,
        from_stop_id=hub_stop,
        to_stop_id=hub_stop,
        from_trip_id=first_trip,
        to_trip_id=second_trip,
        from_route_id=from_route,
        to_route_id=to_route,
        arrival_seconds=hub_arrival,
        departure_seconds=second_board,
    )
    status = ("feasible_one_transfer_positive"
              if transfer.status == "allowed" else transfer.status)
    if status not in {
            "feasible_one_transfer_positive", "insufficient_time",
            "prohibited", "unresolved"}:
        raise CandidateTransferError(
            f"unexpected transfer resolver status {transfer.status!r}")

    # Copy and freeze the complete source record. Extra feeder-stream evidence is
    # intentionally retained rather than reduced to a second minutes table.
    raw_evidence = MappingProxyType(dict(candidate))
    return CandidateTransferAssessment(
        status=status,
        minimum_seconds=transfer.minimum_seconds,
        available_seconds=transfer.available_seconds,
        provenance=transfer.provenance,
        from_route_id=from_route,
        to_route_id=to_route,
        total_transit_seconds=elapsed,
        candidate_evidence=raw_evidence,
        source_lineage=lineage,
    )
