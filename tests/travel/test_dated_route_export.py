"""Synthetic tests for the deterministic all-destination dated route exporter."""
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))

import dated_route_profile as profile
import dated_route_export as export


def ride(number, trip, start, end, departure, arrival, *, pickup=0, drop_off=0):
    return profile.Connection(number, trip, f"R-{trip}", "S", 1, 2,
                              departure, arrival, start, end, pickup, drop_off)


def transfer(number, stop):
    return profile.TransferRule(number, stop, stop, "", "", "", "", 2, 0,
                                "", 0, "potentially_applicable")


def groups():
    return {str(4000 + value): [f"Z{value}"] for value in range(1, 20)}


def lineage():
    return dict(zip(export.SOURCE_KEYS, ("a" * 64, "b" * 64, "c" * 64,
                                         "d" * 64, "e" * 64)))


class DatedRouteExportTests(unittest.TestCase):
    def build(self, connections=(), assignments=None, municipalities=None):
        return export.build_export(
            connections, (), groups(), assignments or {},
            municipalities or [str(value) for value in range(1, 2111)],
            service_date="2026-10-27",
            source_sha256=lineage())

    def test_all_19_by_2110_unknown_coverage_with_zero_routes(self):
        payload = self.build()
        self.assertEqual(len(payload["destinations"]), 19)
        for destination in payload["destinations"].values():
            self.assertEqual(len(destination["statuses"]), 2110)
            self.assertTrue(all(row["status"] == "unknown"
                                for row in destination["statuses"].values()))
            self.assertEqual(destination["directOnly"], {})

    def test_elapsed_boundary_duplicate_origin_and_deterministic_bytes(self):
        connections = [
            ride(1, "EARLY", "A", "Z1", 23400, 25200),
            ride(2, "OVER", "A", "Z1", 23401, 25202),
            ride(3, "LATER-FAST", "B", "Z1", 24000, 24200),
        ]
        payload = self.build(connections, {"A": "1", "B": "1"})
        row = payload["destinations"]["4001"]["statuses"]["1"]
        self.assertEqual((row["status"], row["elapsedSeconds"], row["firstBoardStopId"]),
                         ("best_found_unproven", 200, "B"))
        encoded = export.encode_export(payload)
        self.assertEqual(encoded, export.encode_export(
            self.build(list(reversed(connections)), {"B": "1", "A": "1"})))
        self.assertNotIn(b'outside_elapsed_cap', encoded)

    def test_direct_alternative_retained_when_transfer_is_faster(self):
        connections = [ride(1, "BUS", "A", "X", 23400, 23500),
                       ride(2, "TRAIN", "X", "Z1", 23500, 23600),
                       ride(3, "DIRECT", "A", "Z1", 23400, 24000)]
        payload = export.build_export(
            connections, [transfer(1, "X")], groups(), {"A": "1"}, ["1"],
            service_date="2026-10-27", source_sha256=lineage())
        destination = payload["destinations"]["4001"]
        self.assertEqual(destination["statuses"]["1"]["elapsedSeconds"], 200)
        self.assertEqual(destination["statuses"]["1"]["transferCount"], 1)
        self.assertEqual(destination["directOnly"]["1"]["elapsedSeconds"], 600)

    def test_four_changes_and_pickup_dropoff_fail_closed(self):
        connections = []
        rules = []
        for index in range(5):
            start = chr(ord("A") + index)
            end = "Z1" if index == 4 else chr(ord("A") + index + 1)
            connections.append(ride(index + 1, f"T{index}", start, end,
                                    23400 + index * 200, 23500 + index * 200))
            if index < 4:
                rules.append(transfer(index + 1, end))
        connections += [ride(20, "NO-PICKUP", "P", "Z1", 23400, 23500, pickup=1),
                        ride(21, "NO-DROPOFF", "Q", "Z1", 23400, 23500, drop_off=1)]
        payload = export.build_export(
            connections, rules, groups(), {"A": "1", "P": "2", "Q": "3"},
            ["1", "2", "3"], service_date="2026-10-27",
            source_sha256=lineage())
        statuses = payload["destinations"]["4001"]["statuses"]
        self.assertEqual(statuses["1"]["transferCount"], 4)
        self.assertEqual(statuses["2"]["status"], "unknown")
        self.assertEqual(statuses["3"]["status"], "unknown")

    def test_vs_route_evidence_is_not_tax_quarantined_by_exporter(self):
        payload = self.build([ride(1, "VS", "SION", "Z1", 23400, 23500)], {"SION": "6266"}, ["6266"])
        self.assertEqual(payload["destinations"]["4001"]["statuses"]["6266"]["status"],
                         "best_found_unproven")
        self.assertNotIn("tax", json.dumps(payload).lower())

    def test_wrong_date_authority_and_pins_fail(self):
        with self.assertRaisesRegex(export.RouteExportError, "service date"):
            export.build_export([], [], groups(), {}, ["1"], service_date="2026-10-28",
                                source_sha256={})
        with self.assertRaisesRegex(export.RouteExportError, "19 destination"):
            export.build_export([], [], {"1": ["Z"]}, {}, ["1"], service_date="2026-10-27",
                                source_sha256={})
        with self.assertRaisesRegex(export.RouteExportError, "Gemeinde authority"):
            export.build_export([], [], groups(), {}, ["1", "1"], service_date="2026-10-27",
                                source_sha256={key: "a" * 64 for key in export.SOURCE_KEYS})
        with self.assertRaisesRegex(export.RouteExportError, "source SHA"):
            export.build_export([], [], groups(), {}, ["1"], service_date="2026-10-27",
                                source_sha256={key: "bad" for key in export.SOURCE_KEYS})


if __name__ == "__main__":
    unittest.main()
