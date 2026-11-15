# =====================================================================
#  CITY ENGINE - shared by dispatch_112.py (text) and map_112.py (map)
# =====================================================================
#  Holds the city (a multigraph), the route finder, the ambulances,
#  the hospitals and the dispatch decision.
#  Uses only lists, tuples, sets, dictionaries and functions.
#
#  NOTE: the junction and road names are real Bangalore names, but the
#  layout is a simplified grid and the travel times, ambulances and
#  hospitals are made-up test data.
#
#  The city is always a 4 x 4 grid. The program can build the FIXED
#  city (default_city) or a RANDOM one (random_city): the junction
#  names move to different spots on the grid, the roads move to
#  different grid edges, and the hospitals get random places, beds and
#  facilities. A random city is made from a "seed" number: the same
#  seed always gives the same city, so a good city can be replayed.
# =====================================================================

import random
import sys

# ---------------------------------------------------------------------
# PART 1: THE CITY (a multigraph on a 4 x 4 grid)
# ---------------------------------------------------------------------
# roads[(from, to)] = LIST of road options between the two junctions.
# Each option: {"name", "km", "times": {period: (average, extra)}}
# worst case time for a road = average + extra

roads = {}              # the road network
places = []             # junction names, in grid order (row by row)
slot_of = {}            # junction name -> (row, column) on the grid

GRID = 4                # the grid is 4 x 4


def add_road(a, b, name, km, night, day, rush):
    """Add a two-way road between junctions a and b."""
    option = {
        "name": name,
        "km": km,
        "times": {"night": night, "day": day, "rush": rush},
    }
    for key in [(a, b), (b, a)]:
        if key not in roads:
            roads[key] = []
        roads[key].append(option)


# The grid has 16 SLOTS, numbered row by row:
#     0  1  2  3
#     4  5  6  7
#     8  9 10 11
#    12 13 14 15
# and 24 EDGES, each joining two neighbouring slots.
grid_edges = []
for row in range(GRID):                       # left-right edges (12)
    for column in range(GRID - 1):
        grid_edges.append((row * GRID + column, row * GRID + column + 1))
for row in range(GRID - 1):                   # up-down edges (12)
    for column in range(GRID):
        grid_edges.append((row * GRID + column, (row + 1) * GRID + column))

# The 16 junction names, in the order of the fixed city's slots.
# (Names were chosen to be easy for the voice recognizer.)
default_names = ["Orion Mall", "Palace Grounds", "Manyata Tech Park", "KR Puram",
                 "Race Course", "Majestic", "Trinity Circle", "Indiranagar",
                 "Bangalore University", "KR Market", "Richmond Circle", "Koramangala",
                 "PES University", "Jayanagar", "BTM Layout", "Silk Board"]

# A ROAD BUNDLE is the list of road options between two neighbouring
# junctions. A bundle with TWO options is a pair of parallel roads:
# a quick-but-unpredictable one and a longer, steady one.
# default_bundles[i] belongs to grid_edges[i] in the fixed city. In a
# random city the bundles are shuffled onto different edges.
#
#           name            km   night   day     rush
default_bundles = [
    # ---- left-right edges ----
    [("CV Raman Rd", 5, (4, 0), (5, 1), (7, 2))],
    [("Bellary Rd", 5, (4, 0), (5, 1), (7, 2))],
    [("Outer Ring Rd", 5, (4, 0), (5, 1), (7, 2))],
    [("Seshadri Rd", 2, (3, 0), (4, 1), (6, 6)),
     ("Race Course Rd", 3, (5, 0), (6, 1), (8, 1))],
    [("MG Road", 2, (3, 0), (4, 1), (6, 6)),
     ("Cubbon Rd", 3, (4, 0), (5, 0), (7, 1))],
    [("Old Madras Rd", 2, (3, 0), (4, 1), (6, 6)),
     ("Old Airport Rd", 3, (5, 0), (6, 1), (8, 1))],
    [("Mysore Rd", 3, (4, 0), (5, 1), (6, 1))],
    [("Mission Rd", 3, (4, 0), (5, 1), (6, 1)),
     ("Lalbagh Rd", 4, (4, 0), (5, 0), (5, 0))],
    [("Hosur Rd", 3, (4, 0), (5, 1), (6, 1))],
    [("Outer Ring Rd", 3, (4, 0), (5, 1), (6, 2))],
    [("Marenahalli Rd", 2, (3, 0), (4, 2), (5, 7)),
     ("Outer Ring Rd", 3, (4, 0), (5, 1), (6, 2))],
    [("Outer Ring Rd", 3, (4, 0), (5, 1), (6, 2))],
    # ---- up-down edges ----
    [("Rajkumar Rd", 3, (4, 0), (5, 1), (7, 2))],
    [("Palace Rd", 2, (3, 0), (4, 1), (10, 5))],
    [("Jayamahal Rd", 3, (4, 0), (5, 1), (6, 1))],
    [("Old Madras Rd", 3, (4, 0), (5, 1), (7, 3))],
    [("Chord Rd", 3, (4, 0), (5, 1), (7, 2))],
    [("BVK Iyengar Rd", 2, (3, 0), (4, 1), (8, 4))],
    [("Richmond Rd", 3, (4, 0), (5, 1), (6, 1))],
    [("Inner Ring Rd", 3, (4, 0), (5, 1), (8, 4))],
    [("Outer Ring Rd", 3, (4, 0), (5, 1), (7, 2))],
    [("KR Rd", 2, (3, 0), (4, 1), (8, 4))],
    [("Bannerghatta Rd", 3, (4, 0), (5, 1), (6, 1))],
    [("Hosur Rd", 3, (4, 0), (6, 2), (9, 5))],
]


