"""The demo cases in README.md, checked with the real map. If the map data
or the rules change, these tests fail and the README must be updated."""

import unittest

from ambulance import dispatch, routing, triage
from tests.helpers import answers, real_world


def run(world, place, hour, **changes):
    result = triage.triage(answers(**changes))
    plan, reasons = dispatch.plan_dispatch(world, place, result, hour * 60)
    baseline = dispatch.nearest_baseline(world, place, result["care"], result["priority"], plan["period"])
    return plan, baseline, reasons


def road_names(route):
    return [road["name"] for road in route["roads"]]


class DemoCases(unittest.TestCase):

    def test_case_1_heart_attack_nearest_is_not_best(self):
        world = real_world()
        plan, baseline, reasons = run(world, "Kanakapura Rd & 13th Cross Rd", 9,
                                      conscious=False, chest_pain=True)
        self.assertEqual(plan["ambulance"], "Ambulance 5")
        self.assertEqual((plan["route1"]["average"], plan["route1"]["worst"]), (8.8, 10.3))
        self.assertEqual(plan["hospital"], "Jayanagar heart Centre")
        self.assertEqual(baseline["ambulance"], "Ambulance 1")
        self.assertEqual((baseline["average"], baseline["worst"]), (7.8, 13.4))
        self.assertEqual(baseline["hospital"], "AMC Multispeciality Hospital")
        self.assertEqual(baseline["missing"], ["no cath lab", "no ICU"])

    def test_case_1_when_the_caller_is_not_in_danger_the_quick_ambulance_goes(self):
        world = real_world()
        plan, baseline, reasons = run(world, "Kanakapura Rd & 13th Cross Rd", 9)
        self.assertEqual(plan["ambulance"], "Ambulance 1")
        self.assertEqual((plan["route1"]["average"], plan["route1"]["worst"]), (7.8, 13.4))
        self.assertEqual(plan["priority"], 3)

    def test_case_2_a_stroke_goes_to_a_hospital_with_a_stroke_unit(self):
        world = real_world()
        plan, baseline, reasons = run(world, "Bannerghatta Rd & Swagath Rd", 9, stroke_signs=True)
        self.assertEqual(plan["hospital"], "NIMHANS Emergency Block")
        self.assertEqual(baseline["hospital"], "Sagar Hospitals")
        self.assertEqual(baseline["missing"], ["no stroke unit"])
        self.assertIn("Sagar Hospitals : rejected (no stroke unit)", "\n".join(reasons))

    def test_case_3_a_full_hospital_is_skipped(self):
        world = real_world()
        plan, baseline, reasons = run(world, "Bannerghatta Rd & New MICO Link Rd", 14)
        self.assertEqual(baseline["hospital"], "Sree Venkateshwara Speciality Hospital")
        self.assertEqual(baseline["missing"], ["no free bed"])
        self.assertEqual(plan["hospital"], "NIMHANS Emergency Block")
        self.assertIn("Sree Venkateshwara Speciality Hospital : rejected (no free bed)", "\n".join(reasons))

    def test_case_4_a_closed_road_is_avoided(self):
        world = real_world()
        plan, baseline, reasons = run(world, "Marenahalli Rd & 11th Main Rd", 9, injury=True)
        self.assertEqual(road_names(plan["route1"]), ["Ayodhyarama Rd", "Marenahalli Rd"])
        self.assertEqual((plan["route1"]["average"], plan["route1"]["worst"]), (6.1, 8.4))
        closed = plan["route1"]["roads"][0]["id"]
        world["blocked"].add(closed)
        plan, baseline, reasons = run(world, "Marenahalli Rd & 11th Main Rd", 9, injury=True)
        self.assertEqual(road_names(plan["route1"]), ["9th Cross Rd", "24th Main Rd"])
        self.assertEqual((plan["route1"]["average"], plan["route1"]["worst"]), (6.5, 8.7))
        self.assertNotIn(closed, routing.route_road_ids(plan["route1"]))


if __name__ == "__main__":
    unittest.main()
