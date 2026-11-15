import unittest

from ambulance import dispatch, routing, triage
from tests.helpers import answers, make_world


def run(world, place, clock=9 * 60, **changes):
    result = triage.triage(answers(**changes))
    plan, reasons = dispatch.plan_dispatch(world, place, result, clock)
    return plan, reasons, result


class TimeTests(unittest.TestCase):

    def test_periods(self):
        self.assertEqual(dispatch.get_period(2 * 60), "night")
        self.assertEqual(dispatch.get_period(5 * 60 + 59), "night")
        self.assertEqual(dispatch.get_period(6 * 60), "day")
        self.assertEqual(dispatch.get_period(7 * 60 + 59), "day")
        self.assertEqual(dispatch.get_period(8 * 60), "rush")
        self.assertEqual(dispatch.get_period(10 * 60 + 59), "rush")
        self.assertEqual(dispatch.get_period(11 * 60), "day")
        self.assertEqual(dispatch.get_period(16 * 60 + 59), "day")
        self.assertEqual(dispatch.get_period(17 * 60), "rush")
        self.assertEqual(dispatch.get_period(20 * 60 + 59), "rush")
        self.assertEqual(dispatch.get_period(21 * 60), "day")
        self.assertEqual(dispatch.get_period(23 * 60), "night")

    def test_show_clock(self):
        self.assertEqual(dispatch.show_clock(9 * 60 + 5), "09:05")
        self.assertEqual(dispatch.show_clock(0), "00:00")
        self.assertEqual(dispatch.show_clock(23 * 60 + 59), "23:59")

    def test_now_is_a_valid_time_of_day(self):
        self.assertTrue(0 <= dispatch.now_minutes() < 24 * 60)


class AmbulanceChoiceTests(unittest.TestCase):

    def setUp(self):
        self.world = make_world()

    def test_the_cheapest_free_ambulance_is_sent(self):
        # Ambulance 1 is at A, Ambulance 2 at C. The patient is at B.
        plan, reasons, result = run(self.world, "B", injury=True)      # priority 2: balanced
        self.assertEqual(plan["ambulance"], "Ambulance 2")             # C -> B costs 3
        self.assertEqual(plan["route1"]["average"], 3)

    def test_a_busy_ambulance_is_skipped(self):
        self.world["ambulances"]["Ambulance 2"]["busy"] = True
        plan, reasons, result = run(self.world, "B", injury=True)
        self.assertEqual(plan["ambulance"], "Ambulance 1")
        self.assertTrue(any("Ambulance 2 : busy" in line for line in reasons))

    def test_no_plan_when_every_ambulance_is_busy(self):
        for ambulance in self.world["ambulances"].values():
            ambulance["busy"] = True
        plan, reasons, result = run(self.world, "B")
        self.assertIsNone(plan)

    def test_no_plan_when_the_roads_are_closed(self):
        self.world["blocked"].update(["B|C|bc", "A|B|quick", "A|B|steady"])
        self.world["ambulances"]["Ambulance 2"]["at"] = "C"
        plan, reasons, result = run(self.world, "B")
        self.assertIsNone(plan)

    def test_priority_changes_the_road_used(self):
        critical, _, _ = run(self.world, "B", conscious=False)         # priority 1
        calm, _, _ = run(self.world, "B")                              # priority 3
        self.world["ambulances"]["Ambulance 1"]["busy"] = False
        self.assertEqual(critical["mode"], "worst_case")
        self.assertEqual(calm["mode"], "average")
        # Ambulance 1 comes from A over the parallel roads
        self.world["ambulances"]["Ambulance 2"]["busy"] = True
        critical, _, _ = run(self.world, "B", conscious=False)
        calm, _, _ = run(self.world, "B")
        self.assertEqual([r["name"] for r in critical["route1"]["roads"]], ["steady"])
        self.assertEqual([r["name"] for r in calm["route1"]["roads"]], ["quick"])


