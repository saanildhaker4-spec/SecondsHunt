import json
import unittest

from ambulance import dispatch, mapdata, routing, triage
from tests.helpers import real_world


class RealMapTests(unittest.TestCase):
    """Checks on the shipped Jayanagar data files."""

    @classmethod
    def setUpClass(cls):
        cls.world = real_world()

    def test_the_map_has_junctions_and_roads(self):
        world = self.world
        self.assertGreaterEqual(len(world["junctions"]), 25)
        self.assertGreaterEqual(len(world["roads"]), len(world["junctions"]))
        self.assertIn("Jayanagar", world["area"])

    def test_every_road_joins_two_known_junctions(self):
        for road in self.world["roads"].values():
            self.assertIn(road["a"], self.world["junctions"])
            self.assertIn(road["b"], self.world["junctions"])
            self.assertNotEqual(road["a"], road["b"])
            self.assertTrue(road["a"] < road["b"], "roads are stored with a < b")

    def test_road_ids_are_unique_and_match_their_content(self):
        ids = list(self.world["roads"])
        self.assertEqual(len(ids), len(set(ids)))
        for road_id, road in self.world["roads"].items():
            self.assertEqual(road_id, road["a"] + "|" + road["b"] + "|" + road["name"])

    def test_travel_times_make_sense(self):
        for road in self.world["roads"].values():
            self.assertGreater(road["km"], 0)
            for period in mapdata.PERIODS:
                average, extra = road["times"][period]
                self.assertGreater(average, 0)
                self.assertGreaterEqual(extra, 0)
            # rush hour is never faster than the night
            self.assertGreaterEqual(road["times"]["rush"][0], road["times"]["night"][0])

    def test_road_shapes_stay_inside_the_area(self):
        south, west, north, east = self.world["bbox"]
        margin = 0.003
        for road in self.world["roads"].values():
            self.assertGreaterEqual(len(road["shape"]), 2)
            for lat, lng in road["shape"]:
                self.assertTrue(south - margin <= lat <= north + margin, road["id"])
                self.assertTrue(west - margin <= lng <= east + margin, road["id"])

    def test_every_junction_can_reach_every_other_junction(self):
        names = sorted(self.world["junctions"])
        for a in names:
            for b in names:
                self.assertIsNotNone(routing.find_route(self.world, a, b, "average", "day"), (a, b))

    def test_there_are_parallel_roads_with_different_names(self):
        pairs = [roads for roads in self.world["between"].values() if len(roads) >= 2]
        self.assertGreaterEqual(len(pairs), 8)
        for roads in pairs:
            names = [road["name"] for road in roads]
            self.assertEqual(len(names), len(set(names)), names)

    def test_the_hospitals_are_real_and_placed_on_the_map(self):
        self.assertGreaterEqual(len(self.world["hospitals"]), 8)
        for name, hospital in self.world["hospitals"].items():
            self.assertIn(hospital["junction"], self.world["junctions"], name)
            self.assertLessEqual(hospital["access_m"], 900, name)
            self.assertTrue(hospital["osm"].split("/")[0] in ("node", "way", "relation"), name)
            self.assertIn("general", hospital["facilities"], name)
            self.assertGreaterEqual(hospital["beds_free"], 0)

    def test_the_survey_is_marked_as_sample_data(self):
        self.assertTrue(self.world["sample_survey"])
        self.assertIn("SAMPLE", self.world["survey_note"])

    def test_ambulances_start_at_real_junctions(self):
        self.assertGreaterEqual(len(self.world["ambulances"]), 4)
        for name, ambulance in self.world["ambulances"].items():
            self.assertIn(ambulance["base"], self.world["junctions"], name)
            self.assertFalse(ambulance["busy"])

    def test_every_kind_of_emergency_has_a_hospital_that_can_treat_it(self):
        for care in triage.FACILITIES_FOR:
            capable = [name for name in self.world["hospitals"]
                       if dispatch.missing_for(self.world, name, care, 1) == []]
            self.assertGreater(len(capable), 0, care)

    def test_the_data_credits_openstreetmap(self):
        self.assertIn("OpenStreetMap", self.world["attribution"])
        self.assertIn("ODbL", self.world["attribution"])

    def test_every_emergency_type_can_be_dispatched_from_every_junction(self):
        world = real_world()
        for place in sorted(world["junctions"]):
            for care, priority in [("cardiac", 1), ("stroke", 1), ("accident", 1), ("minor", 3)]:
                result = {"care": care, "priority": priority, "why": ["test"]}
                plan, reasons = dispatch.plan_dispatch(world, place, result, 9 * 60)
                self.assertIsNotNone(plan, (place, care))
                self.assertIsNotNone(plan["hospital"], (place, care))


