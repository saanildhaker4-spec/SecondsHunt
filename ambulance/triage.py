# =====================================================================
#  TRIAGE - the questions the 112 operator asks, and what they mean
# =====================================================================
#  NOTE: these questions and rules are a simplified example made for
#  this project. They are NOT a real medical protocol. A real control
#  room would use its own clinical protocol; only `triage` and the two
#  tables below would need to change.
# =====================================================================

# each question: (key, text, the usual answer)
QUESTIONS = [
    ("conscious", "Is the person conscious (awake and responding)?", True),
    ("breathing", "Is the person breathing normally?", True),
    ("chest_pain", "Is there chest pain or pressure?", False),
    ("stroke_signs", "Face drooping, slurred speech or one-side weakness?", False),
    ("bleeding", "Is there heavy bleeding that will not stop?", False),
    ("injury", "Was there a road accident, fall or serious injury?", False),
]

PRIORITY_NAMES = {
    1: "PRIORITY 1 - life-threatening",
    2: "PRIORITY 2 - urgent",
    3: "PRIORITY 3 - not urgent",
}

# how roads are priced for each priority (see routing.py)
MODE_FOR_PRIORITY = {1: "worst_case", 2: "balanced", 3: "average"}

# what a hospital must have for each kind of care
FACILITIES_FOR = {
    "cardiac": ["cath_lab", "icu"],            # heart attack, cardiac arrest
    "stroke": ["stroke_unit", "ct_scan"],      # a stroke needs a brain scan
    "accident": ["trauma_unit"],               # injuries
    "minor": ["general"],                      # no danger signs
}

FACILITY_NAMES = {
    "general": "general care", "trauma_unit": "trauma unit", "cath_lab": "cath lab",
    "stroke_unit": "stroke unit", "icu": "ICU", "blood_bank": "blood bank", "ct_scan": "CT scan",
}


def usual_answers():
    """The answers for a person with no problem."""
    return {key: usual for key, text, usual in QUESTIONS}


def triage(answers):
    """Turn the six answers (True = yes) into a result dictionary:
         care     : "cardiac", "stroke", "accident" or "minor"
         priority : 1, 2 or 3
         why      : a list of short reasons"""
    why = []

    # 1. what kind of hospital care is needed? (first match wins)
    if answers["injury"] or answers["bleeding"]:
        care = "accident"
    elif answers["stroke_signs"]:
        care = "stroke"
    elif answers["chest_pain"] or not answers["conscious"] or not answers["breathing"]:
        care = "cardiac"
    else:
        care = "minor"

    # 2. how urgent is it?
    if not answers["conscious"]:
        why.append("not conscious")
    if not answers["breathing"]:
        why.append("not breathing normally")
    if answers["bleeding"]:
        why.append("heavy bleeding")
    if answers["chest_pain"]:
        why.append("chest pain")
    if answers["stroke_signs"]:
        why.append("stroke signs")

    if len(why) > 0:
        priority = 1                       # any danger sign
    elif answers["injury"]:
        priority = 2                       # injured, but awake and breathing
        why.append("injury, but awake and breathing")
    else:
        priority = 3
        why.append("no danger signs")
    return {"care": care, "priority": priority, "why": why}


def required_facilities(care, priority):
    """The facilities a hospital MUST have for this care and priority."""
    needed = list(FACILITIES_FOR[care])
    if care == "accident" and priority == 1:
        needed.append("blood_bank")        # heavy bleeding needs blood ready
    return needed
