"""Synthetic residential-entrance probes; no fixture is a real location."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))

from aarau_residential_entrance_probe import evaluate_entrances


class ResidentialEntranceProbeTests(unittest.TestCase):
    def evaluate(self, ways, node_tags=None, coordinates=None, radius_m=250):
        return evaluate_entrances(
            ways,
            node_tags or {},
            coordinates or {1: (0.0, 0.0), 2: (0.001, 0.0), 3: (0.002, 0.0)},
            (0.0, 0.0),
            3,
            radius_m,
        )

    def test_explicit_residential_entrance_on_graph_has_feasible_trace(self):
        result = self.evaluate(
            [
                (10, [1, 4, 5, 1], {"building": "house", "name": "fixture"}),
                (20, [1, 2, 3], {"highway": "footway"}),
            ],
            {1: {"entrance": "yes"}},
            {1: (0.0, 0.0), 2: (0.001, 0.0), 3: (0.002, 0.0), 4: (0.0, 0.001), 5: (0.001, 0.001)},
        )
        self.assertEqual(result["status"], "CONNECTED_RESIDENTIAL_ENTRANCE_FOUND")
        candidate = result["accepted_candidates"][0]
        self.assertEqual(candidate["entrance_node_id"], 1)
        self.assertEqual(candidate["building_way_id"], 10)
        self.assertEqual(candidate["path_node_ids"], [1, 2, 3])
        self.assertEqual(candidate["path_way_ids_by_segment"], [20, 20])
        self.assertLessEqual(candidate["walk_seconds"], 900)

    def test_residential_building_without_explicit_entrance_is_rejected(self):
        result = self.evaluate([(10, [1, 2, 1], {"building": "detached"})])
        self.assertEqual(result["status"], "NO_RESIDENTIAL_ENTRANCE_CONNECTED")
        self.assertEqual(result["rejected_reasons"]["missing_explicit_entrance"], 1)

    def test_nonresidential_building_is_rejected(self):
        result = self.evaluate(
            [(10, [1, 2, 1], {"building": "commercial"})],
            {1: {"entrance": "yes"}},
        )
        self.assertEqual(result["rejected_reasons"]["nonresidential_building"], 1)
        self.assertEqual(result["scanned_candidate_entrances"], 0)

    def test_entrance_not_on_walk_graph_is_rejected(self):
        result = self.evaluate(
            [
                (10, [1, 4, 5, 1], {"building": "apartments"}),
                (20, [2, 3], {"highway": "footway"}),
            ],
            {1: {"entrance": "main"}},
            {1: (0.0, 0.0), 2: (0.001, 0.0), 3: (0.002, 0.0), 4: (0.0, 0.001), 5: (0.001, 0.001)},
        )
        self.assertEqual(result["rejected_reasons"]["entrance_not_on_pedestrian_graph"], 1)

    def test_barrier_and_wrong_way_direction_prevent_connection(self):
        barrier = self.evaluate(
            [
                (10, [1, 4, 5, 1], {"building": "residential"}),
                (20, [1, 2, 3], {"highway": "path"}),
            ],
            {1: {"entrance": "yes"}, 2: {"barrier": "fence"}},
            {1: (0.0, 0.0), 2: (0.001, 0.0), 3: (0.002, 0.0), 4: (0.0, 0.001), 5: (0.001, 0.001)},
        )
        self.assertEqual(barrier["rejected_reasons"]["entrance_not_on_pedestrian_graph"], 1)
        wrong_way = self.evaluate(
            [
                (10, [1, 4, 5, 1], {"building": "terrace"}),
                (20, [3, 2, 1], {"highway": "path", "oneway:foot": "yes"}),
            ],
            {1: {"entrance": "yes"}},
            {1: (0.0, 0.0), 2: (0.001, 0.0), 3: (0.002, 0.0), 4: (0.0, 0.001), 5: (0.001, 0.001)},
        )
        self.assertEqual(wrong_way["rejected_reasons"]["no_directed_path_to_station_entrance"], 1)

    def test_explicit_entrance_outside_radius_is_rejected(self):
        result = self.evaluate(
            [(10, [1, 2, 1], {"building": "house"})],
            {1: {"entrance": "yes"}},
            {1: (0.01, 0.0), 2: (0.011, 0.0), 3: (0.012, 0.0)},
        )
        self.assertEqual(result["rejected_reasons"]["outside_radius"], 1)


if __name__ == "__main__":
    unittest.main()
