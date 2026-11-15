"""Helpers for the tests: a tiny made-up world where every answer can be
worked out by hand.

        A ===== B ----- C
        |               |
        +------ D ------+      (A-D and D-C are a longer way round)

A and B are joined by TWO parallel roads:
    quick   : usual 4 min in rush hour but up to 6 more (worst case 10)
    steady  : usual 7 min in rush hour and only 1 more  (worst case  8)
"""

from ambulance import mapdata


def road(a, b, name, km, rush, day=None, night=None):
    """A road. rush / day / night are (usual minutes, extra minutes)."""
    day = day if day is not None else rush
    night = night if night is not None else rush
    return {"id": a + "|" + b + "|" + name, "a": a, "b": b, "name": name, "class": "tertiary",
            "km": km, "times": {"night": night, "day": day, "rush": rush},
            "shape": [[12.92, 77.58], [12.93, 77.59]]}


def hospital(junction, beds, facilities, wait=10, access_m=100):
    return {"lat": 12.92, "lng": 77.58, "junction": junction, "access_m": access_m, "osm": "node/1",
            "beds_survey": beds, "beds_free": beds, "wait": wait, "facilities": set(facilities)}


def make_world():
    roads = [
        road("A", "B", "quick", 1.0, (4, 6)),
        road("A", "B", "steady", 1.4, (7, 1)),
        road("B", "C", "bc", 1.0, (3, 0)),
        road("A", "D", "ad", 2.0, (6, 0)),
        road("D", "C", "dc", 2.0, (6, 0)),
    ]
    world = {
        "area": "Test", "attribution": "test", "notes": "", "bbox": [12.9, 77.5, 13.0, 77.6],
        "junctions": {name: {"lat": 12.92, "lng": 77.58} for name in "ABCD"},
        "roads": {}, "between": {},
        "hospitals": {
            "Near General": hospital("B", 3, ["general", "trauma_unit"]),
            "Far Heart": hospital("C", 2, ["general", "cath_lab", "icu", "stroke_unit", "ct_scan"]),
        },
        "ambulances": {
            "Ambulance 1": {"base": "A", "at": "A", "busy": False, "job": None},
            "Ambulance 2": {"base": "C", "at": "C", "busy": False, "job": None},
        },
        "blocked": set(), "log": [], "sample_survey": True, "survey_note": "",
    }
    for item in roads:
        world["roads"][item["id"]] = item
        key = (item["a"], item["b"]) if item["a"] < item["b"] else (item["b"], item["a"])
        world["between"].setdefault(key, []).append(item)
    return world


def answers(**changes):
    """The usual answers (a healthy person) with some changes."""
    from ambulance import triage
    result = triage.usual_answers()
    result.update(changes)
    return result


def real_world():
    """The real Jayanagar world (a fresh copy each time)."""
    return mapdata.load_world()