class HospitalChoiceTests(unittest.TestCase):

    def setUp(self):
        self.world = make_world()

    def test_a_cardiac_case_goes_to_the_hospital_with_a_cath_lab(self):
        plan, reasons, result = run(self.world, "B", conscious=False)
        self.assertEqual(plan["hospital"], "Far Heart")                # Near General is closer
        text = "\n".join(reasons)
        self.assertIn("Near General : rejected (no cath lab, no ICU)", text)

    def test_a_minor_case_goes_to_the_best_hospital_by_time(self):
        plan, reasons, result = run(self.world, "B")
        self.assertEqual(plan["hospital"], "Near General")

    def test_a_full_hospital_is_skipped(self):
        self.world["hospitals"]["Near General"]["beds_free"] = 0
        plan, reasons, result = run(self.world, "B")
        self.assertEqual(plan["hospital"], "Far Heart")
        self.assertIn("Near General : rejected (no free bed)", "\n".join(reasons))

    def test_all_the_reasons_for_a_rejection_are_listed(self):
        self.world["hospitals"]["Near General"]["beds_free"] = 0
        plan, reasons, result = run(self.world, "B", stroke_signs=True)
        self.assertIn("Near General : rejected (no stroke unit, no CT scan, no free bed)", "\n".join(reasons))

    def test_no_hospital_can_treat(self):
        for hospital in self.world["hospitals"].values():
            hospital["beds_free"] = 0
        plan, reasons, result = run(self.world, "B")
        self.assertIsNotNone(plan)                                     # the ambulance still goes
        self.assertIsNone(plan["hospital"])
        self.assertIsNone(plan["route2"])
        self.assertIn("NO hospital can treat", "\n".join(reasons))

    def test_blood_bank_is_needed_for_a_priority_1_accident_only(self):
        self.world["hospitals"]["Near General"]["facilities"] = {"general", "trauma_unit"}
        plan, reasons, result = run(self.world, "B", injury=True)                       # priority 2
        self.assertEqual(plan["hospital"], "Near General")
        plan, reasons, result = run(self.world, "B", injury=True, bleeding=True)        # priority 1
        self.assertNotEqual(plan["hospital"], "Near General")

    def test_the_door_time_and_waiting_time_count(self):
        self.world["hospitals"]["Near General"]["wait"] = 60
        plan, reasons, result = run(self.world, "B")
        self.assertEqual(plan["hospital"], "Far Heart")

    def test_missing_for_lists_what_is_missing(self):
        missing = dispatch.missing_for(self.world, "Near General", "cardiac", 1)
        self.assertEqual(missing, ["no cath lab", "no ICU"])
        self.assertEqual(dispatch.missing_for(self.world, "Far Heart", "cardiac", 1), [])

    def test_access_minutes(self):
        hospital = self.world["hospitals"]["Near General"]
        hospital["access_m"] = 500
        self.assertEqual(dispatch.access_minutes(hospital), 1.5)       # 0.5 km at 20 km/h


class CommitTests(unittest.TestCase):

    def setUp(self):
        self.world = make_world()

    def test_committing_a_dispatch(self):
        plan, reasons, result = run(self.world, "B")
        entry = dispatch.commit_dispatch(self.world, plan)
        ambulance = self.world["ambulances"][plan["ambulance"]]
        self.assertTrue(ambulance["busy"])
        self.assertEqual(self.world["hospitals"][plan["hospital"]]["beds_free"], 2)
        self.assertEqual(entry["id"], "INC-001")
        self.assertEqual(len(self.world["log"]), 1)
        self.assertEqual(entry["place"], "B")

    def test_the_second_call_gets_the_next_number_and_ambulance(self):
        first, _, _ = run(self.world, "B")
        dispatch.commit_dispatch(self.world, first)
        second, _, _ = run(self.world, "B")
        entry = dispatch.commit_dispatch(self.world, second)
        self.assertEqual(entry["id"], "INC-002")
        self.assertNotEqual(first["ambulance"], second["ambulance"])

    def test_beds_never_go_below_zero(self):
        self.world["hospitals"]["Near General"]["beds_free"] = 1
        plan, _, _ = run(self.world, "B")
        dispatch.commit_dispatch(self.world, plan)
        self.assertEqual(self.world["hospitals"]["Near General"]["beds_free"], 0)

    def test_finishing_a_job_frees_the_ambulance_at_the_hospital(self):
        plan, _, _ = run(self.world, "B", conscious=False)
        dispatch.commit_dispatch(self.world, plan)
        name = plan["ambulance"]
        dispatch.finish_job(self.world, name)
        ambulance = self.world["ambulances"][name]
        self.assertFalse(ambulance["busy"])
        self.assertEqual(ambulance["at"], "C")                         # Far Heart is at junction C
        self.assertIsNone(ambulance["job"])

    def test_finishing_a_job_with_no_hospital_leaves_it_at_the_patient(self):
        for hospital in self.world["hospitals"].values():
            hospital["beds_free"] = 0
        plan, _, _ = run(self.world, "B")
        dispatch.commit_dispatch(self.world, plan)
        dispatch.finish_job(self.world, plan["ambulance"])
        self.assertEqual(self.world["ambulances"][plan["ambulance"]]["at"], "B")


class BaselineTests(unittest.TestCase):

    def setUp(self):
        self.world = make_world()

    def test_nearest_rule_ignores_facilities(self):
        baseline = dispatch.nearest_baseline(self.world, "B", "cardiac", 1, "rush")
        self.assertEqual(baseline["hospital"], "Near General")
        self.assertEqual(baseline["missing"], ["no cath lab", "no ICU"])

    def test_nearest_rule_picks_the_ambulance_with_the_fewest_km(self):
        self.world["ambulances"]["Ambulance 1"]["at"] = "D"            # 3.0 km from B
        baseline = dispatch.nearest_baseline(self.world, "B", "minor", 3, "rush")
        self.assertEqual(baseline["ambulance"], "Ambulance 2")         # at C, 1.0 km from B
        self.assertEqual(baseline["average"], 3)
        self.assertEqual(baseline["worst"], 3)

    def test_a_tie_in_kilometres_goes_to_the_first_name(self):
        baseline = dispatch.nearest_baseline(self.world, "B", "minor", 3, "rush")
        self.assertEqual(baseline["ambulance"], "Ambulance 1")         # both are 1.0 km away

    def test_nearest_rule_skips_busy_ambulances(self):
        self.world["ambulances"]["Ambulance 2"]["busy"] = True
        baseline = dispatch.nearest_baseline(self.world, "B", "minor", 3, "rush")
        self.assertEqual(baseline["ambulance"], "Ambulance 1")


if __name__ == "__main__":
    unittest.main()
