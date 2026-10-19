#!/usr/bin/env python3
"""Bounded real-input probe for §8 stop nomination; not a release builder."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path


def active_services(day, calendar, exceptions):
    stamp = day.strftime("%Y%m%d")
    weekday = day.strftime("%A").lower()
    active = {
        row["service_id"] for row in calendar
        if row["start_date"] <= stamp <= row["end_date"] and row[weekday] == "1"
    }
    for row in exceptions:
        if row["date"] != stamp:
            continue
        if row["exception_type"] == "1":
            active.add(row["service_id"])
        elif row["exception_type"] == "2":
            active.discard(row["service_id"])
        else:
            raise ValueError("invalid GTFS exception_type")
    return active


def _seconds(value):
    hour, minute, second = map(int, value.split(":"))
    return hour * 3600 + minute * 60 + second


def rank_stations(stops, trips, stop_times, services, inside_stop_ids):
    counts = Counter()
    seen = {}
    for row in stop_times:
        trip = row["trip_id"]
        stop = row["stop_id"]
        if trip not in trips or trips[trip] not in services or stop not in inside_stop_ids:
            continue
        seconds = _seconds(row["departure_time"])
        if not 21600 <= seconds <= 32400:
            continue
        key = (trip, row["stop_sequence"])
        value = (stop, row["departure_time"])
        if key in seen:
            if seen[key] != value:
                raise ValueError("conflicting duplicate trip/stop_sequence")
            continue
        seen[key] = value
        counts[stops[stop].get("parent_station") or stop] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def point_in_ring(point, ring):
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
    return inside


def point_in_polygon(point, polygon):
    return bool(polygon) and point_in_ring(point, polygon[0]) and not any(
        point_in_ring(point, hole) for hole in polygon[1:]
    )


def point_in_multipolygon(point, multipolygon):
    return any(point_in_polygon(point, polygon) for polygon in multipolygon)


def representative_point(multipolygon):
    polygon = max(multipolygon, key=lambda p: abs(_ring_area(p[0])))
    ring = polygon[0]
    ys = sorted({p[1] for p in ring})
    candidates = [(ys[0] + ys[-1]) / 2]
    candidates += [(a + b) / 2 for a, b in zip(ys, ys[1:])]
    for y in candidates:
        xs = []
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > y) != (y2 > y):
                xs.append((x2 - x1) * (y - y1) / (y2 - y1) + x1)
        for left, right in zip(sorted(xs)[::2], sorted(xs)[1::2]):
            point = ((left + right) / 2, y)
            if point_in_polygon(point, polygon):
                return point
    raise ValueError("polygon has no representative point")


def _ring_area(ring):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:])) / 2


def population_centre(cells, multipolygon):
    east = north = total = 0
    for row in cells:
        try:
            population = int(row["BBTOT"])
            point = (float(row["E_KOORD"]) + 50, float(row["N_KOORD"]) + 50)
        except (ValueError, TypeError):
            continue
        if population > 0 and point_in_multipolygon(point, multipolygon):
            east += point[0] * population
            north += point[1] * population
            total += population
    if total:
        return ((east / total, north / total), "statpop", total)
    return (representative_point(multipolygon), "polygon-representative-point", 0)


def assign_stops(stops, polygons):
    assigned = {bfs: set() for bfs in polygons}
    for stop_id, point in stops.items():
        for bfs, multipolygon in polygons.items():
            if point_in_multipolygon(point, multipolygon):
                assigned[bfs].add(stop_id)
                break
    return assigned


def _decode_topology(topology, wanted):
    scale = topology.get("transform", {}).get("scale", [1, 1])
    translate = topology.get("transform", {}).get("translate", [0, 0])
    decoded = []
    for arc in topology["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
        decoded.append(points)

    def arc(index):
        return decoded[index] if index >= 0 else list(reversed(decoded[~index]))

    def ring(indices):
        points = []
        for index in indices:
            part = arc(index)
            points.extend(part if not points else part[1:])
        return points

    result = {}
    for geometry in topology["objects"]["gemeinden"]["geometries"]:
        bfs = str(geometry["id"])
        if bfs not in wanted:
            continue
        arcs = geometry["arcs"]
        if geometry["type"] == "Polygon":
            result[bfs] = [[ring(indices) for indices in arcs]]
        elif geometry["type"] == "MultiPolygon":
            result[bfs] = [[ring(indices) for indices in polygon] for polygon in arcs]
    return result


def wgs84_to_lv95(lon, lat):
    lat_s = lat * 3600
    lon_s = lon * 3600
    lat_aux = (lat_s - 169028.66) / 10000
    lon_aux = (lon_s - 26782.5) / 10000
    east = 2600072.37 + 211455.93 * lon_aux - 10938.51 * lon_aux * lat_aux - 0.36 * lon_aux * lat_aux**2 - 44.54 * lon_aux**3
    north = 1200147.07 + 308807.95 * lat_aux + 3745.25 * lon_aux**2 + 76.63 * lat_aux**2 - 194.56 * lon_aux**2 * lat_aux + 119.79 * lat_aux**3
    return east, north


def _reader(archive, name):
    return csv.DictReader(io.TextIOWrapper(archive.open(name), encoding="utf-8-sig", newline=""))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(gtfs_path, statpop_path, map_path, day):
    wanted = {"4001": "Aarau", "4201": "Lenzburg"}
    topology = json.loads(Path(map_path).read_text())
    polygons = _decode_topology(topology, wanted)
    if set(polygons) != set(wanted):
        raise ValueError("required municipality polygons absent")

    centres = {}
    accumulators = {bfs: [0.0, 0.0, 0] for bfs in wanted}
    with open(statpop_path, encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source, delimiter=";"):
            try:
                population = int(row["BBTOT"])
                point = (float(row["E_KOORD"]) + 50, float(row["N_KOORD"]) + 50)
            except (ValueError, TypeError):
                continue
            if population <= 0:
                continue
            for bfs in wanted:
                if point_in_multipolygon(point, polygons[bfs]):
                    acc = accumulators[bfs]
                    acc[0] += point[0] * population
                    acc[1] += point[1] * population
                    acc[2] += population
                    break
    for bfs, (east, north, population) in accumulators.items():
        centres[bfs] = {
            "point_lv95": [east / population, north / population] if population else list(representative_point(polygons[bfs])),
            "source": "statpop" if population else "polygon-representative-point",
            "population": population,
        }

    with zipfile.ZipFile(gtfs_path) as archive:
        calendar = _reader(archive, "calendar.txt")
        stamp = day.strftime("%Y%m%d")
        exceptions = (row for row in _reader(archive, "calendar_dates.txt") if row["date"] == stamp)
        services = active_services(day, calendar, exceptions)
        trips = {row["trip_id"]: row["service_id"] for row in _reader(archive, "trips.txt") if row["service_id"] in services}
        stops = {}
        coordinates = {}
        for row in _reader(archive, "stops.txt"):
            stops[row["stop_id"]] = row
            if row.get("stop_lon") and row.get("stop_lat"):
                coordinates[row["stop_id"]] = wgs84_to_lv95(float(row["stop_lon"]), float(row["stop_lat"]))
        assignments = assign_stops(coordinates, polygons)
        rankings = {bfs: Counter() for bfs in wanted}
        seen = {}
        scanned = 0
        for row in _reader(archive, "stop_times.txt"):
            scanned += 1
            stop = row["stop_id"]
            bfs = next((key for key in wanted if stop in assignments[key]), None)
            if bfs is None or trips.get(row["trip_id"]) not in services:
                continue
            if not 21600 <= _seconds(row["departure_time"]) <= 32400:
                continue
            key = (row["trip_id"], row["stop_sequence"])
            value = (stop, row["departure_time"])
            if key in seen:
                if seen[key] != value:
                    raise ValueError("conflicting duplicate trip/stop_sequence")
                continue
            seen[key] = value
            parent = stops[stop].get("parent_station") or stop
            rankings[bfs][parent] += 1
    results = {}
    for bfs, name in wanted.items():
        ordered = sorted(rankings[bfs].items(), key=lambda item: (-item[1], item[0]))
        results[bfs] = {"name": name, "inside_stop_count": len(assignments[bfs]), "nominated_parent": ordered[0][0] if ordered else None, "departure_count": ordered[0][1] if ordered else 0, "population_centre": centres[bfs]}
    return {"reference_date": day.isoformat(), "stop_times_rows_scanned": scanned, "municipalities": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gtfs", required=True)
    parser.add_argument("--statpop", required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument("--date", default="2026-11-17")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = run(args.gtfs, args.statpop, args.map, dt.date.fromisoformat(args.date))
    result["inputs"] = {str(path): sha256(path) for path in (args.gtfs, args.statpop, args.map)}
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n")
    print(payload)


if __name__ == "__main__":
    main()
