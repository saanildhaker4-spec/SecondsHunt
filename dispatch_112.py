# =====================================================================
#  112 EMERGENCY RESPONSE - DISPATCH CONSOLE (text version)
# =====================================================================
#  An interactive control-room screen. The operator takes a 112 call,
#  types in where and what the emergency is, and the system picks the
#  ambulance, the route and the hospital, and explains why.
#
#  The city and the routing live in city_engine.py. The line below
#  brings everything from that file into this one.
# =====================================================================

from city_engine import *


# ---------------------------------------------------------------------
# PART 4: INPUT HELPERS
# ---------------------------------------------------------------------
def choose(title, options):
    """Show a numbered list and return the item the operator picks."""
    print()
    print(title)
    number = 1
    for item in options:
        print("   " + str(number) + ". " + str(item))
        number = number + 1
    while True:
        answer = input("   Enter number: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        print("   Please type a number from 1 to " + str(len(options)))


def ask_clock(old_clock):
    """Ask for a time like 09:30. Pressing Enter keeps the old time."""
    while True:
        answer = input("   Time now (HH:MM, or Enter to keep "
                       + show_clock(old_clock) + "): ").strip()
        if answer == "":
            return old_clock
        parts = answer.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            hour = int(parts[0])
            minute = int(parts[1])
            if hour < 24 and minute < 60:
                return hour * 60 + minute
        print("   Please type the time like 09:30")


# ---------------------------------------------------------------------
# PART 5: SCREENS
# ---------------------------------------------------------------------
call_log = []           # one dictionary per call handled


def show_units():
    print()
    print("  AMBULANCE STATUS")
    for name in ambulances:
        if name in busy:
            status = "ON CALL (will finish at " + ambulances[name] + ")"
        else:
            status = "FREE at " + ambulances[name]
        print("     " + name + " : " + status)


def show_hospitals():
    print()
    print("  HOSPITAL STATUS")
    for name in hospitals:
        hospital = hospitals[name]
        print("     " + name + " (" + hospital["at"] + ") : "
              + str(hospital["beds_free"]) + " beds free, wait "
              + str(hospital["wait"]) + " min, has " + str(sorted(hospital["facilities"])))


def show_log():
    print()
    print("  CALL LOG")
    if len(call_log) == 0:
        print("     (no calls yet)")
    for call in call_log:
        print("     " + call["id"] + " | " + show_clock(call["clock"]) + " | "
              + call["type"] + " at " + call["place"] + " | " + call["ambulance"]
              + " -> " + call["hospital"] + " | reach patient in "
              + str(call["average"]) + " min")


def new_call(clock):
    """Take a 112 call and dispatch an ambulance."""
    print()
    print("  ---- NEW 112 CALL ----")
    place = choose("Where is the emergency?", places)

    # ask the caller the triage questions
    print()
    print("Ask the caller (answer y or n):")
    answers = {}
    for key, question, usual in triage_questions:
        answer = input("   " + question + " (y/n): ").strip().lower()
        answers[key] = (answer == "y")
    emergency_type, priority, why = triage(answers)
    print()
    print("  " + priority_names[priority] + " (" + ", ".join(why) + ")")
    print("  Care needed: " + emergency_type + " -> " + ", ".join(required_facilities(emergency_type, priority)))

    plan, reasons = smart_dispatch(place, emergency_type, priority, clock)
    print()
    for line in reasons:
        print("  " + line)
    if plan is None:
        print()
        print("  !! NO AMBULANCE AVAILABLE. Free a unit or call a neighbouring district.")
        return

    print()
    print("  " + "*" * 60)
    print("  DISPATCH ORDER  INC-" + str(len(call_log) + 1).rjust(3, "0"))
    print("  Send       : " + plan["ambulance"])
    print("  Route      : " + show_route(plan["route1"]))
    print("  Reaches patient in " + str(plan["average"]) + " min (worst case "
          + str(plan["worst"]) + " min)")
    if plan["hospital"] is None:
        print("  Hospital   : !! NONE can treat this case right now. Call hospitals directly.")
        hospital_name = "no hospital"
    else:
        hospital_name = plan["hospital"]
        print("  Take to    : " + hospital_name)
        print("  Route      : " + show_route(plan["route2"]))
    print("  " + "*" * 60)

    # comparison with the old "nearest by distance" rule
    old_name, old_route = nearest_ambulance_by_distance(place, clock)
    old_average, old_worst = measure_route(old_route, clock)
    print("  For comparison, nearest-by-distance would send " + old_name
          + ": " + str(old_average) + " min (worst case " + str(old_worst) + " min)")

    # update the control room: ambulance is busy, a bed is taken
    commit_dispatch(plan)

    call_log.append({
        "id": "INC-" + str(len(call_log) + 1).rjust(3, "0"),
        "clock": clock, "place": place, "type": emergency_type,
        "ambulance": plan["ambulance"], "hospital": hospital_name,
        "average": plan["average"],
    })


def free_ambulance():
    """Mark an ambulance as back in service."""
    if len(busy) == 0:
        print()
        print("  All ambulances are already free.")
        return
    name = choose("Which ambulance is back in service?", sorted(busy))
    busy.remove(name)
    print("  " + name + " is now FREE at " + ambulances[name])


def toggle_road():
    """Close a road, or open it again if it is already closed."""
    # build a list of every road once (not both directions)
    all_roads = []
    for key in roads:
        for option in roads[key]:
            if (key[1], key[0], option["name"]) not in all_roads:
                all_roads.append((key[0], key[1], option["name"]))

    labels = []
    for a, b, name in all_roads:
        label = name + " (" + a + " - " + b + ")"
        if (a, b, name) in blocked:
            label = label + "  [BLOCKED]"
        labels.append(label)

    picked = choose("Which road? (picking a blocked road opens it again)", labels)
    a, b, name = all_roads[labels.index(picked)]
    if (a, b, name) in blocked:
        blocked.remove((a, b, name))
        blocked.remove((b, a, name))
        print("  " + name + " is OPEN again.")
    else:
        blocked.add((a, b, name))
        blocked.add((b, a, name))
        print("  " + name + " between " + a + " and " + b + " is now BLOCKED.")


# ---------------------------------------------------------------------
# PART 6: THE MAIN MENU
# ---------------------------------------------------------------------
def main():
    clock = 9 * 60          # the console starts at 09:00
    start_city()            # a new random city (see city_engine.py)
    print()
    print("=" * 64)
    print("        112  EMERGENCY RESPONSE  -  DISPATCH CONSOLE")
    print("        " + describe_city())
    print("=" * 64)

    while True:
        print()
        print("-" * 64)
        print(" Time " + show_clock(clock) + " (" + get_period(clock) + " traffic)"
              + " | Free ambulances: " + str(len(ambulances) - len(busy))
              + "/" + str(len(ambulances))
              + " | Blocked roads: " + str(len(blocked) // 2))
        print("-" * 64)
        print("   1. New 112 call")
        print("   2. Ambulance status")
        print("   3. Hospital status")
        print("   4. Block / open a road")
        print("   5. Ambulance back in service")
        print("   6. Change the time")
        print("   7. Call log")
        print("   8. New random city")
        print("   0. Exit")
        answer = input(" Choose: ").strip()

        if answer == "1":
            new_call(clock)
        elif answer == "2":
            show_units()
        elif answer == "3":
            show_hospitals()
        elif answer == "4":
            toggle_road()
        elif answer == "5":
            free_ambulance()
        elif answer == "6":
            clock = ask_clock(clock)
        elif answer == "7":
            show_log()
        elif answer == "8":
            random_city(new_seed())
            call_log.clear()
            print(" NEW CITY: " + describe_city())
            show_hospitals()
        elif answer == "0":
            print(" Console closed.")
            break
        else:
            print(" Please choose a number from the menu.")


main()
