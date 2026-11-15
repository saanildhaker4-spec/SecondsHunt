import itertools
import unittest

from ambulance import triage
from tests.helpers import answers


class TriageTests(unittest.TestCase):

    def test_a_healthy_person_is_priority_3_minor(self):
        result = triage.triage(triage.usual_answers())
        self.assertEqual(result["care"], "minor")
        self.assertEqual(result["priority"], 3)

    def test_unconscious_is_priority_1_cardiac(self):
        result = triage.triage(answers(conscious=False))
        self.assertEqual((result["care"], result["priority"]), ("cardiac", 1))
        self.assertIn("not conscious", result["why"])

    def test_not_breathing_is_priority_1_cardiac(self):
        result = triage.triage(answers(breathing=False))
        self.assertEqual((result["care"], result["priority"]), ("cardiac", 1))

    def test_chest_pain_is_priority_1_cardiac(self):
        result = triage.triage(answers(chest_pain=True))
        self.assertEqual((result["care"], result["priority"]), ("cardiac", 1))

    def test_stroke_signs_are_priority_1_stroke(self):
        result = triage.triage(answers(stroke_signs=True))
        self.assertEqual((result["care"], result["priority"]), ("stroke", 1))

    def test_heavy_bleeding_is_priority_1_accident(self):
        result = triage.triage(answers(bleeding=True))
        self.assertEqual((result["care"], result["priority"]), ("accident", 1))

    def test_an_injury_alone_is_priority_2_accident(self):
        result = triage.triage(answers(injury=True))
        self.assertEqual((result["care"], result["priority"]), ("accident", 2))

    def test_injury_with_a_danger_sign_is_priority_1(self):
        result = triage.triage(answers(injury=True, conscious=False))
        self.assertEqual((result["care"], result["priority"]), ("accident", 1))

    def test_injury_wins_the_care_type_over_stroke_signs(self):
        result = triage.triage(answers(injury=True, stroke_signs=True))
        self.assertEqual(result["care"], "accident")
        self.assertEqual(result["priority"], 1)

    def test_all_64_combinations_follow_the_rules(self):
        keys = [key for key, text, usual in triage.QUESTIONS]
        self.assertEqual(len(keys), 6)
        for values in itertools.product([True, False], repeat=6):
            given = dict(zip(keys, values))
            result = triage.triage(given)
            danger = (not given["conscious"] or not given["breathing"] or given["chest_pain"]
                      or given["stroke_signs"] or given["bleeding"])
            if danger:
                expected_priority = 1
            elif given["injury"]:
                expected_priority = 2
            else:
                expected_priority = 3
            self.assertEqual(result["priority"], expected_priority, given)
            self.assertIn(result["care"], triage.FACILITIES_FOR, given)
            self.assertGreater(len(result["why"]), 0, given)
            self.assertIn(result["priority"], triage.MODE_FOR_PRIORITY)

    def test_every_priority_has_a_name_and_a_routing_mode(self):
        for priority in [1, 2, 3]:
            self.assertIn(priority, triage.PRIORITY_NAMES)
        self.assertEqual(triage.MODE_FOR_PRIORITY, {1: "worst_case", 2: "balanced", 3: "average"})

    def test_required_facilities(self):
        self.assertEqual(triage.required_facilities("cardiac", 1), ["cath_lab", "icu"])
        self.assertEqual(triage.required_facilities("stroke", 1), ["stroke_unit", "ct_scan"])
        self.assertEqual(triage.required_facilities("minor", 3), ["general"])
        self.assertIn("blood_bank", triage.required_facilities("accident", 1))
        self.assertNotIn("blood_bank", triage.required_facilities("accident", 2))

    def test_required_facilities_does_not_change_the_table(self):
        triage.required_facilities("accident", 1)
        self.assertEqual(triage.FACILITIES_FOR["accident"], ["trauma_unit"])


if __name__ == "__main__":
    unittest.main()
