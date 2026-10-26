"""Tests for the bounded sequential all-destination event-matrix exporter."""
from __future__ import annotations

import gzip
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "travel"))

import canonical_all19_export as all19
import canonical_event_slice as event_slice


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_registry(path: pathlib.Path, destinations: list[tuple[int, list[str]]]) -> None:
    path.write_text(json.dumps({
        "status": "PROVISIONAL_SOURCE_CANDIDATES",
        "workplaces": [{
            "bfs": bfs,
            "targetCandidates": [{"childStopIds": children}],
        } for bfs, children in destinations],
    }), encoding="utf-8")


def result(status: str, identity: tuple) -> dict:
    if status == "unknown":
        return {
            "status": "unknown", "arrivalSeconds": None, "elapsedSeconds": None,
            "transferCount": None, "legs": [], "transferRuleIds": [],
            "unresolvedReasons": ["bounded_source"],
        }
    arrival = identity[4] + 600
    return {
        "status": "best_found_unproven", "arrivalSeconds": arrival,
        "elapsedSeconds": 600, "transferCount": 0,
        "legs": [{
            "trip_id": identity[1], "route_id": "R1", "service_id": "S",
            "board_stop_id": identity[2], "alight_stop_id": "Z",
            "board_seconds": identity[4], "alight_seconds": arrival,
            "connection_ids": [identity[0]],
        }], "transferRuleIds": [],
        "unresolvedReasons": ["bounded_source"],
    }


