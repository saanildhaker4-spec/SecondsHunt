# =====================================================================
#  MAP DATA - loads the Jayanagar map and the hospital survey
# =====================================================================
#  Everything the program knows lives in one dictionary called the
#  "world". The other modules take the world as their first argument.
#
#  world["junctions"]  {name: {"lat": ..., "lng": ...}}
#  world["roads"]      {road id: road}
#  world["between"]    {(junction a, junction b): [roads between them]}
#                      (a < b). Two or more roads in a list = PARALLEL
#                      roads, which is what makes this a multigraph.
#  world["hospitals"]  {name: {...}}  real places, SAMPLE beds/facilities
#  world["ambulances"] {name: {"base", "at", "busy", "job"}}
#  world["blocked"]    set of road ids that are closed
#  world["log"]        list of the calls handled
#
#  A road is a dictionary:
#     {"id", "a", "b", "name", "class", "km",
#      "times": {"night": (average, extra), "day": ..., "rush": ...},
#      "shape": [[lat, lng], ...]}
#  "average" is the usual travel time in minutes, "extra" is how much
#  longer it can take. The worst case is average + extra.
# =====================================================================

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
MAP_FILE = os.path.join(DATA_DIR, "jayanagar.json")
SURVEY_FILE = os.path.join(DATA_DIR, "survey.json")

PERIODS = ["night", "day", "rush"]


def load_world(map_file=MAP_FILE, survey_file=SURVEY_FILE):
    """Read the map and the survey files and build the world."""
    with open(map_file, encoding="utf-8") as file:
        data = json.load(file)
    with open(survey_file, encoding="utf-8") as file:
        survey = json.load(file)

    world = {
        "area": data["area"],
        "attribution": data["attribution"],
        "notes": data["notes"],
        "bbox": data["bbox"],
        "junctions": {},
        "roads": {},
        "between": {},
        "hospitals": {},
        "ambulances": {},
        "blocked": set(),
        "log": [],
        "sample_survey": bool(survey.get("sample", False)),
        "survey_note": survey.get("note", ""),
    }

    for junction in data["junctions"]:
        world["junctions"][junction["name"]] = {"lat": junction["lat"], "lng": junction["lng"]}

    for road in data["roads"]:
        road["times"] = {period: tuple(road["times"][period]) for period in PERIODS}
        world["roads"][road["id"]] = road
        key = (road["a"], road["b"]) if road["a"] < road["b"] else (road["b"], road["a"])
        world["between"].setdefault(key, []).append(road)

    for hospital in data["hospitals"]:
        details = survey["hospitals"].get(hospital["name"], {})
        world["hospitals"][hospital["name"]] = {
            "lat": hospital["lat"],
            "lng": hospital["lng"],
            "junction": hospital["junction"],
            "access_m": hospital["access_m"],
            "osm": hospital["osm"],
            "beds_survey": details.get("beds_free", 0),     # the surveyed number of free beds
            "beds_free": details.get("beds_free", 0),       # goes down as patients arrive
            "wait": details.get("wait", 15),
            "facilities": set(details.get("facilities", ["general"])),
        }

    for ambulance in survey["ambulances"]:
        base = ambulance["base"]
        if base not in world["junctions"]:
            raise ValueError("Ambulance base is not a junction: " + base)
        world["ambulances"][ambulance["name"]] = {
            "base": base, "at": base, "busy": False, "job": None}
    return world


def reset_world(world):
    """Back to the start: every ambulance free at its base, every road
    open, every hospital back to its surveyed number of beds."""
    world["blocked"].clear()
    world["log"].clear()
    for ambulance in world["ambulances"].values():
        ambulance["at"] = ambulance["base"]
        ambulance["busy"] = False
        ambulance["job"] = None
    for hospital in world["hospitals"].values():
        hospital["beds_free"] = hospital["beds_survey"]


def roads_list(world):
    """Every road once, sorted by junction names and road name."""
    return sorted(world["roads"].values(), key=lambda road: (road["a"], road["b"], road["name"]))
