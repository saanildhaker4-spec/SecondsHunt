import unittest

import dijkstar

from ambulance import routing
from tests.helpers import make_world, real_world


def all_pairs(world, mode, period):
    """An independent shortest-path answer (Floyd-Warshall) to check Dijkstar against."""
    names = sorted(world["junctions"])
    big = 1e18
    cost = {(a, b): (0.0 if a == b else big) for a in names for b in names}
    for (a, b), roads in world["between"].items():
        open_roads = [r for r in roads if r["id"] not in world["blocked"]]
        if open_roads:
            best = min(routing.road_cost(r, mode, period) for r in open_roads)
            cost[(a, b)] = min(cost[(a, b)], best)
            cost[(b, a)] = min(cost[(b, a)], best)
    for k in names:
        for i in names:
            for j in names:
                if cost[(i, k)] + cost[(k, j)] < cost[(i, j)]:
                    cost[(i, j)] = cost[(i, k)] + cost[(k, j)]
    return cost


class RoadChoiceTests(unittest.TestCase):

    def setUp(self):
        self.world = make_world()

    def road_names(self, route):
        return [road["name"] for road in route["roads"]]

    def test_dijkstar_is_the_library_in_use(self):
        self.assertTrue(hasattr(dijkstar, "find_path"))
        graph = routing.get_graph(self.world)
        self.assertIsInstance(graph, dijkstar.Graph)

    def test_average_mode_takes_the_quick_road(self):
        route = routing.find_route(self.world, "A", "B", "average", "rush")
        self.assertEqual(self.road_names(route), ["quick"])
        self.assertEqual((route["average"], route["worst"]), (4, 10))

    def test_worst_case_mode_takes_the_steady_road(self):
        route = routing.find_route(self.world, "A", "B", "worst_case", "rush")
        self.assertEqual(self.road_names(route), ["steady"])
        self.assertEqual((route["average"], route["worst"]), (7, 8))

    def test_balanced_mode_is_in_between(self):
        # quick: 4 + 6/2 = 7, steady: 7 + 1/2 = 7.5  -> quick
        route = routing.find_route(self.world, "A", "B", "balanced", "rush")
        self.assertEqual(self.road_names(route), ["quick"])
        self.assertAlmostEqual(route["cost"], 7.0)

    def test_distance_mode_uses_kilometres(self):
        route = routing.find_route(self.world, "A", "C", "distance", "rush")
        self.assertEqual(route["junctions"], ["A", "B", "C"])
        self.assertAlmostEqual(route["cost"], 2.0)
        self.assertAlmostEqual(route["km"], 2.0)

    def test_a_route_joins_several_roads(self):
        route = routing.find_route(self.world, "A", "C", "average", "rush")
        self.assertEqual(route["junctions"], ["A", "B", "C"])
        self.assertEqual(self.road_names(route), ["quick", "bc"])
        self.assertEqual(route["average"], 7)
        self.assertEqual(route["worst"], 13)

    def test_the_time_of_day_changes_the_cost(self):
        self.world["roads"]["A|B|quick"]["times"]["night"] = (1, 0)
        night = routing.find_route(self.world, "A", "B", "average", "night")
        rush = routing.find_route(self.world, "A", "B", "average", "rush")
        self.assertEqual(night["average"], 1)
        self.assertEqual(rush["average"], 4)

    def test_the_same_junction_is_an_empty_route(self):
        route = routing.find_route(self.world, "A", "A", "average", "rush")
        self.assertEqual(route["junctions"], ["A"])
        self.assertEqual(route["roads"], [])
        self.assertEqual(route["cost"], 0)
        self.assertEqual(routing.describe_route(route), "(already there)")

    def test_tie_goes_to_the_faster_usual_time(self):
        self.world["roads"]["A|B|steady"]["times"]["rush"] = (6, 4)    # worst case 10, like quick
        route = routing.find_route(self.world, "A", "B", "worst_case", "rush")
        self.assertEqual(self.road_names(route), ["quick"])             # usual 4 beats usual 6

    def test_describe_route(self):
        route = routing.find_route(self.world, "A", "C", "average", "rush")
        self.assertEqual(routing.describe_route(route), "A -[quick]-> B -[bc]-> C")
        self.assertEqual(routing.describe_route(None), "(no open route)")


