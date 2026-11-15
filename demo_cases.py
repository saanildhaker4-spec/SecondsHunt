# =====================================================================
#  DEMO CASES - the cases used in the demo, run without the window
# =====================================================================
#  Prints, for each case, what the SMART dispatcher decides and what the
#  old "nearest by distance" rule would do, so the numbers in DEMO.md
#  can be checked by anyone:
#
#       python demo_cases.py
#
#  Times are minutes: average / worst case.
#  All data is made up (see README.md).
# =====================================================================

from city_engine import *


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
# triage answers that differ from the usual ones (usual = conscious,
# breathing, and no other danger sign)
CARDIAC = {"conscious": False, "chest_pain": True}
STROKE = {"stroke_signs": True}
INJURY = {"injury": True}
NOTHING = {}


def baseline(place, clock, emergency_type, priority):
    """The old way: nearest ambulance by km, nearest hospital by km."""
    ambulance, route1 = nearest_ambulance_by_distance(place, clock)
    best_hospital = None
    best_km = None
    for name in hospitals:
        km, route = find_route(place, hospitals[name]["at"], clock, "distance", blocked)
        if km is not None and (best_km is None or km < best_km):
            best_hospital, best_km = name, km
    average, worst = measure_route(route1, clock)
    return ambulance, route1, average, worst, best_hospital, \
        missing_for(best_hospital, emergency_type, priority)


def run_case(title, hour, place, changes, closed_roads=()):
    clock = hour * 60

    # the answers: usual ones, then this case's changes
    answers = {}
    for key, question, usual in triage_questions:
        answers[key] = usual
    for key in changes:
        answers[key] = changes[key]
    emergency_type, priority, why = triage(answers)

    for a, b, name in closed_roads:                  # close roads, both directions
        blocked.add((a, b, name))
        blocked.add((b, a, name))

    plan, reasons = smart_dispatch(place, emergency_type, priority, clock)
    old = baseline(place, clock, emergency_type, priority)

    print()
    print(title)
    print("  " + show_clock(clock) + " (" + get_period(clock) + ") at " + place + " | "
          + priority_names[priority] + " (" + ", ".join(why) + ")")
    print("  needs: " + ", ".join(required_facilities(emergency_type, priority)))
    for a, b, name in closed_roads:
        print("  BLOCKED: " + name + " between " + a + " and " + b)
    print("  SMART   : " + plan["ambulance"] + " by " + show_route(plan["route1"])
          + "  -> " + str(plan["average"]) + " / " + str(plan["worst"]))
    if plan["hospital"] is None:
        print("            no hospital can treat this case")
    else:
        print("            to " + plan["hospital"] + " by " + show_route(plan["route2"]))
    print("  NEAREST : " + old[0] + " by " + show_route(old[1])
          + "  -> " + str(old[2]) + " / " + str(old[3]))
    if len(old[5]) == 0:
        print("            to " + old[4] + " (it can treat the patient)")
    else:
        print("            to " + old[4] + " - WRONG: " + ", ".join(old[5]))

    for a, b, name in closed_roads:                  # open them again
        blocked.remove((a, b, name))
        blocked.remove((b, a, name))


# ---------------------------------------------------------------------
# The fixed city (the same every time)
# ---------------------------------------------------------------------
default_city()
print("=" * 72)
print("FIXED CITY  (python map_112.py default)")
print("=" * 72)
run_case("F1  Nearest is not fastest: stroke in the morning rush", 9, "Palace Grounds", STROKE)
run_case("F2  Priority changes the route: unconscious with chest pain", 9, "Majestic", CARDIAC)
run_case("F3  Same place and time, no danger signs", 9, "Majestic", NOTHING)
run_case("F4  Night: quiet roads, the two systems agree", 2, "Majestic", CARDIAC)
run_case("F5  The nearest hospital is full", 14, "Bangalore University", NOTHING)
run_case("F6  A blocked road (compare with F3)", 9, "Majestic", NOTHING,
         [("Race Course", "Majestic", "Seshadri Rd")])

# ---------------------------------------------------------------------
# Random cities, replayed from their seed numbers
# ---------------------------------------------------------------------
for seed, place, changes, label in [
        (1, "Orion Mall", CARDIAC, "Unconscious with chest pain"),
        (1, "Bangalore University", STROKE, "Stroke signs"),
        (3, "Richmond Circle", CARDIAC, "Unconscious with chest pain"),
        (3, "Richmond Circle", STROKE, "Stroke signs"),
        (6, "Majestic", CARDIAC, "Unconscious with chest pain")]:
    random_city(seed)
    print()
    print("=" * 72)
    print("RANDOM CITY, seed " + str(seed) + "  (python map_112.py " + str(seed) + ")")
    print("=" * 72)
    run_case("S" + str(seed) + "  " + label, 9, place, changes)