# ---------------------------------------------------------------------
# PART 2: TIME HELPERS AND THE ROUTE FINDER
# ---------------------------------------------------------------------
def get_period(clock):
    """Turn a clock time (minutes after midnight) into a traffic period."""
    hour = (int(clock) // 60) % 24
    if 8 <= hour < 11 or 17 <= hour < 21:
        return "rush"
    if 6 <= hour < 23:
        return "day"
    return "night"


def show_clock(clock):
    """Turn minutes after midnight into text like 09:30."""
    hour = (int(clock) // 60) % 24
    minute = int(clock) % 60
    return str(hour).rjust(2, "0") + ":" + str(minute).rjust(2, "0")


def road_cost(option, period, mode):
    """Cost of one road option.
    mode = distance / average / balanced / worst_case."""
    average, extra = option["times"][period]
    if mode == "distance":
        return option["km"]
    if mode == "average":
        return average
    if mode == "balanced":
        return average + extra / 2    # half-way between average and worst
    return average + extra


def find_route(start, goal, start_clock, mode, blocked):
    """Dijkstra's algorithm. Returns (cost, route).
    route is a list of steps (from_junction, to_junction, road_name)."""
    best_cost = {start: 0}
    clock_at = {start: start_clock}
    came_from = {}
    finished = set()

    while True:
        current = None
        for junction in best_cost:
            if junction not in finished:
                if current is None or best_cost[junction] < best_cost[current]:
                    current = junction

        if current is None:
            return None, []
        if current == goal:
            break
        finished.add(current)

        period = get_period(clock_at[current])
        for key in roads:
            if key[0] != current:
                continue
            neighbour = key[1]
            for option in roads[key]:
                if (current, neighbour, option["name"]) in blocked:
                    continue
                new_cost = best_cost[current] + road_cost(option, period, mode)
                new_clock = clock_at[current] + option["times"][period][0]

                if neighbour not in best_cost:
                    better = True
                elif new_cost < best_cost[neighbour]:
                    better = True
                elif (new_cost == best_cost[neighbour] and mode != "distance"
                      and new_clock < clock_at[neighbour]):
                    better = True     # a tie: prefer the faster average
                else:
                    better = False

                if better:
                    best_cost[neighbour] = new_cost
                    clock_at[neighbour] = new_clock
                    came_from[neighbour] = (current, neighbour, option["name"])

    route = []
    junction = goal
    while junction != start:
        step = came_from[junction]
        route.append(step)
        junction = step[0]
    route.reverse()
    return best_cost[goal], route


def measure_route(route, start_clock):
    """Drive along a route and return (average_time, worst_time)."""
    average_time = 0
    worst_time = 0
    for step in route:
        a, b, name = step
        period = get_period(start_clock + average_time)
        for option in roads[(a, b)]:
            if option["name"] == name:
                average, extra = option["times"][period]
                average_time = average_time + average
                worst_time = worst_time + average + extra
    return average_time, worst_time


def show_route(route):
    if len(route) == 0:
        return "(already there)"
    text = route[0][0]
    for step in route:
        text = text + " -[" + step[2] + "]-> " + step[1]
    return text


# ---------------------------------------------------------------------
# PART 3: AMBULANCES, HOSPITALS AND THE DISPATCH DECISION
# ---------------------------------------------------------------------
ambulances = {}         # ambulance name -> junction where it is now
busy = set()            # names of ambulances that are out on a call
blocked = set()         # (from, to, road_name) tuples that are closed

# hospitals[name] = {"at": junction, "beds_free": number, "wait": minutes,
#                    "facilities": set of facility names}
# The hospital names are invented (not real hospitals), because their
# beds and facilities here are made-up numbers.
hospitals = {}

# Where each ambulance starts. (The junction NAMES stay the same, but
# in a random city those names sit in different places on the grid.)
start_ambulances = {"Amb-1": "Race Course", "Amb-2": "Manyata Tech Park",
                    "Amb-3": "KR Market", "Amb-4": "Indiranagar",
                    "Amb-5": "BTM Layout"}

# ---------------------------------------------------------------------
# FACILITY CONSTRAINTS: what a hospital must have for each situation
# ---------------------------------------------------------------------
# NOTE: a simplified example, not a real medical protocol.
facilities_for = {
    "cardiac": ["cath_lab", "icu"],            # heart attack, cardiac arrest
    "stroke": ["stroke_unit", "ct_scan"],      # stroke needs a brain scan
    "accident": ["trauma_unit"],               # injuries
    "minor": ["general"],                      # no danger signs
}

# every kind of facility a hospital can have (besides "general")
extra_facilities = ["trauma_unit", "cath_lab", "stroke_unit", "icu",
                    "blood_bank", "ct_scan"]

# short codes shown on the map
facility_short = {"trauma_unit": "TRAUMA", "cath_lab": "CATH", "stroke_unit": "STROKE",
                  "icu": "ICU", "blood_bank": "BLD", "ct_scan": "CT"}

SCENE_TIME = 5          # minutes the crew spends with the patient


def required_facilities(emergency_type, priority):
    """The facilities a hospital MUST have for this emergency."""
    needed = list(facilities_for[emergency_type])
    if emergency_type == "accident" and priority == 1:
        needed.append("blood_bank")      # heavy bleeding needs blood ready
    return needed


def missing_for(name, emergency_type, priority):
    """What stops this hospital from treating the case, as a list of
    short texts. An empty list means the hospital CAN treat it."""
    hospital = hospitals[name]
    missing = []
    for facility in required_facilities(emergency_type, priority):
        if facility not in hospital["facilities"]:
            missing.append("no " + facility)
    if hospital["beds_free"] <= 0:
        missing.append("no free bed")
    return missing


def hospital_can_treat(name, emergency_type, priority):
    return len(missing_for(name, emergency_type, priority)) == 0


def nearest_ambulance_by_distance(place, clock):
    """The OLD way, only used to show the operator a comparison."""
    best_name = None
    best_km = None
    best_route = []
    for name in ambulances:
        if name in busy:
            continue
        km, route = find_route(ambulances[name], place, clock, "distance", blocked)
        if km is not None and (best_km is None or km < best_km):
            best_name, best_km, best_route = name, km, route
    return best_name, best_route


# ---------------------------------------------------------------------
# TRIAGE: the questions the 112 operator asks the caller
# ---------------------------------------------------------------------
# NOTE: these questions and rules are a simplified example made for
# this project. They are NOT a real medical protocol.
#
# Each question is a tuple: (short key, question text, usual answer)

triage_questions = [
    ("conscious", "Is the person conscious (awake and responding)?", True),
    ("breathing", "Is the person breathing normally?", True),
    ("chest_pain", "Is there chest pain or pressure?", False),
    ("stroke_signs", "Face drooping, slurred speech or one-side weakness?", False),
    ("bleeding", "Is there heavy bleeding that will not stop?", False),
    ("injury", "Was there a road accident, fall or serious injury?", False),
]

# how the route is chosen for each priority level
route_mode = {
    1: "worst_case",     # Priority 1: most RELIABLE route
    2: "balanced",       # Priority 2: half-way
    3: "average",        # Priority 3: fastest AVERAGE route
}

priority_names = {
    1: "PRIORITY 1 - life-threatening",
    2: "PRIORITY 2 - urgent",
    3: "PRIORITY 3 - not urgent",
}


def triage(answers):
    """answers is a dictionary: key -> True (yes) or False (no).
    Returns (emergency_type, priority, why).
    why is a list of short reasons for the priority."""
    why = []

    # 1. what kind of hospital care is needed?
    if answers["injury"] or answers["bleeding"]:
        emergency_type = "accident"
    elif answers["stroke_signs"]:
        emergency_type = "stroke"
    elif answers["chest_pain"] or not answers["conscious"] or not answers["breathing"]:
        emergency_type = "cardiac"
    else:
        emergency_type = "minor"

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
        priority = 1
    elif answers["injury"]:
        priority = 2
        why.append("injury, but awake and breathing")
    else:
        priority = 3
        why.append("no danger signs")
    return emergency_type, priority, why


def smart_dispatch(place, emergency_type, priority, clock):
    """Pick the ambulance, route and hospital.
    Returns (plan, reasons).
      plan    = a dictionary, or None if no ambulance is free
      reasons = a list of text lines explaining the decision"""
    mode = route_mode[priority]

    reasons = []
    reasons.append("Checking free ambulances (" + mode + " time, "
                   + get_period(clock) + " traffic):")
    best_ambulance = None
    best_cost = None
    best_average = None
    best_route1 = []
    for name in ambulances:
        if name in busy:
            reasons.append("   " + name + " : busy")
            continue
        cost, route = find_route(ambulances[name], place, clock, mode, blocked)
        if cost is None:
            reasons.append("   " + name + " : no open road to the patient")
            continue
        average, worst = measure_route(route, clock)
        reasons.append("   " + name + " at " + ambulances[name] + " : " + str(cost)
                       + " min (average " + str(average) + ")")
        # lowest cost wins; if two are tied, the faster average wins
        if best_cost is None or cost < best_cost or (cost == best_cost and average < best_average):
            best_ambulance, best_cost, best_route1 = name, cost, route
            best_average = average

    if best_ambulance is None:
        return None, reasons

    average1, worst1 = measure_route(best_route1, clock)
    leave_clock = clock + average1 + SCENE_TIME

    needs = required_facilities(emergency_type, priority)
    reasons.append("Checking hospitals (needs " + ", ".join(needs) + " and a free bed):")
    best_hospital = None
    best_score = None
    best_route2 = []
    for name in hospitals:
        missing = missing_for(name, emergency_type, priority)
        if len(missing) > 0:
            reasons.append("   " + name + " : rejected (" + ", ".join(missing) + ")")
            continue
        cost, route = find_route(place, hospitals[name]["at"], leave_clock, mode, blocked)
        if cost is None:
            continue
        score = cost + hospitals[name]["wait"]
        reasons.append("   " + name + " : travel " + str(cost) + " + wait "
                       + str(hospitals[name]["wait"]) + " = " + str(score) + " min")
        if best_score is None or score < best_score:
            best_hospital, best_score, best_route2 = name, score, route

    plan = {
        "ambulance": best_ambulance,
        "route1": best_route1,
        "average": average1,
        "worst": worst1,
        "hospital": best_hospital,
        "route2": best_route2,
    }
    return plan, reasons


def commit_dispatch(plan):
    """Update the control room after an ambulance is sent:
    the ambulance becomes busy and the hospital loses one free bed."""
    busy.add(plan["ambulance"])
    if plan["hospital"] is not None:
        hospital = hospitals[plan["hospital"]]
        hospital["beds_free"] = hospital["beds_free"] - 1
        # when the job is over the ambulance will be at the hospital
        ambulances[plan["ambulance"]] = hospital["at"]


# ---------------------------------------------------------------------
# PART 5: BUILDING THE CITY (the fixed one, or a random one)
# ---------------------------------------------------------------------
city_info = {"kind": "default", "seed": None}


def put_roads_on_grid(names, bundles):
    """Place the junction names on the grid slots and the road bundles
    on the grid edges. names[i] goes in slot i, bundles[i] on edge i.
    Everything is changed IN PLACE, so other files see the change."""
    roads.clear()
    places[:] = names
    slot_of.clear()
    for slot in range(len(names)):
        slot_of[names[slot]] = (slot // GRID, slot % GRID)
    edge_number = 0
    for slot_a, slot_b in grid_edges:
        for name, km, night, day, rush in bundles[edge_number]:
            add_road(names[slot_a], names[slot_b], name, km, night, day, rush)
        edge_number = edge_number + 1


def reset_control_room():
    """All ambulances free at their start junctions, no blocked roads."""
    busy.clear()
    blocked.clear()
    ambulances.clear()
    ambulances.update(start_ambulances)


def make_default_hospitals():
    return {
        "Majestic General": {"at": "Majestic", "beds_free": 2, "wait": 10,
                             "facilities": {"general", "trauma_unit", "blood_bank"}},
        "Manyata Heart": {"at": "Manyata Tech Park", "beds_free": 5, "wait": 5,
                          "facilities": {"general", "cath_lab", "stroke_unit",
                                         "icu", "ct_scan"}},
        "University Clinic": {"at": "Bangalore University", "beds_free": 0, "wait": 20,
                              "facilities": {"general"}},
        "Koramangala Trauma": {"at": "Koramangala", "beds_free": 4, "wait": 8,
                               "facilities": {"general", "trauma_unit", "blood_bank"}},
        "Jayanagar Medical": {"at": "Jayanagar", "beds_free": 3, "wait": 15,
                              "facilities": {"general", "cath_lab", "stroke_unit",
                                             "icu", "ct_scan"}},
    }


def default_city():
    """The fixed city (the same every time)."""
    put_roads_on_grid(default_names, default_bundles)
    hospitals.clear()
    hospitals.update(make_default_hospitals())
    reset_control_room()
    city_info["kind"] = "default"
    city_info["seed"] = None


random_hospital_names = ["Alpha Hospital", "Bravo Hospital", "Charlie Hospital",
                         "Delta Hospital", "Echo Hospital"]


def every_case_covered():
    """True if, for every kind of emergency, at least one hospital can
    treat it (using the most demanding version, priority 1) and has at
    least 2 free beds. Without this a random city could have no hospital
    for some emergencies. (Hospitals can still fill up as calls come in,
    and then the dispatcher says that no hospital can treat the case.)"""
    for emergency_type in ["cardiac", "stroke", "accident", "minor"]:
        found = False
        for name in hospitals:
            # at least 2 free beds, so the first emergency does not
            # use up the only bed
            if hospital_can_treat(name, emergency_type, 1) and hospitals[name]["beds_free"] >= 2:
                found = True
        if not found:
            return False
    return True


def make_random_hospitals(rng):
    """Random places, beds, waiting times and facilities."""
    for attempt in range(1000):
        hospitals.clear()
        spots = rng.sample(places, len(random_hospital_names))    # all different
        number = 0
        for name in random_hospital_names:
            facilities = {"general"}
            for facility in extra_facilities:
                if rng.random() < 0.5:           # a coin flip for each facility
                    facilities.add(facility)
            hospitals[name] = {"at": spots[number], "beds_free": rng.randint(0, 6),
                               "wait": rng.randint(5, 20), "facilities": facilities}
            number = number + 1
        if every_case_covered():
            return
    # (practically never reached) give the first hospital everything
    first = random_hospital_names[0]
    hospitals[first]["facilities"] = set(extra_facilities) | {"general"}
    hospitals[first]["beds_free"] = 3


def random_city(seed):
    """A random city. The same seed always gives the same city."""
    rng = random.Random(seed)
    names = default_names[:]           # a copy of the list
    rng.shuffle(names)                 # names go to different grid slots
    bundles = default_bundles[:]
    rng.shuffle(bundles)               # roads go to different grid edges
    put_roads_on_grid(names, bundles)
    make_random_hospitals(rng)
    reset_control_room()
    city_info["kind"] = "random"
    city_info["seed"] = seed


def new_seed():
    """A fresh seed number (different every time the program runs)."""
    return random.randrange(1000, 10000)


def describe_city():
    if city_info["kind"] == "default":
        return "fixed default city"
    return "random city, seed " + str(city_info["seed"])


def start_city():
    """Choose the city when a program starts, from the command line:
         python map_112.py          -> a NEW random city every run
         python map_112.py 4821     -> replay the random city with seed 4821
         python map_112.py default  -> the fixed city"""
    arguments = sys.argv
    if len(arguments) > 1 and arguments[1] == "default":
        default_city()
    elif len(arguments) > 1 and arguments[1].isdigit():
        random_city(int(arguments[1]))
    else:
        random_city(new_seed())


# any program that imports this file starts with the fixed city;
# map_112.py and dispatch_112.py then call start_city() to change it
default_city()
