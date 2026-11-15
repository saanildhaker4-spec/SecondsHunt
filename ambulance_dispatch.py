# =====================================================================
#  BASELINE vs SMART DISPATCH - comparison on the Bangalore city
# =====================================================================
#  Runs a fixed list of test emergencies through two dispatchers and
#  prints a table comparing them.
#
#    BASELINE : nearest ambulance by km, shortest route by km,
#               nearest hospital by km (ignores traffic, priority,
#               facilities and beds)
#    SMART    : our system (time-of-day traffic, parallel roads,
#               triage priority, hospital facility and free beds)
#
#  The city, the route finder, the triage rules and the smart
#  dispatcher all come from city_engine.py.
#
#  This file always uses the FIXED default city (never a random one),
#  so that the test cases below mean the same thing every time.
#
#  NOTE: travel times, ambulances and hospitals are made-up test data,
#  and the test cases were chosen to show where the two systems differ.
# =====================================================================

from city_engine import *


# ---------------------------------------------------------------------
# PART 1: THE BASELINE DISPATCHER (the old way)
# ---------------------------------------------------------------------
def baseline_dispatch(place, clock):
    """Nearest ambulance by km and nearest hospital by km.
    Returns a plan dictionary shaped like the smart dispatcher's."""
    ambulance, route1 = nearest_ambulance_by_distance(place, clock)

    best_hospital = None
    best_km = None
    route2 = []
    for name in hospitals:
        km, route = find_route(place, hospitals[name]["at"], clock, "distance", blocked)
        if km is not None and (best_km is None or km < best_km):
            best_hospital, best_km, route2 = name, km, route

    average, worst = measure_route(route1, clock)
    return {
        "ambulance": ambulance,
        "route1": route1,
        "average": average,
        "worst": worst,
        "hospital": best_hospital,
        "route2": route2,
    }


# ---------------------------------------------------------------------
# PART 2: PRINTING ONE CASE
# ---------------------------------------------------------------------
def show_plan(title, plan, emergency_type, priority):
    print("  " + title)
    print("    Ambulance :", plan["ambulance"])
    print("    To patient:", show_route(plan["route1"]))
    print("    Response  :", plan["average"], "min average,", plan["worst"], "min worst case")
    print("    Hospital  :", plan["hospital"], "via", show_route(plan["route2"]))
    if hospital_can_treat(plan["hospital"], emergency_type, priority):
        print("    Hospital can treat this patient: YES")
    else:
        print("    Hospital can treat this patient: NO  <-- wrong hospital!")


def run_case(case):
    """Run one emergency through both dispatchers. Returns both plans."""
    place = case["place"]
    clock = case["clock"]

    # start from the usual answers, then apply this case's answers
    answers = {}
    for key, question, usual in triage_questions:
        answers[key] = usual
    for key in case["answers"]:
        answers[key] = case["answers"][key]
    emergency_type, priority, why = triage(answers)

    # close this case's blocked roads (in both directions)
    for a, b, name in case["blocked"]:
        blocked.add((a, b, name))
        blocked.add((b, a, name))

    print()
    print("=" * 72)
    print(case["label"])
    print("Time", show_clock(clock), "(" + get_period(clock) + ") | Place:", place,
          "| Care:", emergency_type)
    print(priority_names[priority], "(" + ", ".join(why) + ")")
    for a, b, name in case["blocked"]:
        print("BLOCKED:", name, "between", a, "and", b)
    print("-" * 72)

    old = baseline_dispatch(place, clock)
    new, reasons = smart_dispatch(place, emergency_type, priority, clock)

    show_plan("BASELINE (nearest by distance)", old, emergency_type, priority)
    print()
    print("  SMART DISPATCH - how it decided:")
    for line in reasons:
        print("    " + line)
    show_plan("SMART DISPATCH - final plan", new, emergency_type, priority)

    # open the roads again so the next case starts fresh
    for a, b, name in case["blocked"]:
        blocked.remove((a, b, name))
        blocked.remove((b, a, name))

    return old, new, emergency_type, priority