def write_slice(path: pathlib.Path, bfs: int, children: list[str], *,
                target_registry_sha="d" * 64,
                identities=((1, "T1", "S1", 1, 23_400, 100),
                            (2, "T2", "S2", 2, 23_500, 200)),
                statuses=(("best_found_unproven", "best_found_unproven"),
                          ("unknown", "unknown")),
                include_summary=True) -> None:
    source = {
        "connections": "a" * 64, "transferScope": "b" * 64,
        "boardStopGemeinde": "c" * 64, "targetRegistry": target_registry_sha,
    }
    records = [{
        "event": {
            "connectionId": identity[0], "tripInstanceId": identity[1],
            "stopId": identity[2], "stopSequence": identity[3],
            "boardSeconds": identity[4], "originBfs": identity[5],
        },
        "allRoutes": result(status[0], identity),
        "directOnly": result(status[1], identity),
    } for identity, status in zip(identities, statuses)]
    manifest = {
        "kind": "manifest", "schema": "steuerpendler.canonical-event-slice.v1",
        "destinationBfs": bfs, "serviceDate": "2026-10-27",
        "timezone": "Europe/Zurich",
        "firstBoardWindowSecondsInclusive": [23_400, 30_600],
        "maxElapsedSecondsInclusive": 1_800, "sourceSha256": source,
        "denominator": len(records),
        "sourceCoverage": {"sourceCandidateFirstBoardEvents": 3,
                           "excludedFirstBoardEvents": 1},
        "generatorVersion": "1.2", "generatorSha256": "e" * 64,
        "destinationChildStopIds": sorted(children),
        "uncertaintyInventory": {
            "frequency_source_quarantined": 1,
            "non_exact_source_quarantined": 2,
            "in_seat_continuations_unvalidated": 3,
            "board_stops_boundary_quarantined": 4,
            "board_stops_unassigned": 5,
            "target_group_status": "PROVISIONAL_SOURCE_CANDIDATES",
        },
        "unresolvedReasons": ["bounded_source"],
        "claims": "BOUNDED_DESTINATION_POSITIVES_AND_UNKNOWNS_NOT_GLOBAL_PROOF",
    }
    summary = {
        "kind": "summary", "denominator": len(records), "emitted": len(records),
        "positives": {"allRoutes": 1, "directOnly": 1},
        "unknowns": {"allRoutes": 1, "directOnly": 1},
        "statuses": {
            "allRoutes": {"best_found_unproven": 1, "unknown": 1},
            "directOnly": {"best_found_unproven": 1, "unknown": 1},
        },
    }
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as stream:
            payloads = [manifest, *records] + ([summary] if include_summary else [])
            for payload in payloads:
                stream.write((json.dumps(payload, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode())


def read_gzip(path: pathlib.Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def rewrite_slice(path: pathlib.Path, mutate) -> None:
    payloads = read_gzip(path)
    mutate(payloads)
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as stream:
            for payload in payloads:
                stream.write((json.dumps(payload, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode())


class CanonicalAll19ExportTests(unittest.TestCase):
    def settings(self, registry: pathlib.Path, count: int):
        return mock.patch.multiple(
            all19, DESTINATION_COUNT=count, TARGET_REGISTRY_SHA256=sha256(registry),
            CONNECTION_SHA256="a" * 64, BOARD_STOP_SHA256="c" * 64,
            EVENT_SLICE_GENERATOR_SHA256="e" * 64)

    def test_aggregate_streams_identity_order_and_exact_product(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            registry = directory / "targets.json"
            write_registry(registry, [(100, ["B", "A"]), (200, ["C"])])
            slices = {}
            for bfs, children in ((100, ["A", "B"]), (200, ["C"])):
                path = directory / f"{bfs}.gz"
                write_slice(path, bfs, children, target_registry_sha=sha256(registry))
                slices[bfs] = path
            output = directory / "matrix.gz"
            with self.settings(registry, 2):
                manifest, summary, _ = all19.aggregate_slices(
                    slices, registry, output,
                    expected_transfer_scope_sha256="b" * 64)
            payloads = read_gzip(output)
            records = payloads[1:-1]
            self.assertEqual(manifest["destinationBfs"], [100, 200])
            self.assertEqual(manifest["destinationGroups"], [
                {"destinationBfs": 100, "destinationChildStopIds": ["A", "B"]},
                {"destinationBfs": 200, "destinationChildStopIds": ["C"]},
            ])
            self.assertEqual(summary["eventDestinationRecords"], 4)
            self.assertEqual(summary["firstBoardEvents"], 2)
            self.assertEqual([row["destinationBfs"] for row in records], [100, 100, 200, 200])
            self.assertEqual([row["event"]["connectionId"] for row in records], [1, 2, 1, 2])
            self.assertEqual(payloads[-1], summary)

    def test_registry_rejects_duplicate_and_missing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            duplicate = directory / "duplicate.json"
            write_registry(duplicate, [(100, ["A"]), (100, ["B"])])
            with mock.patch.object(all19, "DESTINATION_COUNT", 2):
                with self.assertRaisesRegex(all19.All19ExportError, "unique"):
                    all19.load_destination_registry(duplicate)
            missing = directory / "missing.json"
            write_registry(missing, [(100, ["A"])])
            with mock.patch.object(all19, "DESTINATION_COUNT", 2):
                with self.assertRaisesRegex(all19.All19ExportError, "exactly 2"):
                    all19.load_destination_registry(missing)

    def test_mismatched_identity_preserves_prior_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            registry = directory / "targets.json"
            write_registry(registry, [(100, ["A"]), (200, ["B"])])
            first, second = directory / "100.gz", directory / "200.gz"
            write_slice(first, 100, ["A"], target_registry_sha=sha256(registry))
            write_slice(second, 200, ["B"], identities=(
                (1, "T1", "S1", 1, 23_400, 100),
                (3, "T3", "S3", 3, 23_600, 300)),
                target_registry_sha=sha256(registry))
            output = directory / "matrix.gz"
            output.write_bytes(b"PRIOR")
            with self.settings(registry, 2):
                with self.assertRaisesRegex(all19.All19ExportError, "identity"):
                    all19.aggregate_slices(
                        {100: first, 200: second}, registry, output,
                        expected_transfer_scope_sha256="b" * 64)
            self.assertEqual(output.read_bytes(), b"PRIOR")

    def test_corrupt_or_missing_summary_preserves_prior_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            registry = directory / "targets.json"
            write_registry(registry, [(100, ["A"]), (200, ["B"])])
            good, bad = directory / "100.gz", directory / "200.gz"
            write_slice(good, 100, ["A"], target_registry_sha=sha256(registry))
            write_slice(bad, 200, ["B"], include_summary=False,
                        target_registry_sha=sha256(registry))
            output = directory / "matrix.gz"
            output.write_bytes(b"PRIOR")
            with self.settings(registry, 2):
                with self.assertRaisesRegex(all19.All19ExportError, "summary"):
                    all19.aggregate_slices(
                        {100: good, 200: bad}, registry, output,
                        expected_transfer_scope_sha256="b" * 64)
            self.assertEqual(output.read_bytes(), b"PRIOR")
            bad.write_bytes(b"not gzip")
            with self.settings(registry, 2):
                with self.assertRaises(all19.All19ExportError):
                    all19.aggregate_slices(
                        {100: good, 200: bad}, registry, output,
                        expected_transfer_scope_sha256="b" * 64)
            self.assertEqual(output.read_bytes(), b"PRIOR")

    def test_repeated_aggregation_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            registry = directory / "targets.json"
            write_registry(registry, [(100, ["A"]), (200, ["B"])])
            slices = {}
            for bfs, children in ((100, ["A"]), (200, ["B"])):
                slices[bfs] = directory / f"{bfs}.gz"
                write_slice(slices[bfs], bfs, children,
                            target_registry_sha=sha256(registry))
            outputs = [directory / "one.gz", directory / "two.gz"]
            with self.settings(registry, 2):
                for output in outputs:
                    all19.aggregate_slices(
                        slices, registry, output,
                        expected_transfer_scope_sha256="b" * 64)
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())

    def test_child_memory_is_capped_and_over_budget_report_fails_closed(self):
        with mock.patch.object(all19.resource,'setrlimit') as set_limit:
            all19._bound_child_address_space()
        set_limit.assert_called_once_with(
            all19.resource.RLIMIT_AS,
            (all19.CHILD_VIRTUAL_LIMIT_BYTES,all19.CHILD_VIRTUAL_LIMIT_BYTES))
        with self.assertRaisesRegex(all19.All19ExportError,'memory'):
            all19._validate_child_memory({'peakRssKiB':1_600_000},100)
        with self.assertRaisesRegex(all19.All19ExportError,'memory'):
            all19._validate_child_memory({'peakRssKiB':'unknown'},100)
        all19._validate_child_memory({'peakRssKiB':1_080_000},100)

    def test_direct_only_transfer_path_is_rejected_without_replacing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            registry = directory/'targets.json'
            write_registry(registry,[(100,['A']),(200,['B'])])
            slices={}
            for bfs,children in ((100,['A']),(200,['B'])):
                path=directory/f'{bfs}.gz'
                write_slice(path,bfs,children,target_registry_sha=sha256(registry))
                slices[bfs]=path
            def forge(rows):
                direct=rows[1]['directOnly']
                first=direct['legs'][0]
                first['alight_stop_id']='X'
                first['alight_seconds']=first['board_seconds']+200
                second={**first,'trip_id':'T-TRANSFER','board_stop_id':'X',
                        'board_seconds':first['board_seconds']+240,
                        'alight_stop_id':'Z','alight_seconds':direct['arrivalSeconds'],
                        'connection_ids':[999]}
                direct['legs'].append(second)
                direct['transferCount']=1
                direct['transferRuleIds']=[123]
            rewrite_slice(slices[100],forge)
            output=directory/'matrix.gz'
            output.write_bytes(b'PRIOR')
            with self.settings(registry,2):
                with self.assertRaisesRegex(all19.All19ExportError,'direct-only'):
                    all19.aggregate_slices(slices,registry,output,
                        expected_transfer_scope_sha256='b'*64)
            self.assertEqual(output.read_bytes(),b'PRIOR')

    def test_direct_only_cannot_be_positive_if_all_routes_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            registry = directory / 'targets.json'
            write_registry(registry, [(100,['A']),(200,['B'])])
            slices = {}
            for bfs,children in ((100,['A']),(200,['B'])):
                path = directory / f'{bfs}.gz'
                write_slice(path,bfs,children,target_registry_sha=sha256(registry))
                slices[bfs]=path
            rewrite_slice(slices[100],lambda rows: rows[1].update(
                allRoutes=result('unknown',(1,'T1','S1',1,23_400,100))))
            output = directory/'matrix.gz'
            output.write_bytes(b'PRIOR')
            with self.settings(registry,2):
                with self.assertRaisesRegex(all19.All19ExportError,'direct-only'):
                    all19.aggregate_slices(slices,registry,output,
                        expected_transfer_scope_sha256='b'*64)
            self.assertEqual(output.read_bytes(),b'PRIOR')

    def test_malformed_result_and_forged_generator_provenance_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            registry = directory / "targets.json"
            write_registry(registry, [(100, ["A"]), (200, ["B"])])
            slices = {}
            for bfs, children in ((100, ["A"]), (200, ["B"])):
                slices[bfs] = directory / f"{bfs}.gz"
                write_slice(slices[bfs], bfs, children,
                            target_registry_sha=sha256(registry))
            output = directory / "matrix.gz"
            output.write_bytes(b"PRIOR")
            rewrite_slice(slices[100], lambda rows: rows[1]["directOnly"].pop(
                "arrivalSeconds"))
            with self.settings(registry, 2):
                with self.assertRaisesRegex(all19.All19ExportError, "malformed"):
                    all19.aggregate_slices(
                        slices, registry, output,
                        expected_transfer_scope_sha256="b" * 64)
            self.assertEqual(output.read_bytes(), b"PRIOR")

            write_slice(slices[100], 100, ["A"],
                        target_registry_sha=sha256(registry))
            rewrite_slice(slices[100], lambda rows: rows[0].update(
                generatorSha256="f" * 64))
            with self.settings(registry, 2):
                with self.assertRaisesRegex(all19.All19ExportError, "provenance"):
                    all19.aggregate_slices(
                        slices, registry, output,
                        expected_transfer_scope_sha256="b" * 64)
            self.assertEqual(output.read_bytes(), b"PRIOR")

    def test_run_report_failure_restores_prior_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            registry = directory / "targets.json"
            write_registry(registry, [(100, ["A"]), (200, ["B"])])
            slices = {}
            for bfs, children in ((100, ["A"]), (200, ["B"])):
                slices[bfs] = directory / f"{bfs}.gz"
                write_slice(slices[bfs], bfs, children,
                            target_registry_sha=sha256(registry))
            output = directory / "matrix.gz"
            report = output.with_suffix(output.suffix + ".run.json")
            output.write_bytes(b"PRIOR OUTPUT")
            report.write_bytes(b"PRIOR REPORT")
            with self.settings(registry, 2), mock.patch.object(
                    all19, "_atomic_json", side_effect=OSError("report write")):
                with self.assertRaisesRegex(OSError, "report write"):
                    all19.aggregate_slices(
                        slices, registry, output,
                        expected_transfer_scope_sha256="b" * 64)
            self.assertEqual(output.read_bytes(), b"PRIOR OUTPUT")
            self.assertEqual(report.read_bytes(), b"PRIOR REPORT")

    def test_slice_destination_parameter_defaults_to_aarau_and_accepts_registry_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            output = directory / "slice.gz"
            metadata = {
                "service_date": "2026-10-27",
                "count.candidate_first_board_events": "0",
                "count.quarantined_frequency_pairs": "0",
                "count.quarantined_non_exact_pairs": "0",
            }
            board_metadata = {
                "service_date": "2026-10-27", "count.boundary_quarantined": "0",
                "count.unassigned": "0",
            }
            transfer_metadata = {
                "service_date": "2026-10-27",
                "count.status.in_seat_candidate_unvalidated": "0",
            }
            checked = lambda path, expected, label: pathlib.Path(path)
            with mock.patch.object(event_slice, "_checked", side_effect=checked), \
                    mock.patch.object(event_slice.route_profile, "_load_connections",
                                      return_value=([], metadata)), \
                    mock.patch.object(event_slice.route_profile, "_load_rules",
                                      return_value=([], transfer_metadata)), \
                    mock.patch.object(event_slice, "_board_assignments",
                                      return_value=({}, board_metadata)), \
                    mock.patch.object(event_slice.route_profile, "_target_children",
                                      return_value=(["TARGET"], "PROVISIONAL")) as target:
                event_slice.export_slice(
                    "connections", "transfers", "boards", "targets", output,
                    expected_transfer_scope_sha256=event_slice.route_export.TRANSFER_SCOPE_SHA256,
                    destination_bfs=9999)
            target.assert_called_once_with(pathlib.Path("targets"), 9999)
            self.assertEqual(read_gzip(output)[0]["destinationBfs"], 9999)
            self.assertEqual(event_slice.export_slice.__kwdefaults__["destination_bfs"], 4001)


if __name__ == "__main__":
    unittest.main()