class ClosedRoadTests(unittest.TestCase):

    def setUp(self):
        self.world = make_world()

    def test_closing_one_parallel_road_uses_the_other(self):
        self.world["blocked"].add("A|B|quick")
        route = routing.find_route(self.world, "A", "B", "average", "rush")
        self.assertEqual([r["name"] for r in route["roads"]], ["steady"])

    def test_closing_both_parallel_roads_goes_round(self):
        self.world["blocked"].update({"A|B|quick", "A|B|steady"})
        route = routing.find_route(self.world, "A", "B", "average", "rush")
        self.assertEqual(route["junctions"], ["A", "D", "C", "B"])

    def test_reopening_a_road_changes_the_route_back(self):
        self.world["blocked"].add("A|B|quick")
        routing.find_route(self.world, "A", "B", "average", "rush")     # builds and caches the graph
        self.world["blocked"].clear()
        route = routing.find_route(self.world, "A", "B", "average", "rush")
        self.assertEqual([r["name"] for r in route["roads"]], ["quick"])

    def test_no_route_when_everything_is_closed(self):
        self.world["blocked"].update(self.world["roads"].keys())
        self.assertIsNone(routing.find_route(self.world, "A", "C", "average", "rush"))

    def test_a_cut_off_junction_has_no_route(self):
        for road_id in ["A|B|quick", "A|B|steady", "B|C|bc"]:
            self.world["blocked"].add(road_id)
        self.world["blocked"].add("D|C|dc")
        self.assertIsNone(routing.find_route(self.world, "A", "C", "average", "rush"))

    def test_route_road_ids(self):
        route = routing.find_route(self.world, "A", "C", "average", "rush")
        self.assertEqual(routing.route_road_ids(route), {"A|B|quick", "B|C|bc"})
        self.assertEqual(routing.route_road_ids(None), set())


class AgainstAnIndependentAlgorithm(unittest.TestCase):
    """Dijkstar's answers must equal an independent all-pairs calculation."""

    def check(self, world, modes, periods):
        names = sorted(world["junctions"])
        for mode in modes:
            for period in periods:
                expected = all_pairs(world, mode, period)
                for a in names:
                    for b in names:
                        route = routing.find_route(world, a, b, mode, period)
                        self.assertIsNotNone(route, (a, b))
                        self.assertAlmostEqual(route["cost"], expected[(a, b)], places=6,
                                               msg=(mode, period, a, b))

    def test_small_world_all_modes(self):
        self.check(make_world(), routing.MODES, ["night", "day", "rush"])

    def test_small_world_with_a_closed_road(self):
        world = make_world()
        world["blocked"].add("B|C|bc")
        self.check(world, ["average", "worst_case"], ["rush"])

    def test_real_jayanagar_map_rush_hour(self):
        self.check(real_world(), ["average", "worst_case"], ["rush"])

    def test_real_jayanagar_map_with_closed_roads(self):
        world = real_world()
        # close the first road of five different links; every junction must still be reachable
        for key in sorted(world["between"])[:5]:
            world["blocked"].add(world["between"][key][0]["id"])
        names = sorted(world["junctions"])
        expected = all_pairs(world, "average", "day")
        for a in names[:8]:
            for b in names:
                route = routing.find_route(world, a, b, "average", "day")
                if expected[(a, b)] >= 1e17:
                    self.assertIsNone(route)
                else:
                    self.assertAlmostEqual(route["cost"], expected[(a, b)], places=6)


if __name__ == "__main__":
    unittest.main()
