import csv
import os
import tempfile
import tkinter as tk
import unittest
from unittest import mock

from ambulance import dispatch, gui, mapdata, voice
from tests.helpers import real_world


def can_open_a_window():
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


@unittest.skipUnless(can_open_a_window(), "no display available for the window tests")
class WindowTests(unittest.TestCase):

    def setUp(self):
        self.world = real_world()
        self.app = gui.build_window(self.world)
        self.root = self.app["root"]
        self.root.update()
        # never show a real dialog during a test
        patches = [mock.patch.object(gui.messagebox, "showinfo"),
                   mock.patch.object(gui.messagebox, "askyesno", return_value=True)]
        self.showinfo = patches[0].start()
        patches[1].start()
        self.addCleanup(lambda: [p.stop() for p in patches])

    def tearDown(self):
        if not self.app.get("closed"):
            self.root.destroy()

    def click(self, x, y):
        self.app["canvas"].event_generate("<Button-1>", x=x, y=y)
        self.root.update()

    def place(self, index=10):
        name = sorted(self.world["junctions"])[index]
        x, y = gui.positions[name]
        self.click(x, y)
        return name

    def tick_answers(self, **changes):
        for key, value in changes.items():
            self.app["answers"][key].set(int(value))
        gui.on_answer_change()

    def set_hour(self, hour):
        self.app["use_now"].set(0)
        gui.on_time_change()                 # (this is what ticking the box does: it enables the slider)
        self.app["hour"].set(hour)
        gui.on_time_change()

    # ---- the map
    def test_the_window_opens_with_a_full_map(self):
        canvas = self.app["canvas"]
        self.assertEqual(len(gui.positions), len(self.world["junctions"]))
        kinds = [value[0] for value in gui.clickable.values()]
        for kind in ["place", "road", "hospital", "ambulance"]:
            self.assertIn(kind, kinds)
        self.assertEqual(self.app["place_label"].cget("text"),
                         "Emergency at: (click a junction on the map)")
        self.assertGreater(len(canvas.find_all()), 200)

    def test_no_label_runs_off_the_map(self):
        canvas = self.app["canvas"]
        for item in canvas.find_all():
            if canvas.type(item) == "text":
                x1, y1, x2, y2 = canvas.bbox(item)
                self.assertGreaterEqual(x1, 0)
                self.assertGreaterEqual(y1, 0)
                self.assertLessEqual(x2, gui.CANVAS_WIDTH)
                self.assertLessEqual(y2, gui.CANVAS_HEIGHT)

    def test_clicking_a_junction_sets_the_emergency_location(self):
        name = self.place()
        self.assertEqual(self.app["place"], name)
        self.assertIn(name, self.app["place_label"].cget("text"))

    def free_road_point(self):
        """A point on a road where nothing else (junction, label, marker) is drawn."""
        canvas = self.app["canvas"]
        for item, value in gui.clickable.items():
            if value[0] != "road":
                continue
            coords = canvas.coords(item)
            for i in range(0, len(coords) - 2, 2):
                x = round((coords[i] + coords[i + 2]) / 2)
                y = round((coords[i + 1] + coords[i + 3]) / 2)
                near = canvas.find_overlapping(x - 6, y - 6, x + 6, y + 6)     # wider than a real click
                kinds = set(gui.clickable.get(n, ("other",))[0] for n in near)
                ids = set(gui.clickable[n][1] for n in near if n in gui.clickable)
                if kinds == {"road"} and len(ids) == 1:
                    return x, y, value[1]
        self.fail("no free point on any road")

    def test_clicking_a_road_closes_and_reopens_it(self):
        x, y, road_id = self.free_road_point()
        self.click(x, y)
        self.assertIn(road_id, self.world["blocked"])
        x, y, again = self.free_road_point()                 # the map was redrawn
        if again == road_id:
            self.click(x, y)
            self.assertNotIn(road_id, self.world["blocked"])
        else:
            self.world["blocked"].discard(road_id)

    # ---- time
    def test_the_hour_slider_is_used_when_not_following_real_time(self):
        self.set_hour(18)
        self.assertEqual(gui.current_clock(), 18 * 60)
        self.assertIn("rush", self.app["clock_label"].cget("text"))
        self.assertEqual(str(self.app["hour"].cget("state")), "normal")

    def test_real_time_is_used_by_default(self):
        self.assertEqual(self.app["use_now"].get(), 1)
        self.assertEqual(str(self.app["hour"].cget("state")), "disabled")
        self.assertAlmostEqual(gui.current_clock(), dispatch.now_minutes(), delta=2)

    # ---- triage display
    def test_the_priority_follows_the_ticked_answers(self):
        self.assertIn("PRIORITY 3", self.app["priority_label"].cget("text"))
        self.tick_answers(conscious=False, chest_pain=True)
        text = self.app["priority_label"].cget("text")
        self.assertIn("PRIORITY 1", text)
        self.assertIn("cath lab", text)
        self.tick_answers(conscious=True, chest_pain=False, injury=True)
        self.assertIn("PRIORITY 2", self.app["priority_label"].cget("text"))

    # ---- dispatch
    def test_dispatch_needs_a_location(self):
        self.assertFalse(gui.on_dispatch())
        self.showinfo.assert_called()

    def test_a_full_dispatch(self):
        self.set_hour(9)
        name = self.place()
        self.tick_answers(conscious=False, chest_pain=True)
        self.assertTrue(gui.on_dispatch())
        plan = self.app["plan"]
        self.assertEqual(plan["place"], name)
        self.assertEqual(plan["priority"], 1)
        self.assertIsNotNone(plan["hospital"])
        self.assertEqual(len(self.world["log"]), 1)
        text = self.app["result"].get("1.0", "end")
        for part in ["DISPATCH ORDER INC-001", "SEND", plan["ambulance"], "TAKE TO", plan["hospital"],
                     "COMPARE", "WHY:", "PRIORITY 1"]:
            self.assertIn(part, text)
        self.assertTrue(self.world["ambulances"][plan["ambulance"]]["busy"])
        self.assertEqual(len(self.app["log_table"].get_children()), 1)

    def test_the_route_is_coloured_on_the_map(self):
        self.set_hour(9)
        self.place(10)
        self.tick_answers(conscious=False, chest_pain=True)
        gui.on_dispatch()
        colours = set()
        canvas = self.app["canvas"]
        for item in canvas.find_all():
            if canvas.type(item) == "line":
                colours.add(canvas.itemcget(item, "fill"))
        self.assertIn(gui.GREEN, colours)                # the way to the hospital (the ambulance may already be there)

    def test_dispatching_until_no_ambulance_is_left(self):
        self.set_hour(9)
        for number in range(len(self.world["ambulances"])):
            self.place(3 + number)
            self.assertTrue(gui.on_dispatch())
        self.place(20)
        self.assertFalse(gui.on_dispatch())
        self.assertIn("NO AMBULANCE", self.app["result"].get("1.0", "end"))

    def test_clicking_a_busy_ambulance_frees_it(self):
        self.set_hour(9)
        self.place()
        gui.on_dispatch()
        name = self.app["plan"]["ambulance"]
        item = next(i for i, v in gui.clickable.items() if v == ("ambulance", name))
        x1, y1, x2, y2 = self.app["canvas"].bbox(item)
        self.click((x1 + x2) / 2, (y1 + y2) / 2)
        self.assertFalse(self.world["ambulances"][name]["busy"])

    # ---- fleet tab
    def test_the_fleet_tables_list_everything(self):
        self.assertEqual(len(self.app["ambulance_table"].get_children()), len(self.world["ambulances"]))
        self.assertEqual(len(self.app["hospital_table"].get_children()), len(self.world["hospitals"]))

    def test_the_bed_buttons_change_the_free_beds(self):
        name = sorted(self.world["hospitals"])[0]
        before = self.world["hospitals"][name]["beds_free"]
        self.app["hospital_table"].selection_set(name)
        gui.on_change_beds(1)
        self.assertEqual(self.world["hospitals"][name]["beds_free"], before + 1)
        self.app["hospital_table"].selection_set(name)
        gui.on_change_beds(-1)
        gui.on_change_beds(-1)
        self.world["hospitals"][name]["beds_free"] = 0
        self.app["hospital_table"].selection_set(name)
        gui.on_change_beds(-1)
        self.assertEqual(self.world["hospitals"][name]["beds_free"], 0)

    def test_back_in_service_button(self):
        self.set_hour(9)
        self.place()
        gui.on_dispatch()
        name = self.app["plan"]["ambulance"]
        self.app["ambulance_table"].selection_set(name)
        gui.on_free_ambulance()
        self.assertFalse(self.world["ambulances"][name]["busy"])

    def test_reset_everything(self):
        self.set_hour(9)
        self.place()
        gui.on_dispatch()
        self.world["blocked"].add(next(iter(self.world["roads"])))
        gui.on_reset_all()
        self.assertEqual(self.world["log"], [])
        self.assertEqual(self.world["blocked"], set())
        self.assertIsNone(self.app["plan"])
        self.assertTrue(all(not a["busy"] for a in self.world["ambulances"].values()))

    # ---- log
    def test_the_call_log_is_saved_as_csv(self):
        self.set_hour(9)
        self.place()
        gui.on_dispatch()
        path = os.path.join(tempfile.mkdtemp(), "log.csv")
        with mock.patch.object(gui.filedialog, "asksaveasfilename", return_value=path):
            gui.on_save_log()
        with open(path, newline="", encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "INC-001")
        self.assertEqual(rows[0]["ambulance"], self.app["plan"]["ambulance"])

    # ---- voice call
    def scripted_voice(self, answers):
        spoken = []
        patches = [mock.patch.object(voice, "available", return_value=True),
                   mock.patch.object(voice, "speak", side_effect=lambda text, keep: spoken.append(text)),
                   mock.patch.object(voice, "ask_yes_no", side_effect=lambda q, keep: answers.pop(0))]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return spoken

    def test_a_voice_call_asks_the_questions_dispatches_and_says_the_result(self):
        self.set_hour(9)
        name = self.place()
        spoken = self.scripted_voice([False, True, True, False, False, False])   # unconscious, chest pain
        gui.on_voice_call()
        self.assertEqual(self.app["answers"]["conscious"].get(), 0)
        self.assertEqual(self.app["answers"]["chest_pain"].get(), 1)
        self.assertEqual(len(self.world["log"]), 1)
        self.assertEqual(self.app["plan"]["priority"], 1)
        self.assertTrue(any(text.startswith("Ambulance") and "on the way to" in text for text in spoken))
        self.assertFalse(self.app["in_call"])
        self.assertTrue(self.app["voice_button"].cget("text").startswith("VOICE CALL"))

    def test_a_voice_call_that_misses_an_answer_does_not_dispatch(self):
        self.set_hour(9)
        self.place()
        self.scripted_voice([True, None, False, False, False, False])
        gui.on_voice_call()
        self.assertEqual(self.world["log"], [])
        self.assertIn("could not understand", self.app["status"].cget("text"))

    def test_a_voice_call_needs_a_location(self):
        self.scripted_voice([])
        gui.on_voice_call()
        self.assertEqual(self.world["log"], [])
        self.showinfo.assert_called()

    def test_stopping_a_voice_call(self):
        self.set_hour(9)
        self.place()
        spoken = self.scripted_voice([True, True, True, True, True, True])

        def stop_after_two_questions(question, keep):
            if len(spoken) >= 0 and self.app["answers"]["breathing"].get() is not None:
                self.app["stop"] = True
            return True
        with mock.patch.object(voice, "ask_yes_no", side_effect=stop_after_two_questions):
            gui.on_voice_call()
        self.assertEqual(self.world["log"], [])
        self.assertFalse(self.app["in_call"])
        self.assertFalse(self.app["stop"])

    def test_closing_the_window_during_a_voice_call(self):
        self.set_hour(9)
        self.place()
        self.scripted_voice([True, True, True, True, True, True])

        def close_window(question, keep):
            gui.on_close()
            return True
        with mock.patch.object(voice, "ask_yes_no", side_effect=close_window):
            gui.on_voice_call()                          # must not raise
        self.assertTrue(self.app["closed"])



