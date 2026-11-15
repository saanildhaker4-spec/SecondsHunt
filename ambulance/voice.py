# =====================================================================
#  VOICE - the program speaks a question and hears the answer
# =====================================================================
#  Python cannot speak or listen by itself, so each function here runs
#  voice_helper.ps1, which uses the speech tools built into Windows.
#  Nothing is downloaded and it works without the internet. It needs
#  Windows; on other systems the VOICE CALL button says so.
#
#  The program only listens for a fixed list of answers ("yes" and "no"
#  and a few longer phrases), which is much more reliable than free speech.
# =====================================================================

import os
import subprocess
import time

HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_helper.ps1")
MIN_CONFIDENCE = 0.45       # below this an answer counts as "not heard"

# Only clearly different phrases are allowed, so that "yes" and "no" are
# never mixed up (short words like "yeah" sounded too much like "no").
YES_NO = {
    "yes": True, "yes yes": True, "yes he is": True, "yes she is": True,
    "yes there is": True, "correct": True,
    "no": False, "no no": False, "no he is not": False, "no she is not": False,
    "no there is not": False, "negative": False,
}


def available():
    """True if spoken questions can work on this computer."""
    return os.name == "nt" and os.path.exists(HELPER)


def spoken(text):
    """Road and junction names as they should be SAID: 'Kanakapura Rd &
    13th Cross Rd' becomes 'Kanakapura Road and 13th Cross Road'."""
    return text.replace(" & ", " and ").replace(" Rd", " Road").replace(" St", " Street")


def run_helper(say, choices, keep_alive, wave=""):
    """Speak `say`, then listen for one of `choices` (a list of phrases).
    keep_alive is called again and again while we wait, so the window does
    not freeze. If it returns False the call was stopped: the helper is
    shut down at once. Returns (heard text, confidence); "" if nothing."""
    if keep_alive is not None and keep_alive() is False:
        return "", 0.0

    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", HELPER, "-Say", say, "-Choices", "|".join(choices)]
    if wave != "":
        command = command + ["-Wave", wave]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)

    while process.poll() is None:            # still speaking or listening
        if keep_alive is not None and keep_alive() is False:
            process.kill()                   # stop speaking and listening now
            process.wait()
            process.stdout.close()
            return "", 0.0
        time.sleep(0.05)

    output = process.stdout.read().strip()
    process.stdout.close()
    for line in output.split("\n"):
        parts = line.strip().split("|")
        if parts[0] == "HEARD" and len(parts) == 3:
            return parts[1], float(parts[2])
        if parts[0] == "ERROR":
            print("Voice problem:", line)
    return "", 0.0


def speak(text, keep_alive):
    """Just say something."""
    run_helper(text, [], keep_alive)


def ask_yes_no(question, keep_alive):
    """Ask a question aloud. Returns True, False, or None if the answer
    was not understood (it tries twice)."""
    for attempt in [1, 2]:
        say = question if attempt == 1 else "Sorry, I did not catch that. " + question
        heard, confidence = run_helper(say, list(YES_NO.keys()), keep_alive)
        if heard in YES_NO and confidence >= MIN_CONFIDENCE:
            return YES_NO[heard]
    return None
