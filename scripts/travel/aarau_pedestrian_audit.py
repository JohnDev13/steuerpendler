#!/usr/bin/env python3
"""Fail-closed, bounded pedestrian audit for the Aarau pilot.

The reusable graph functions have no OSM dependency.  The CLI reads only the
frozen local PBF and writes an audit artifact outside Git.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
from collections import defaultdict
from pathlib import Path

ALLOWED_HIGHWAYS = {
    "residential", "living_street", "footway", "pedestrian", "path", "track",
    "service", "steps", "unclassified", "tertiary", "secondary", "primary",
}
FOOT_ALLOW = {"yes", "designated", "permissive", "destination"}
IMPASSABLE_BARRIERS = {
    "fence", "wall", "retaining_wall", "hedge", "ditch", "chain", "jersey_barrier",
}
BOUNDS = (8.14, 47.375, 8.215, 47.42)
EXPECTED_PBF_SHA256 = "16dd2c5cedaf63205fcb21c50b723e43b1b3953a8ffef32e5683ec91c0ea84d1"
ENTRANCE_NODE = 1209130473


def distance_m(a, b):
    lon1, lat1 = a
    lon2, lat2 = b
    lat = math.radians((lat1 + lat2) / 2)
    return math.hypot((lon2 - lon1) * 111320 * math.cos(lat), (lat2 - lat1) * 111194.9)


def _way_policy(tags):
    if tags.get("highway") not in ALLOWED_HIGHWAYS:
        return None, "highway-not-pedestrian-candidate"
    if tags.get("foot") in {"no", "private"}:
        return None, f"foot={tags['foot']}"
    if tags.get("access") in {"no", "private"} and tags.get("foot") not in FOOT_ALLOW:
        return None, f"access={tags['access']}"
    direction = tags.get("oneway:foot")
    if direction in {"yes", "1", "true"}:
        return 1, None
    if direction == "-1":
        return -1, None
    return 0, None


def _node_block_reason(tags):
    if tags.get("foot") in {"no", "private"}:
        return f"foot={tags['foot']}"
    if tags.get("access") in {"no", "private"} and tags.get("foot") not in FOOT_ALLOW:
        return f"access={tags['access']}"
    barrier = tags.get("barrier")
    if barrier in IMPASSABLE_BARRIERS and tags.get("foot") not in FOOT_ALLOW:
        return f"barrier={barrier}"
    return None


def build_graph(ways, node_tags, coordinates):
    graph = defaultdict(list)
    rejected = []
    blocked = {}
    for node_id, tags in node_tags.items():
        reason = _node_block_reason(tags)
        if reason:
            blocked[node_id] = reason
            rejected.append((node_id, reason))
    for way_id, node_ids, tags in ways:
        direction, reason = _way_policy(tags)
        if reason:
            rejected.append((way_id, reason))
            continue
        for left, right in zip(node_ids, node_ids[1:]):
            if left not in coordinates or right not in coordinates or left == right:
                continue
            if left in blocked or right in blocked:
                continue
            length = distance_m(coordinates[left], coordinates[right])
            if length <= 0:
                continue
            if direction >= 0:
                graph[left].append((right, length, way_id))
            if direction <= 0:
                graph[right].append((left, length, way_id))
    return graph, rejected


def shortest_path(graph, start, target):
    if start is None or target is None:
        return None
    queue = [(0.0, start)]
    best = {start: 0.0}
    previous = {}
    while queue:
        total, node = heapq.heappop(queue)
        if total != best[node]:
            continue
        if node == target:
            nodes = [node]
            ways = []
            while node != start:
                node, way_id = previous[node]
                nodes.append(node)
                ways.append(way_id)
            return total, list(reversed(nodes)), list(reversed(ways))
        for other, length, way_id in graph.get(node, ()):
            candidate = total + length
            if candidate < best.get(other, math.inf):
                best[other] = candidate
                previous[other] = (node, way_id)
                heapq.heappush(queue, (candidate, other))
    return None


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def real_probe(pbf, origins_path):
    actual_hash = _sha256(pbf)
    if actual_hash != EXPECTED_PBF_SHA256:
        raise RuntimeError(f"PBF SHA-256 mismatch: {actual_hash}")
    try:
        import osmium  # type: ignore
        from pyproj import Transformer  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            'Python 3.11 with osmium==4.3.2 and pyproj==3.7.2 is required '
            'for the frozen OSM probe') from exc

    coordinates = {}
    node_tags = {}

    class Nodes(osmium.SimpleHandler):
        def node(self, node):
            if node.location.valid() and BOUNDS[0] <= node.location.lon <= BOUNDS[2] and BOUNDS[1] <= node.location.lat <= BOUNDS[3]:
                coordinates[node.id] = (node.location.lon, node.location.lat)
                tags = dict(node.tags)
                if tags:
                    node_tags[node.id] = tags

    Nodes().apply_file(str(pbf))
    ways = []
    containing_entrance = []
    member_way_ids = set()
    relations = []

    class WaysAndRelations(osmium.SimpleHandler):
        def way(self, way):
            ids = [member.ref for member in way.nodes]
            tags = dict(way.tags)
            if ENTRANCE_NODE in ids:
                containing_entrance.append({"id": way.id, "tags": tags, "nodes": ids})
                member_way_ids.add(way.id)
            if any(node in coordinates for node in ids):
                ways.append((way.id, ids, tags))

        def relation(self, relation):
            members = [(member.type, member.ref, member.role) for member in relation.members]
            if any((kind == "n" and ref == ENTRANCE_NODE) or (kind == "w" and ref in member_way_ids) for kind, ref, _ in members):
                relations.append({"id": relation.id, "tags": dict(relation.tags), "matching_members": [m for m in members if (m[0] == "n" and m[1] == ENTRANCE_NODE) or (m[0] == "w" and m[1] in member_way_ids)]})

    # PBF types are ordered nodes → ways → relations. One combined pass keeps
    # entrance-way IDs available when relation members are inspected.
    WaysAndRelations().apply_file(str(pbf))
    graph, rejected = build_graph(ways, node_tags, coordinates)
    origins = json.loads(origins_path.read_text())
    transformer = Transformer.from_crs(2056, 4326, always_xy=True)
    cases = {
        "staufen_near": origins["municipalities"]["4210"]["near_example_10th_closest_cell"]["cell_centre_lv95"],
        "staufen_far": origins["municipalities"]["4210"]["far_example_10th_farthest_cell"]["cell_centre_lv95"],
        "niederlenz_reference": origins["municipalities"]["4204"]["population_weighted_centre_lv95"],
    }
    audited = {}
    graph_nodes = set(graph)
    for edges in graph.values():
        graph_nodes.update(edge[0] for edge in edges)
    for label, point in cases.items():
        origin = transformer.transform(*point)
        nearest_distance, nearest_node = min((distance_m(origin, coordinates[node]), node) for node in graph_nodes)
        path = shortest_path(graph, nearest_node, ENTRANCE_NODE)
        audited[label] = {
            "status": "UNVERIFIED",
            "origin_lv95": point,
            "nearest_network_node": nearest_node,
            "unevidenced_connector_m": round(nearest_distance, 3),
            "missing_evidence": "inhabited-cell/population centre is not an OSM node and no source geometry proves a legal connector to the nearest network node",
            "network_diagnostic": None if path is None else {
                "meters_excluding_origin_connector": round(path[0], 3),
                "node_ids": path[1],
                "way_ids_by_segment": path[2],
                "unique_way_ids": list(dict.fromkeys(path[2])),
            },
            "accepted_walk_seconds": None,
        }
    entrance_tags = node_tags.get(ENTRANCE_NODE, {})
    return {
        "status": "NO_WALK_ACCEPTED",
        "pbf": str(pbf),
        "pbf_sha256": actual_hash,
        "bounds_wgs84": BOUNDS,
        "entrance": {
            "node_id": ENTRANCE_NODE,
            "coordinates_wgs84": coordinates.get(ENTRANCE_NODE),
            "tags": entrance_tags,
            "containing_ways": containing_entrance,
            "relations": relations,
            "correspondence_status": "VERIFIED" if entrance_tags.get("entrance") and any(item["tags"].get("railway") == "station" or item["tags"].get("public_transport") == "station" for item in containing_entrance + relations) else "UNVERIFIED",
        },
        "profile": {
            "generic_oneway_ignored_for_foot": True,
            "explicit_oneway_foot_obeyed": True,
            "barriers_fail_closed": sorted(IMPASSABLE_BARRIERS),
            "rejected_feature_count": len(rejected),
        },
        "cases": audited,
        "limitations": [
            "Network-only diagnostics exclude the unevidenced origin connector and therefore are not durations.",
            "This bounded extractor does not evaluate turn restrictions or conditional/time-based tags.",
            "No municipality eligibility or timetable result follows from this audit.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pbf", type=Path, required=True)
    parser.add_argument("--origins", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = real_probe(args.pbf, args.origins)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "status": report["status"], "cases": {key: value["status"] for key, value in report["cases"].items()}}))


if __name__ == "__main__":
    main()