@unittest.skipUnless(can_open_a_window(), "no display available for the window tests")
class RealSurveyTests(unittest.TestCase):
    """When data/survey.json is marked as real, the window stops saying SAMPLE."""

    def test_no_sample_warning_for_a_real_survey(self):
        world = real_world()
        world["sample_survey"] = False
        app = gui.build_window(world)
        try:
            app["root"].update()
            canvas = app["canvas"]
            texts = [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]
            self.assertFalse(any("SAMPLE" in text for text in texts))
            self.assertTrue(any("survey.json" in text for text in texts))
        finally:
            app["root"].destroy()

    def test_the_sample_warning_is_shown_for_the_sample_survey(self):
        app = gui.build_window(real_world())
        try:
            app["root"].update()
            canvas = app["canvas"]
            texts = [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]
            self.assertTrue(any("SAMPLE" in text for text in texts))
        finally:
            app["root"].destroy()



@unittest.skipUnless(can_open_a_window(), "no display available for the window tests")
class DuringAVoiceCallTests(unittest.TestCase):
    """While a voice call is running the rest of the window must not interfere."""

    def setUp(self):
        self.world = real_world()
        self.app = gui.build_window(self.world)
        self.root = self.app["root"]
        self.root.update()
        patch = mock.patch.object(gui.messagebox, "askyesno", return_value=True)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.root.destroy)

    def test_dispatch_is_refused_during_a_call(self):
        self.app["place"] = sorted(self.world["junctions"])[3]
        self.app["in_call"] = True
        self.assertFalse(gui.on_dispatch())
        self.assertEqual(self.world["log"], [])
        self.assertIn("voice call is running", self.app["status"].cget("text"))

    def test_the_location_cannot_change_during_a_call(self):
        names = sorted(self.world["junctions"])
        self.app["place"] = names[3]
        self.app["in_call"] = True
        x, y = gui.positions[names[8]]
        self.app["canvas"].event_generate("<Button-1>", x=round(x), y=round(y))
        self.root.update()
        self.assertEqual(self.app["place"], names[3])

    def test_reset_is_refused_during_a_call(self):
        self.world["blocked"].add(next(iter(self.world["roads"])))
        self.app["in_call"] = True
        gui.on_reset_all()
        self.assertEqual(len(self.world["blocked"]), 1)

    def test_the_comparison_line_does_not_call_a_real_hospital_wrong(self):
        self.app["use_now"].set(0)
        gui.on_time_change()
        self.app["hour"].set(9)
        gui.on_time_change()
        x, y = gui.positions["Kanakapura Rd & 13th Cross Rd"]
        self.app["canvas"].event_generate("<Button-1>", x=round(x), y=round(y))
        self.root.update()
        self.app["answers"]["conscious"].set(0)
        self.app["answers"]["chest_pain"].set(1)
        gui.on_answer_change()
        self.assertTrue(gui.on_dispatch())
        text = self.app["result"].get("1.0", "end")
        self.assertIn("NOT SUITABLE (survey says: no cath lab, no ICU)", text)
        self.assertNotIn("WRONG", text)
        self.assertIn("SAMPLE data", text)


if __name__ == "__main__":
    unittest.main()
