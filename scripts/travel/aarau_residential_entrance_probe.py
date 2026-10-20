#!/usr/bin/env python3
"""Bounded frozen-OSM probe for a mapped residential entrance in Staufen."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from aarau_pedestrian_audit import (
    BOUNDS,
    ENTRANCE_NODE,
    EXPECTED_PBF_SHA256,
    build_graph,
    distance_m,
    shortest_path,
)

RESIDENTIAL_BUILDINGS = {"house", "detached", "terrace", "apartments", "residential"}
ORIGIN_LV95 = (2655050.0, 1248550.0)
DEFAULT_RADIUS_M = 250.0
WALK_SPEED_M_S = 1.2
WALK_CAP_SECONDS = 900.0


def _is_explicit_entrance(tags):
    return bool(tags.get("entrance")) and tags.get("entrance") != "no"


def evaluate_entrances(ways, node_tags, coordinates, origin_wgs84, station_node, radius_m):
    """Evaluate way-backed residential entrance nodes against the directed graph."""
    graph_ways = []
    residential = []
    rejected = Counter()
    scanned_buildings = 0

    for way_id, node_ids, tags in ways:
        if "building" in tags:
            scanned_buildings += 1
            if tags.get("building") not in RESIDENTIAL_BUILDINGS:
                rejected["nonresidential_building"] += 1
                continue
            entrances = [node_id for node_id in node_ids if _is_explicit_entrance(node_tags.get(node_id, {}))]
            if not entrances:
                rejected["missing_explicit_entrance"] += 1
            else:
                for node_id in dict.fromkeys(entrances):
                    residential.append((node_id, way_id, tags))
        if "highway" in tags:
            graph_ways.append((way_id, node_ids, tags))

    graph, _ = build_graph(graph_ways, node_tags, coordinates)
    graph_nodes = set(graph)
    for edges in graph.values():
        graph_nodes.update(edge[0] for edge in edges)

    accepted = []
    for node_id, building_way_id, building_tags in residential:
        coordinate = coordinates.get(node_id)
        if coordinate is None:
            rejected["entrance_coordinate_unavailable"] += 1
            continue
        radial_distance = distance_m(origin_wgs84, coordinate)
        if radial_distance > radius_m:
            rejected["outside_radius"] += 1
            continue
        if node_id not in graph_nodes:
            rejected["entrance_not_on_pedestrian_graph"] += 1
            continue
        path = shortest_path(graph, node_id, station_node)
        if path is None:
            rejected["no_directed_path_to_station_entrance"] += 1
            continue
        network_m, path_nodes, path_ways = path
        walk_seconds = network_m / WALK_SPEED_M_S
        if walk_seconds > WALK_CAP_SECONDS:
            rejected["path_exceeds_15_minute_cap"] += 1
            continue
        accepted.append({
            "entrance_node_id": node_id,
            "entrance_tags": node_tags[node_id],
            "entrance_coordinates_wgs84": coordinate,
            "building_way_id": building_way_id,
            "building_tags": building_tags,
            "radius_distance_m": radial_distance,
            "network_distance_m": network_m,
            "walk_seconds": walk_seconds,
            "walk_ceiled_minutes": int(-(-walk_seconds // 60)),
            "path_node_ids": path_nodes,
            "path_way_ids_by_segment": path_ways,
            "unique_path_way_ids": list(dict.fromkeys(path_ways)),
        })

    accepted.sort(key=lambda item: (item["network_distance_m"], item["entrance_node_id"], item["building_way_id"]))
    return {
        "status": "CONNECTED_RESIDENTIAL_ENTRANCE_FOUND" if accepted else "NO_RESIDENTIAL_ENTRANCE_CONNECTED",
        "scanned_buildings": scanned_buildings,
        "scanned_candidate_entrances": len(residential),
        "rejected_reasons": dict(sorted(rejected.items())),
        "accepted_candidates": accepted,
    }


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def real_probe(pbf, radius_m):
    actual_hash = _sha256(pbf)
    if actual_hash != EXPECTED_PBF_SHA256:
        raise RuntimeError(f"PBF SHA-256 mismatch: {actual_hash}")
    try:
        import osmium  # type: ignore
        from pyproj import Transformer  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("osmium==4.3.2 and pyproj==3.7.2 are required") from exc

    coordinates = {}
    node_tags = {}

    class Nodes(osmium.SimpleHandler):
        def node(self, node):
            if (node.location.valid() and BOUNDS[0] <= node.location.lon <= BOUNDS[2]
                    and BOUNDS[1] <= node.location.lat <= BOUNDS[3]):
                coordinates[node.id] = (node.location.lon, node.location.lat)
                tags = dict(node.tags)
                if tags:
                    node_tags[node.id] = tags

    Nodes().apply_file(str(pbf))
    ways = []

    class Ways(osmium.SimpleHandler):
        def way(self, way):
            node_ids = [member.ref for member in way.nodes]
            if any(node_id in coordinates for node_id in node_ids):
                tags = dict(way.tags)
                if "highway" in tags or "building" in tags:
                    ways.append((way.id, node_ids, tags))

    # PBF ordering permits one node pass and one combined building/graph way pass.
    Ways().apply_file(str(pbf))
    origin_wgs84 = Transformer.from_crs(2056, 4326, always_xy=True).transform(*ORIGIN_LV95)
    result = evaluate_entrances(ways, node_tags, coordinates, origin_wgs84, ENTRANCE_NODE, radius_m)
    result.update({
        "pbf": str(pbf),
        "pbf_sha256": actual_hash,
        "bounds_wgs84": BOUNDS,
        "origin": {
            "description": "Staufen near inhabited-cell centre; not a verified residence",
            "lv95": ORIGIN_LV95,
            "wgs84": origin_wgs84,
            "candidate_radius_m": radius_m,
        },
        "station_entrance_node_id": ENTRANCE_NODE,
        "walk_policy": {
            "speed_m_s": WALK_SPEED_M_S,
            "external_walk_cap_seconds": WALK_CAP_SECONDS,
            "entrance_to_platform_seconds_added": 0,
            "direction_and_barrier_policy": "aarau_pedestrian_audit.build_graph",
        },
        "limitations": [
            "A candidate is a separate home-like pilot entrance, not the representative municipality origin.",
            "The bounded graph does not establish nationwide routing, reference-day acceptance, or travel release.",
            "Turn restrictions and conditional/time-based access tags are not evaluated; affected paths require further review.",
        ],
    })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pbf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--radius-m", type=float, default=DEFAULT_RADIUS_M)
    args = parser.parse_args()
    if args.radius_m <= 0:
        parser.error("--radius-m must be positive")
    report = real_probe(args.pbf, args.radius_m)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "status": report["status"],
        "scanned_candidate_entrances": report["scanned_candidate_entrances"],
        "accepted_candidates": len(report["accepted_candidates"]),
    }))


if __name__ == "__main__":
    main()
