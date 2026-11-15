# =====================================================================
#  VOICE - lets the program speak a question and hear the answer
# =====================================================================
#  Python cannot speak or listen by itself, so each function here runs
#  voice_helper.ps1, which uses the speech tools built into Windows.
#  Nothing is downloaded and it works without the internet.
#
#  The program only listens for a fixed list of answers (for example
#  "yes" and "no"), which makes it much more reliable than free speech.
# =====================================================================

import os
import subprocess
import time

HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_helper.ps1")
MIN_CONFIDENCE = 0.45       # below this we treat the answer as "not heard"


def run_helper(say, choices, keep_alive, wave=""):
    """Speak `say`, then listen for one of `choices` (a list of phrases).
    keep_alive is a function called again and again while we wait, so
    the window does not freeze (use None if there is no window).
    If keep_alive() returns False the call was stopped: the helper is
    shut down at once so nothing keeps running in the background.
    Returns (heard_text, confidence). heard_text is "" if nothing."""
    if keep_alive is not None and keep_alive() is False:
        return "", 0.0                  # already stopped: do not even start

    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", HELPER, "-Say", say, "-Choices", "|".join(choices)]
    if wave != "":
        command = command + ["-Wave", wave]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)

    while process.poll() is None:       # still speaking or listening
        if keep_alive is not None and keep_alive() is False:
            process.kill()              # stop speaking / listening now
            process.wait()
            return "", 0.0
        time.sleep(0.05)

    output = process.stdout.read().strip()
    for line in output.split("\n"):
        parts = line.strip().split("|")
        if parts[0] == "HEARD" and len(parts) == 3:
            return parts[1], float(parts[2])
        if parts[0] == "ERROR":
            print("Voice problem:", line)
    return "", 0.0


def speak(text, keep_alive):
    """Just say something (no listening)."""
    run_helper(text, [], keep_alive)


def ask(question, meanings, keep_alive):
    """Ask a question aloud and return what the answer MEANS.
    meanings is a dictionary: spoken phrase -> value to return.
    Tries twice. Returns None if the answer was not understood."""
    phrases = list(meanings.keys())
    for attempt in [1, 2]:
        if attempt == 1:
            say = question
        else:
            say = "Sorry, I did not catch that. " + question
        heard, confidence = run_helper(say, phrases, keep_alive)
        if heard in meanings and confidence >= MIN_CONFIDENCE:
            return meanings[heard]
    return None


# ---------------------------------------------------------------------
# The three kinds of question the 112 operator asks
# ---------------------------------------------------------------------
# Only clearly different phrases are allowed, so that "yes" and "no"
# are never mixed up. (Short words like "yeah" sounded too much like
# "no" in testing.)
YES_NO = {
    "yes": True, "yes yes": True, "yes he is": True, "yes she is": True,
    "yes there is": True, "correct": True,
    "no": False, "no no": False, "no he is not": False, "no she is not": False,
    "no there is not": False, "negative": False,
}


def ask_yes_no(question, keep_alive):
    """Returns True, False, or None if not understood."""
    return ask(question, YES_NO, keep_alive)


def spoken_name(place):
    """How a place name is said aloud: 'KR Puram' -> 'K R Puram'."""
    place = place.replace("KR ", "K R ").replace("BTM ", "B T M ")
    return place.replace("PES ", "P E S ")


# The Windows recognizer is American English, so it guesses how to
# say Indian place names from the spelling. These extra spellings
# give it more ways to match the same place.
OTHER_SPELLINGS = {
    "Manyata Tech Park": ["Manyatha Tech Park", "Man yata Tech Park"],
    "Indiranagar": ["Indira nagar", "Indira nuggar"],
    "Jayanagar": ["Jaya nagar", "Jaya nuggar"],
    "Koramangala": ["Kora mangala", "Kora mungala"],
    "Bangalore University": ["Bengaluru University"],
}


def place_meanings(places):
    """Dictionary: every way of saying a place -> the place name."""
    meanings = {}
    for place in places:
        meanings[spoken_name(place)] = place
        if place in OTHER_SPELLINGS:
            for spelling in OTHER_SPELLINGS[place]:
                meanings[spelling] = place
    return meanings


def ask_place(question, places, keep_alive):
    """Returns one of the place names, or None. Confirms the answer."""
    meanings = place_meanings(places)
    for attempt in [1, 2]:
        place = ask(question, meanings, keep_alive)
        if place is None:
            return None
        sure = ask_yes_no("Did you say " + spoken_name(place) + "?", keep_alive)
        if sure:
            return place
    return None


NUMBER_WORDS = ["one", "two", "three", "four", "five", "six", "seven",
                "eight", "nine", "ten", "eleven", "twelve"]


def ask_hour(question, keep_alive):
    """Listens for answers like 'nine a m' or 'six p m'.
    Returns the hour in 24-hour form (0 to 23), or None."""
    meanings = {"noon": 12, "midnight": 0}
    number = 0
    for word in NUMBER_WORDS:
        number = number + 1
        meanings[word + " a m"] = number % 12           # twelve a m -> 0
        meanings[word + " p m"] = number % 12 + 12      # twelve p m -> 12
    return ask(question, meanings, keep_alive)
