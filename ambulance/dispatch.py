# =====================================================================
#  DISPATCH - picks the ambulance, the route and the hospital
# =====================================================================
#  For one emergency the dispatcher
#    1. prices the roads by the patient's priority (see triage.py),
#    2. asks routing.py for the route from every free ambulance to the
#       patient and keeps the cheapest,
#    3. keeps only the hospitals that have the facilities the case needs
#       and a free bed, and chooses the one with the lowest
#       travel + waiting time,
#    4. writes down WHY, so the operator can see every decision.
# =====================================================================

import datetime

from ambulance import routing, triage

SCENE_TIME = 5        # minutes the crew spends with the patient
ACCESS_KMH = 20       # speed from a junction to the door of a hospital


# ---------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------
def get_period(minutes):
    """Turn the time of day (minutes after midnight) into a traffic period."""
    hour = (int(minutes) // 60) % 24
    if 8 <= hour < 11 or 17 <= hour < 21:
        return "rush"
    if 6 <= hour < 23:
        return "day"
    return "night"


def show_clock(minutes):
    """Minutes after midnight as text, for example 09:30."""
    hour = (int(minutes) // 60) % 24
    minute = int(minutes) % 60
    return str(hour).rjust(2, "0") + ":" + str(minute).rjust(2, "0")


def now_minutes():
    """The time in Bangalore (UTC+05:30) right now, in minutes after midnight."""
    bangalore = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now = datetime.datetime.now(bangalore)
    return now.hour * 60 + now.minute


# ---------------------------------------------------------------------
# Hospitals
# ---------------------------------------------------------------------
def missing_for(world, hospital_name, care, priority):
    """What stops this hospital from treating the case, as a list of short
    texts. An empty list means the hospital CAN treat it."""
    hospital = world["hospitals"][hospital_name]
    missing = []
    for facility in triage.required_facilities(care, priority):
        if facility not in hospital["facilities"]:
            missing.append("no " + triage.FACILITY_NAMES[facility])
    if hospital["beds_free"] <= 0:
        missing.append("no free bed")
    return missing


def access_minutes(hospital):
    """Minutes from the nearest junction to the door of the hospital."""
    return round(hospital["access_m"] / 1000.0 / ACCESS_KMH * 60.0, 1)


# ---------------------------------------------------------------------
# The old rule, for comparison
# ---------------------------------------------------------------------
def nearest_baseline(world, place, care, priority, period):
    """What a plain 'nearest' rule would do: the free ambulance with the
    fewest kilometres to the patient, and the hospital with the fewest
    kilometres from the patient, ignoring facilities and beds."""
    best_ambulance, best_route = None, None
    for name in sorted(world["ambulances"]):
        ambulance = world["ambulances"][name]
        if ambulance["busy"]:
            continue
        route = routing.find_route(world, ambulance["at"], place, "distance", period)
        if route is not None and (best_route is None or route["km"] < best_route["km"]):
            best_ambulance, best_route = name, route
    best_hospital, hospital_route = None, None
    for name in sorted(world["hospitals"]):
        route = routing.find_route(world, place, world["hospitals"][name]["junction"],
                                   "distance", period)
        if route is not None and (hospital_route is None or route["km"] < hospital_route["km"]):
            best_hospital, hospital_route = name, route
    result = {"ambulance": best_ambulance, "route1": best_route,
              "hospital": best_hospital, "route2": hospital_route, "missing": []}
    if best_hospital is not None:
        result["missing"] = missing_for(world, best_hospital, care, priority)
    if best_route is not None:
        # the time it would REALLY take at this time of day
        result["average"] = sum(road["times"][period][0] for road in best_route["roads"])
        result["worst"] = sum(road["times"][period][0] + road["times"][period][1]
                              for road in best_route["roads"])
        result["average"] = round(result["average"], 1)
        result["worst"] = round(result["worst"], 1)
    return result


# ---------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------
def plan_dispatch(world, place, result, clock):
    """Decide what to do for an emergency at junction `place`.
    `result` is the triage result. `clock` is the time in minutes.
    Returns (plan, reasons). plan is None if no ambulance can reach the
    patient; plan["hospital"] is None if no hospital can treat the case.
    reasons is a list of text lines that explain the decision."""
    care = result["care"]
    priority = result["priority"]
    mode = triage.MODE_FOR_PRIORITY[priority]
    period = get_period(clock)
    reasons = []

    # ---- 1. the ambulance
    reasons.append("Roads priced by " + mode + " time (" + triage.PRIORITY_NAMES[priority].lower()
                   + "), " + period + " traffic.")
    reasons.append("Ambulances:")
    best_ambulance, best_route = None, None
    for name in sorted(world["ambulances"]):
        ambulance = world["ambulances"][name]
        if ambulance["busy"]:
            reasons.append("   " + name + " : busy")
            continue
        route = routing.find_route(world, ambulance["at"], place, mode, period)
        if route is None:
            reasons.append("   " + name + " : no open road to the patient")
            continue
        reasons.append("   " + name + " at " + ambulance["at"] + " : "
                       + str(round(route["cost"], 1)) + " min (usual " + str(route["average"])
                       + ", worst " + str(route["worst"]) + ")")
        if best_route is None or (route["cost"], route["average"]) < (best_route["cost"], best_route["average"]):
            best_ambulance, best_route = name, route
    if best_ambulance is None:
        return None, reasons

    # ---- 2. the hospital
    needs = [triage.FACILITY_NAMES[f] for f in triage.required_facilities(care, priority)]
    reasons.append("Hospitals (need " + ", ".join(needs) + " and a free bed):")
    best_hospital, best_route2, best_score = None, None, None
    for name in sorted(world["hospitals"]):
        hospital = world["hospitals"][name]
        missing = missing_for(world, name, care, priority)
        if len(missing) > 0:
            reasons.append("   " + name + " : rejected (" + ", ".join(missing) + ")")
            continue
        route = routing.find_route(world, place, hospital["junction"], mode, period)
        if route is None:
            reasons.append("   " + name + " : no open road from the patient")
            continue
        score = route["cost"] + access_minutes(hospital) + hospital["wait"]
        reasons.append("   " + name + " : travel " + str(round(route["cost"], 1)) + " + door "
                       + str(access_minutes(hospital)) + " + wait " + str(hospital["wait"])
                       + " = " + str(round(score, 1)) + " min")
        if best_score is None or score < best_score:
            best_hospital, best_route2, best_score = name, route, score

    plan = {
        "place": place, "care": care, "priority": priority, "why": result["why"],
        "mode": mode, "period": period, "clock": clock,
        "ambulance": best_ambulance, "route1": best_route,
        "hospital": best_hospital, "route2": best_route2,
        "needs": triage.required_facilities(care, priority),
    }
    if best_hospital is None:
        reasons.append("   -> NO hospital can treat this case right now.")
    return plan, reasons


def commit_dispatch(world, plan):
    """The ambulance is sent: it becomes busy, the hospital loses one free
    bed, and the call is written in the log. Returns the log entry."""
    ambulance = world["ambulances"][plan["ambulance"]]
    ambulance["busy"] = True
    ambulance["job"] = {"place": plan["place"], "hospital": plan["hospital"]}
    if plan["hospital"] is not None:
        hospital = world["hospitals"][plan["hospital"]]
        hospital["beds_free"] = max(0, hospital["beds_free"] - 1)
    entry = {
        "id": "INC-" + str(len(world["log"]) + 1).rjust(3, "0"),
        "time": show_clock(plan["clock"]),
        "place": plan["place"],
        "care": plan["care"],
        "priority": plan["priority"],
        "ambulance": plan["ambulance"],
        "hospital": plan["hospital"] if plan["hospital"] is not None else "none",
        "minutes_to_patient": plan["route1"]["average"],
        "worst_minutes_to_patient": plan["route1"]["worst"],
    }
    world["log"].append(entry)
    return entry


def finish_job(world, ambulance_name):
    """The ambulance is back in service, at the hospital it went to (or at
    the patient's junction if there was no hospital)."""
    ambulance = world["ambulances"][ambulance_name]
    job = ambulance["job"]
    if job is not None:
        if job["hospital"] is not None:
            ambulance["at"] = world["hospitals"][job["hospital"]]["junction"]
        else:
            ambulance["at"] = job["place"]
    ambulance["busy"] = False
    ambulance["job"] = None
