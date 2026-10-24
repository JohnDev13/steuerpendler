"""Tests for exact-day applicability evidence over directed transfer rules."""
import csv
import datetime as dt
import hashlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))

import dated_active_services as active_services
import dated_transfer_index as transfer_index
import dated_transfer_scope as scope

DAY = dt.date(2026, 10, 27)
TRANSFER_HEADER = (
    "from_stop_id,to_stop_id,from_route_id,to_route_id,from_trip_id,"
    "to_trip_id,transfer_type,min_transfer_time,service_id\n"
)


def _csv(fields, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _feed(path):
    calendar_fields = [
        "service_id", "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday", "start_date", "end_date",
    ]
    tables = {
        "calendar.txt": _csv(calendar_fields, [
            {"service_id": "BASE", "monday": "0", "tuesday": "1",
             "wednesday": "0", "thursday": "0", "friday": "0",
             "saturday": "0", "sunday": "0", "start_date": "20260101",
             "end_date": "20261231"},
            {"service_id": "REMOVED", "monday": "0", "tuesday": "1",
             "wednesday": "0", "thursday": "0", "friday": "0",
             "saturday": "0", "sunday": "0", "start_date": "20260101",
             "end_date": "20261231"},
        ]),
        "calendar_dates.txt": _csv(
            ["service_id", "date", "exception_type"], [
                {"service_id": "ADDED", "date": "20261027", "exception_type": "1"},
                {"service_id": "REMOVED", "date": "20261027", "exception_type": "2"},
            ]),
        "trips.txt": _csv(["route_id", "service_id", "trip_id"], [
            {"route_id": "R1", "service_id": "BASE", "trip_id": "T_ACTIVE"},
            {"route_id": "R2", "service_id": "ADDED", "trip_id": "T_ADDED"},
            {"route_id": "RI", "service_id": "REMOVED", "trip_id": "T_INACTIVE"},
        ]),
        "frequencies.txt": _csv(
            ["trip_id", "start_time", "end_time", "headway_secs", "exact_times"], []),
        "transfers.txt": TRANSFER_HEADER + "".join([
            "BUS,RAIL,,,,,2,240,\n",
            "RAIL,BUS,,,,,2,999,\n",
            "BUS,RAIL,R1,R2,T_ACTIVE,T_ADDED,1,,\n",
            "BUS,RAIL,R1,RI,T_ACTIVE,T_INACTIVE,1,,\n",
            ",,R1,R2,T_ACTIVE,T_ADDED,4,,ADDED\n",
            ",,R1,R2,T_ACTIVE,T_ADDED,4,,REMOVED\n",
            ",,R1,R2,T_ACTIVE,T_ADDED,4,,NEVER-LISTED\n",
            "BUS,RAIL,WRONG,R2,T_ACTIVE,T_ADDED,2,300,BASE\n",
        ]),
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in tables.items():
            archive.writestr(name, value)
    return _sha256(path)


class DatedTransferScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = pathlib.Path(temporary.name)
        self.feed = self.directory / "feed.zip"
        self.feed_sha = _feed(self.feed)
        self.active = self.directory / "active.sqlite"
        active_services.build_active_trip_manifest(
            self.feed, self.feed_sha, DAY, self.active,
            expected_active_trips=2, expected_active_services=2,
            expected_frequency_templates=0,
        )
        self.active_sha = _sha256(self.active)
        self.rules = self.directory / "rules.sqlite"
        transfer_index.build_dated_transfer_index(
            self.feed, self.feed_sha, self.rules,
            service_date=DAY.isoformat(), expected_total_rows=8,
            expected_type_counts={"1": 2, "2": 3, "4": 3},
        )
        self.rules_sha = _sha256(self.rules)
        self.output = self.directory / "scope.sqlite"

    def build(self, **changes):
        arguments = {
            "feed_path": self.feed,
            "expected_feed_sha256": self.feed_sha,
            "active_trip_path": self.active,
            "expected_active_trip_sha256": self.active_sha,
            "transfer_rule_path": self.rules,
            "expected_transfer_rule_sha256": self.rules_sha,
            "service_day": DAY,
            "output_path": self.output,
            "expected_in_seat_candidates": 1,
            "expected_timed_trip_pairs": 1,
        }
        arguments.update(changes)
        return scope.build_dated_transfer_scope(**arguments)

    def query(self, sql, parameters=()):
        database = sqlite3.connect(self.output)
        try:
            return database.execute(sql, parameters).fetchall()
        finally:
            database.close()

    def test_calendar_exceptions_service_classes_and_inactive_trip(self):
        manifest = self.build()
        rows = self.query("""
            SELECT source_row_number, service_date_applicability,
                   from_trip_status, to_trip_status, applicability_status
            FROM transfer_scope ORDER BY source_row_number
        """)
        self.assertEqual(rows, [
            (2, "unrestricted", "not_selected", "not_selected", "potentially_applicable"),
            (3, "unrestricted", "not_selected", "not_selected", "potentially_applicable"),
            (4, "unrestricted", "active", "active", "potentially_applicable"),
            (5, "unrestricted", "active", "not_active", "inactive_trip"),
            (6, "active", "active", "active", "in_seat_candidate_unvalidated"),
            (7, "known_inactive", "active", "active", "inactive_service"),
            (8, "unknown", "active", "active", "unresolved_service"),
            (9, "active", "active", "active", "unresolved_route_conflict"),
        ])
        self.assertEqual(manifest["counts"]["in_seat_both_trips_active_service_active"], 1)
        self.assertEqual(manifest["counts"]["timed_both_trips_active"], 1)
        self.assertEqual(manifest["service_counts"], {"active": 2, "known": 3})

    def test_preserves_direction_selectors_source_and_type4_semantics(self):
        self.build()
        forward = self.query("""
            SELECT min_transfer_time, applicability_status
            FROM transfer_scope
            WHERE from_stop_id='BUS' AND to_stop_id='RAIL'
              AND transfer_type=2 AND from_trip_id=''
        """)
        reverse = self.query("""
            SELECT min_transfer_time FROM transfer_scope
            WHERE from_stop_id='RAIL' AND to_stop_id='BUS'
        """)
        in_seat = self.query("""
            SELECT semantic_class, applicability_status, reason,
                   source_rule_id, source_row_number, source_fields_json
            FROM transfer_scope WHERE source_row_number=6
        """)[0]
        self.assertEqual(forward, [(240, "potentially_applicable")])
        self.assertEqual(reverse, [(999,)])
        self.assertEqual(in_seat[:2], ("in_seat", "in_seat_candidate_unvalidated"))
        self.assertIn("same-vehicle", in_seat[2])
        self.assertNotIn("walk", in_seat[2])
        self.assertEqual(in_seat[3:5], (5, 6))
        self.assertEqual(json.loads(in_seat[5])["service_id"], "ADDED")

    def test_active_routes_are_evidence_but_conflicts_remain_unresolved(self):
        self.build()
        row = self.query("""
            SELECT from_route_status, to_route_status, reason
            FROM transfer_scope WHERE source_row_number=9
        """)[0]
        self.assertEqual(row[:2], ("conflicts_active_trip", "matches_active_trip"))
        self.assertIn("route selector conflicts", row[2])

    def test_hash_schema_integrity_date_and_expected_counts_are_pinned(self):
        manifest = self.build()
        self.assertEqual(manifest["source_sha256"], {
            "active_trip_sqlite": self.active_sha,
            "gtfs_zip": self.feed_sha,
            "transfer_rule_sqlite": self.rules_sha,
        })
        self.assertEqual(self.query("PRAGMA integrity_check"), [("ok",)])
        self.assertEqual(self.query("SELECT value FROM metadata WHERE key='service_date'"),
                         [(DAY.isoformat(),)])
        with self.assertRaisesRegex(scope.DatedTransferScopeError, "in-seat candidate count mismatch"):
            self.build(expected_in_seat_candidates=99)

    def test_wrong_source_pin_and_publish_failure_roll_back(self):
        first = self.build()
        old_database = self.output.read_bytes()
        manifest_path = pathlib.Path(f"{self.output}.manifest.json")
        old_manifest = manifest_path.read_bytes()
        with self.assertRaisesRegex(scope.DatedTransferScopeError, "transfer-rule SQLite SHA-256 mismatch"):
            self.build(expected_transfer_rule_sha256="0" * 64)
        self.assertEqual(self.output.read_bytes(), old_database)
        self.assertEqual(manifest_path.read_bytes(), old_manifest)

        real_replace = scope.os.replace

        def fail_manifest(source, destination):
            if pathlib.Path(destination) == manifest_path:
                raise OSError("injected manifest publish failure")
            return real_replace(source, destination)

        with mock.patch.object(scope.os, "replace", side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, "injected manifest publish failure"):
                self.build()
        self.assertEqual(self.output.read_bytes(), old_database)
        self.assertEqual(manifest_path.read_bytes(), old_manifest)
        self.assertEqual(first, json.loads(old_manifest))
        self.assertEqual(list(self.directory.glob(".*.tmp")), [])

    def test_unknown_source_semantic_class_fails_closed(self):
        malformed = self.directory / "malformed.sqlite"
        database = sqlite3.connect(malformed)
        database.execute(f"PRAGMA application_id={transfer_index.APPLICATION_ID}")
        database.execute(f"PRAGMA user_version={transfer_index.SCHEMA_VERSION}")
        database.executescript("""
            CREATE TABLE transfer_rules (
                rule_id INTEGER PRIMARY KEY, source_row_number INTEGER,
                from_stop_id TEXT, to_stop_id TEXT, from_route_id TEXT,
                to_route_id TEXT, from_trip_id TEXT, to_trip_id TEXT,
                transfer_type INTEGER, min_transfer_time INTEGER,
                service_id TEXT, semantic_class TEXT, selector_specificity INTEGER,
                scope_status TEXT, service_date_applicability TEXT,
                source_fields_json TEXT
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
        """)
        values = (1, 2, "A", "B", "", "", "", "", 2, 10, "", "mystery",
                  1, "resolved", "unrestricted_by_service_id", "{}")
        database.execute("INSERT INTO transfer_rules VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
        metadata = {
            "schema_id": transfer_index.SCHEMA_ID,
            "schema_version": str(transfer_index.SCHEMA_VERSION),
            "service_date": DAY.isoformat(),
            "source_sha256": self.feed_sha,
        }
        database.executemany("INSERT INTO metadata VALUES (?,?)", metadata.items())
        database.commit()
        database.close()
        malformed_sha = _sha256(malformed)
        with self.assertRaisesRegex(scope.DatedTransferScopeError, "unsupported semantic class"):
            self.build(transfer_rule_path=malformed,
                       expected_transfer_rule_sha256=malformed_sha,
                       expected_in_seat_candidates=None,
                       expected_timed_trip_pairs=None)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
