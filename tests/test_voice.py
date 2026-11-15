import os
import subprocess
import tempfile
import unittest
from unittest import mock

from ambulance import voice


class SpokenTextTests(unittest.TestCase):

    def test_road_names_are_made_speakable(self):
        self.assertEqual(voice.spoken("Kanakapura Rd & 13th Cross Rd"),
                         "Kanakapura Road and 13th Cross Road")
        self.assertEqual(voice.spoken("Market St"), "Market Street")

    def test_yes_and_no_phrases_are_clearly_different(self):
        self.assertTrue(voice.YES_NO["yes"])
        self.assertFalse(voice.YES_NO["no"])
        self.assertNotIn("yeah", voice.YES_NO)           # sounded too much like "no"
        for phrase, value in voice.YES_NO.items():
            if phrase.startswith("yes"):
                self.assertTrue(value, phrase)
            if phrase.startswith("no"):
                self.assertFalse(value, phrase)


class AskYesNoTests(unittest.TestCase):

    def test_a_clear_yes(self):
        with mock.patch.object(voice, "run_helper", return_value=("yes", 0.9)):
            self.assertIs(voice.ask_yes_no("Question?", None), True)

    def test_a_clear_no(self):
        with mock.patch.object(voice, "run_helper", return_value=("no", 0.9)):
            self.assertIs(voice.ask_yes_no("Question?", None), False)

    def test_a_low_confidence_answer_is_asked_again(self):
        answers = [("yes", 0.2), ("no", 0.9)]
        with mock.patch.object(voice, "run_helper", side_effect=answers) as helper:
            self.assertIs(voice.ask_yes_no("Question?", None), False)
        self.assertEqual(helper.call_count, 2)
        self.assertTrue(helper.call_args_list[1][0][0].startswith("Sorry"))

    def test_nothing_understood_gives_none_after_two_tries(self):
        with mock.patch.object(voice, "run_helper", return_value=("", 0.0)) as helper:
            self.assertIsNone(voice.ask_yes_no("Question?", None))
        self.assertEqual(helper.call_count, 2)


class StopTests(unittest.TestCase):

    def test_a_stopped_call_never_starts_the_helper(self):
        with mock.patch.object(voice.subprocess, "Popen") as popen:
            self.assertEqual(voice.run_helper("hello", ["yes"], lambda: False), ("", 0.0))
        popen.assert_not_called()

    def test_stopping_kills_the_helper_at_once(self):
        process = mock.MagicMock()
        process.poll.return_value = None                 # still running
        calls = {"n": 0}

        def keep_alive():
            calls["n"] += 1
            return calls["n"] < 3                        # stop on the third check

        with mock.patch.object(voice.subprocess, "Popen", return_value=process):
            self.assertEqual(voice.run_helper("hello", ["yes"], keep_alive), ("", 0.0))
        process.kill.assert_called_once()

    def test_the_helper_output_is_parsed(self):
        process = mock.MagicMock()
        process.poll.return_value = 0
        process.stdout.read.return_value = "HEARD|yes|0.87\n"
        with mock.patch.object(voice.subprocess, "Popen", return_value=process):
            self.assertEqual(voice.run_helper("hello", ["yes"], None), ("yes", 0.87))

    def test_a_helper_error_gives_nothing(self):
        process = mock.MagicMock()
        process.poll.return_value = 0
        process.stdout.read.return_value = "ERROR|no audio device\n"
        with mock.patch.object(voice.subprocess, "Popen", return_value=process),                 mock.patch("builtins.print") as printed:
            self.assertEqual(voice.run_helper("hello", ["yes"], None), ("", 0.0))
        printed.assert_called_once()


@unittest.skipUnless(os.name == "nt", "the speech engine is Windows only")
class RealSpeechRecognitionTests(unittest.TestCase):
    """Makes a sound file with the Windows voice and listens to it with the
    Windows recogniser (no microphone or loudspeaker is used)."""

    def spoken_wave(self, text):
        path = os.path.join(tempfile.mkdtemp(), "speech.wav")
        script = ("Add-Type -AssemblyName System.Speech; "
                  "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "$s.SelectVoice('Microsoft David Desktop'); "
                  "$s.SetOutputToWaveFile('" + path + "'); $s.Speak('" + text + "'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
        return path

    def test_yes_and_no_are_recognised(self):
        if not voice.available():
            self.skipTest("voice helper not available")
        for phrase, expected in [("yes", True), ("no", False)]:
            heard, confidence = voice.run_helper("", list(voice.YES_NO), None, wave=self.spoken_wave(phrase))
            self.assertEqual(voice.YES_NO.get(heard), expected, (phrase, heard))
            self.assertGreaterEqual(confidence, voice.MIN_CONFIDENCE)


if __name__ == "__main__":
    unittest.main()