# ---------------------------------------------------------------------
# PART 3: THE TEST EMERGENCIES
# ---------------------------------------------------------------------
# "answers" only lists the triage answers that differ from the usual
# ones (usual = conscious, breathing, and no other danger signs).
# Every case starts with all 5 ambulances free.

cases = [
    {"label": "Case 1: quiet night, injury at Majestic",
     "clock": 2 * 60, "place": "Majestic",
     "answers": {"injury": True}, "blocked": []},

    {"label": "Case 2: rush hour, unconscious with chest pain at Majestic",
     "clock": 9 * 60, "place": "Majestic",
     "answers": {"conscious": False, "chest_pain": True}, "blocked": []},

    {"label": "Case 3: same place and time, no danger signs",
     "clock": 9 * 60, "place": "Majestic",
     "answers": {}, "blocked": []},

    {"label": "Case 4: afternoon, no danger signs at Bangalore University (clinic is full)",
     "clock": 14 * 60, "place": "Bangalore University",
     "answers": {}, "blocked": []},

    {"label": "Case 5: evening rush, stroke signs at Palace Grounds",
     "clock": 18 * 60, "place": "Palace Grounds",
     "answers": {"stroke_signs": True}, "blocked": []},

    {"label": "Case 6: rush hour, stroke signs at PES University",
     "clock": 9 * 60, "place": "PES University",
     "answers": {"stroke_signs": True}, "blocked": []},

    {"label": "Case 7: rush hour, injury at Silk Board",
     "clock": 9 * 60, "place": "Silk Board",
     "answers": {"injury": True}, "blocked": []},

    {"label": "Case 8: Case 3 again, but Seshadri Rd is blocked",
     "clock": 9 * 60, "place": "Majestic",
     "answers": {}, "blocked": [("Race Course", "Majestic", "Seshadri Rd")]},
]

results = []
for case in cases:
    old, new, emergency_type, priority = run_case(case)
    results.append((old, new, emergency_type, priority))


# ---------------------------------------------------------------------
# PART 4: SUMMARY TABLE
# ---------------------------------------------------------------------
print()
print("=" * 72)
print("SUMMARY  (time to reach the patient, in minutes)")
print("-" * 72)
print("Case".ljust(6), "Base avg".ljust(10), "Base worst".ljust(12),
      "Smart avg".ljust(11), "Smart worst".ljust(13), "Right hospital?")

old_wrong = 0
new_wrong = 0
old_average_total = 0
new_average_total = 0
old_worst_total = 0
new_worst_total = 0
case_number = 0
for old, new, emergency_type, priority in results:
    case_number = case_number + 1
    if hospital_can_treat(old["hospital"], emergency_type, priority):
        old_text = "yes"
    else:
        old_text = "NO"
        old_wrong = old_wrong + 1
    if hospital_can_treat(new["hospital"], emergency_type, priority):
        new_text = "yes"
    else:
        new_text = "NO"
        new_wrong = new_wrong + 1
    old_average_total = old_average_total + old["average"]
    new_average_total = new_average_total + new["average"]
    old_worst_total = old_worst_total + old["worst"]
    new_worst_total = new_worst_total + new["worst"]
    print(str(case_number).ljust(6),
          str(old["average"]).ljust(10), str(old["worst"]).ljust(12),
          str(new["average"]).ljust(11), str(new["worst"]).ljust(13),
          "base: " + old_text + ", smart: " + new_text)

print("-" * 72)
print("Total average response    : baseline", old_average_total, "min, smart",
      new_average_total, "min")
print("Total worst-case response : baseline", old_worst_total, "min, smart",
      new_worst_total, "min")
print("Sent to a hospital that could NOT treat the patient : baseline",
      old_wrong, "of", len(results), ", smart", new_wrong, "of", len(results))
