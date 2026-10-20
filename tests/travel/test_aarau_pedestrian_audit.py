"""Synthetic pedestrian-profile tests; no fixture is a real route."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "travel"))

from aarau_pedestrian_audit import build_graph, shortest_path


class PedestrianAuditTests(unittest.TestCase):
    def test_disallowed_foot_and_private_access_are_excluded(self):
        ways = [
            (10, [1, 2], {"highway": "residential", "foot": "no"}),
            (11, [2, 3], {"highway": "service", "access": "private"}),
        ]
        graph, rejected = build_graph(ways, {}, {1: (0, 0), 2: (1, 0), 3: (2, 0)})
        self.assertEqual(dict(graph), {})
        self.assertEqual({r[1] for r in rejected}, {"foot=no", "access=private"})

    def test_barrier_without_explicit_foot_passage_breaks_path(self):
        ways = [(10, [1, 2, 3], {"highway": "footway"})]
        graph, rejected = build_graph(
            ways, {2: {"barrier": "fence"}}, {1: (0, 0), 2: (1, 0), 3: (2, 0)})
        self.assertIsNone(shortest_path(graph, 1, 3))
        self.assertIn((2, "barrier=fence"), rejected)

    def test_explicit_foot_oneway_is_directional(self):
        ways = [(10, [1, 2, 3], {"highway": "path", "oneway:foot": "yes"})]
        graph, _ = build_graph(ways, {}, {1: (0, 0), 2: (1, 0), 3: (2, 0)})
        self.assertEqual(shortest_path(graph, 1, 3)[1], [1, 2, 3])
        self.assertIsNone(shortest_path(graph, 3, 1))

    def test_connector_must_be_source_evidenced(self):
        ways = [(10, [1, 2], {"highway": "footway"})]
        graph, _ = build_graph(ways, {}, {1: (0, 0), 2: (1, 0)})
        self.assertIsNone(shortest_path(graph, None, 2))


if __name__ == "__main__":
    unittest.main()