class WorldStateTests(unittest.TestCase):

    def test_reset_world_restores_everything(self):
        world = real_world()
        first_road = next(iter(world["roads"]))
        world["blocked"].add(first_road)
        name = sorted(world["ambulances"])[0]
        world["ambulances"][name].update({"busy": True, "at": "elsewhere", "job": {"x": 1}})
        hospital = sorted(world["hospitals"])[0]
        survey_beds = world["hospitals"][hospital]["beds_survey"]
        world["hospitals"][hospital]["beds_free"] = 99
        world["log"].append({"id": "INC-001"})
        mapdata.reset_world(world)
        self.assertEqual(world["blocked"], set())
        self.assertFalse(world["ambulances"][name]["busy"])
        self.assertEqual(world["ambulances"][name]["at"], world["ambulances"][name]["base"])
        self.assertEqual(world["hospitals"][hospital]["beds_free"], survey_beds)
        self.assertEqual(world["log"], [])

    def test_loading_twice_gives_independent_worlds(self):
        first, second = real_world(), real_world()
        first["blocked"].add("x")
        first["hospitals"][sorted(first["hospitals"])[0]]["beds_free"] = 99
        self.assertEqual(second["blocked"], set())
        self.assertNotEqual(second["hospitals"][sorted(second["hospitals"])[0]]["beds_free"], 99)

    def test_a_hospital_missing_from_the_survey_gets_safe_defaults(self):
        import os
        import tempfile
        with open(mapdata.SURVEY_FILE, encoding="utf-8") as file:
            survey = json.load(file)
        survey["hospitals"] = {}
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "survey.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(survey, file)
        world = mapdata.load_world(survey_file=path)
        for hospital in world["hospitals"].values():
            self.assertEqual(hospital["beds_free"], 0)
            self.assertEqual(hospital["facilities"], {"general"})

    def test_a_bad_ambulance_base_is_rejected(self):
        import os
        import tempfile
        with open(mapdata.SURVEY_FILE, encoding="utf-8") as file:
            survey = json.load(file)
        survey["ambulances"][0]["base"] = "Nowhere"
        path = os.path.join(tempfile.mkdtemp(), "survey.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(survey, file)
        with self.assertRaises(ValueError):
            mapdata.load_world(survey_file=path)


class PriorityEffectOnTheRealMap(unittest.TestCase):
    """Priority 1 prices roads by their worst case. On the real map that
    sometimes picks a different road, and it must never be slower in the
    worst case."""

    def test_the_reliable_route_is_never_worse_in_the_worst_case(self):
        world = real_world()
        names = sorted(world["junctions"])
        different = 0
        for a in names:
            for b in names:
                if a >= b:
                    continue
                average_route = routing.find_route(world, a, b, "average", "rush")
                reliable = routing.find_route(world, a, b, "worst_case", "rush")
                self.assertLessEqual(reliable["worst"], average_route["worst"] + 1e-6, (a, b))
                if [r["id"] for r in reliable["roads"]] != [r["id"] for r in average_route["roads"]]:
                    different += 1
        self.assertGreater(different, 0)


if __name__ == "__main__":
    unittest.main()
