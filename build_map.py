# =====================================================================
#  BUILD MAP - turns OpenStreetMap data for JAYANAGAR (Bangalore) into
#  the files the ambulance dispatch app uses
# =====================================================================
#  The app already ships with the finished data files, so you only need
#  this script if you want to rebuild them (it needs the internet and
#  takes a minute or two):
#
#       python build_map.py
#
#  It does these things:
#   1. Downloads the roads and the hospitals of the Jayanagar area from
#      OpenStreetMap (saved in the folder osm_cache for the next run).
#   2. Picks about 30 busy intersections to be the JUNCTIONS and names
#      each one after the two biggest roads that meet there.
#   3. Joins two junctions with a road when the shortest road path
#      between them does not pass through a third junction.
#   4. Looks for a second, genuinely different road between the same
#      two junctions. Two roads between the same junctions is what makes
#      the road network a MULTIGRAPH.
#   5. Writes data/jayanagar.json (the map), and, only if it does not
#      exist yet, data/survey.json (sample hospital beds and facilities,
#      and the ambulance stations, which you can edit).
#
#  WHAT IS REAL AND WHAT IS NOT
#   Real     : junction positions, road shapes, road names, road
#              lengths, and the names and positions of the hospitals.
#   Modelled : travel times (OpenStreetMap has no traffic data). They
#              come from road class, length and the time of day.
#   Ignored  : one-way streets (every road is treated as two-way).
#   Sample   : hospital beds, waiting times, facilities and ambulance
#              stations in data/survey.json are SAMPLE values.
#
#  Map data (c) OpenStreetMap contributors, available under the Open
#  Database License (ODbL): https://www.openstreetmap.org/copyright
# =====================================================================

import hashlib
import heapq
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "osm_cache")
DATA_DIR = os.path.join(HERE, "data")
MAP_FILE = os.path.join(DATA_DIR, "jayanagar.json")
SURVEY_FILE = os.path.join(DATA_DIR, "survey.json")

# south, west, north, east: the Jayanagar area of South Bangalore
BBOX = (12.908, 77.570, 12.945, 77.604)

CLASSES = ["trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
           "living_street", "trunk_link", "primary_link", "secondary_link", "tertiary_link"]

# how important a road class is (used to choose the junctions)
IMPORTANCE = {"trunk": 6, "primary": 5, "secondary": 4, "tertiary": 3,
              "unclassified": 2, "residential": 1, "living_street": 1}
# free-flow speed in km/h (an assumption)
SPEED = {"trunk": 45, "primary": 35, "secondary": 30, "tertiary": 25,
         "unclassified": 22, "residential": 20, "living_street": 10}
# how much slower rush hour is and how unpredictable it is (a model, not data)
RUSH_FACTOR = {"trunk": 2.2, "primary": 2.2, "secondary": 1.8, "tertiary": 1.5,
               "unclassified": 1.3, "residential": 1.2, "living_street": 1.0}
RUSH_RISK = {"trunk": 0.35, "primary": 0.30, "secondary": 0.18, "tertiary": 0.10,
             "unclassified": 0.08, "residential": 0.06, "living_street": 0.0}

MAX_JUNCTIONS = 32
MIN_GAP_M = 420              # junctions are at least this far apart
MAX_PARALLEL = 14            # at most this many links get a second road
HOSPITAL_MAX_DISTANCE_M = 900

# OpenStreetMap lists every clinic, eye hospital and dental centre as a
# "hospital", but an ambulance should take an emergency to a hospital
# that treats emergencies. We keep a hospital if OpenStreetMap marks it
# emergency=yes, or if its name looks like a general / multi-speciality /
# trauma / heart hospital, and we drop names that are clearly something
# else (eye, dental, maternity, ayurveda, clinics and so on).
EXCLUDE_NAMES = re.compile(
    "eye|dental|ayurved|unani|nature ?cure|physio|fertility|diagnost|clinic|maternity|kidney|"
    "cancer|oncology|psychiatr|rehabilitation|vaidya|tuberculosis|research|screening|opd|"
    "nethra|netradhama|vasan|sunayana|tirumalai|liver|orthopaedic|mr-pet|dia centre|department|"
    "block$|^hospital complex$", re.I)
# hospitals whose OpenStreetMap speciality says they do not treat general emergencies
EXCLUDE_SPECIALITY = re.compile("gynec|obstet|ophthal|dental|fertility|physio|dermat", re.I)
INCLUDE_NAMES = re.compile(
    "general|multi ?speciali|speciali|trauma|accident|heart|cardio|institute|esi hospital|"
    "medical|emergency|hospital complex|nursing home|hospitals", re.I)

SERVERS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter"]

# what a hospital can have (every hospital has "general")
FACILITIES = ["trauma_unit", "cath_lab", "stroke_unit", "icu", "blood_bank", "ct_scan"]
# what each kind of emergency needs (the app has the same table in ambulance/triage.py)
NEEDS = {"cardiac": ["cath_lab", "icu"], "stroke": ["stroke_unit", "ct_scan"],
         "accident": ["trauma_unit", "blood_bank"], "minor": ["general"]}


# ---------------------------------------------------------------------
# PART 1: DOWNLOAD FROM OPENSTREETMAP
# ---------------------------------------------------------------------
def download(name, query):
    """Run an Overpass query once and keep the answer in osm_cache."""
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path):
        print("Using the saved download:", name)
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    os.makedirs(CACHE_DIR, exist_ok=True)
    for attempt in range(6):
        server = SERVERS[attempt % len(SERVERS)]
        print("Downloading", name, "from OpenStreetMap (attempt " + str(attempt + 1) + ")...")
        try:
            request = urllib.request.Request(
                server, data=urllib.parse.urlencode({"data": query}).encode(),
                headers={"User-Agent": "JayanagarAmbulanceDispatch/1.0"})
            started = time.time()
            with urllib.request.urlopen(request, timeout=200) as response:
                data = response.read()
            parsed = json.loads(data)
            print("  got", len(data) // 1000, "KB in", round(time.time() - started), "seconds")
            with open(path, "wb") as file:
                file.write(data)
            return parsed
        except Exception as error:
            print("  failed:", type(error).__name__, str(error)[:70])
            time.sleep(10)
    print("Could not download", name, "- try again in a few minutes.")
    sys.exit(1)


def box_text():
    return ",".join(str(x) for x in BBOX)


# ---------------------------------------------------------------------
# PART 2: A ROAD GRAPH
# ---------------------------------------------------------------------
def metres(lat1, lng1, lat2, lng2):
    """Distance in metres between two points (good enough for a city)."""
    dy = (lat2 - lat1) * 110574
    dx = (lng2 - lng1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dx * dx + dy * dy)


nodes = {}          # point id -> (latitude, longitude)
signals = set()     # points with a traffic signal (real, from OpenStreetMap)
calming = set()     # points with a speed bump, hump or table (real)
graph = {}          # point id -> list of (neighbour id, length in metres, way number)
ways = []           # one dictionary per road: {"class", "name"}


def clean_name(tags):
    """A short English-looking road name, or '' if there is none."""
    for key in ["name:en", "name", "ref"]:
        text = tags.get(key, "")
        if text != "" and text.isascii():
            text = text.split(";")[0].strip()
            return text.replace("Road", "Rd").replace("Street", "St")
    return ""


def load_graph(elements):
    for element in elements:
        if element["type"] == "node":
            nodes[element["id"]] = (element["lat"], element["lon"])
            tags = element.get("tags", {})
            if tags.get("highway") == "traffic_signals":
                signals.add(element["id"])
            if "traffic_calming" in tags:
                calming.add(element["id"])
    for element in elements:
        if element["type"] != "way":
            continue
        tags = element.get("tags", {})
        way_class = tags.get("highway", "").replace("_link", "")
        if way_class not in SPEED:
            continue
        ways.append({"class": way_class, "name": clean_name(tags)})
        way_number = len(ways) - 1
        ids = [n for n in element["nodes"] if n in nodes]
        for i in range(len(ids) - 1):
            a, b = ids[i], ids[i + 1]
            length = metres(nodes[a][0], nodes[a][1], nodes[b][0], nodes[b][1])
            graph.setdefault(a, []).append((b, length, way_number))
            graph.setdefault(b, []).append((a, length, way_number))
    print("Road graph:", len(graph), "points,", len(ways), "roads")


def edge_key(a, b):
    return (a, b) if a < b else (b, a)


def shortest_path(start, goal, penalty, limit_m):
    """Dijkstra on the raw OpenStreetMap graph. `penalty` makes some road
    pieces more expensive (used to find a different second road)."""
    best = {start: 0.0}
    came_from = {}
    queue = [(0.0, start)]
    while queue:
        cost, here = heapq.heappop(queue)
        if here == goal:
            path = [goal]
            while path[-1] != start:
                path.append(came_from[path[-1]])
            path.reverse()
            return path
        if cost > best.get(here, 1e18) or cost > limit_m:
            continue
        for neighbour, length, way_number in graph.get(here, []):
            new_cost = cost + length * penalty.get(edge_key(here, neighbour), 1.0)
            if new_cost < best.get(neighbour, 1e18):
                best[neighbour] = new_cost
                came_from[neighbour] = here
                heapq.heappush(queue, (new_cost, neighbour))
    return None


def path_pieces(path):
    pieces = []
    for i in range(len(path) - 1):
        for neighbour, length, way_number in graph[path[i]]:
            if neighbour == path[i + 1]:
                pieces.append((length, way_number))
                break
    return pieces


def path_length(path):
    return sum(length for length, way_number in path_pieces(path))


# ---------------------------------------------------------------------
# PART 3: THE JUNCTIONS
# ---------------------------------------------------------------------
def roads_at(node):
    """{road name: importance} of the named roads that meet at a point."""
    found = {}
    for neighbour, length, way_number in graph[node]:
        label = ways[way_number]["name"]
        if label != "":
            importance = IMPORTANCE[ways[way_number]["class"]]
            if importance > found.get(label, 0):
                found[label] = importance
    return found


def same_road(first, second):
    """True if two names are probably the same road written differently
    (for example '30 Cross Rd' and '30th Cross Rd')."""
    def simple(text):
        text = re.sub("(?<=[0-9])(st|nd|rd|th)", "", text.lower())
        return "".join(ch for ch in text if ch.isalnum())
    a = simple(first)
    b = simple(second)
    return a == b or (len(a) >= 6 and len(b) >= 6 and (a.startswith(b) or b.startswith(a)))


def distinct_roads(here):
    """The names at a junction, biggest road first, without repeats."""
    result = []
    for label in sorted(here, key=lambda label: (-here[label], label)):
        if not any(same_road(label, other) for other in result):
            result.append(label)
    return result


def choose_junctions():
    """The busiest intersections, at least MIN_GAP_M apart.
    Returns {junction name: point id}."""
    scored = []
    for node in graph:
        neighbours = set(n for n, l, w in graph[node])
        here = roads_at(node)
        if len(neighbours) >= 3 and len(distinct_roads(here)) >= 2:
            score = sum(here.values()) + (2 if len(neighbours) >= 4 else 0)
            scored.append((-score, node))
    scored.sort()
    chosen = []
    for negative_score, node in scored:
        lat, lng = nodes[node]
        if all(metres(lat, lng, nodes[c][0], nodes[c][1]) >= MIN_GAP_M for c in chosen):
            chosen.append(node)
        if len(chosen) >= MAX_JUNCTIONS:
            break
    result = {}
    for node in chosen:
        top = distinct_roads(roads_at(node))[:2]
        name = top[0] + " & " + top[1]
        number = 2
        while name in result:
            name = top[0] + " & " + top[1] + " (" + str(number) + ")"
            number = number + 1
        result[name] = node
    return result


# ---------------------------------------------------------------------
# PART 4: ROADS BETWEEN JUNCTIONS, PARALLEL ROADS, MODELLED TIMES
# ---------------------------------------------------------------------
def road_name_of(path):
    """The road that covers most of the length of a path."""
    totals = {}
    for length, way_number in path_pieces(path):
        label = ways[way_number]["name"]
        if label == "":
            label = "unnamed " + ways[way_number]["class"] + " road"
        totals[label] = totals.get(label, 0) + length
    return max(totals, key=totals.get)


def road_class_of(path):
    """The class of road that covers most of the length of a path."""
    totals = {}
    for length, way_number in path_pieces(path):
        way_class = ways[way_number]["class"]
        totals[way_class] = totals.get(way_class, 0) + length
    return max(totals, key=totals.get)


def is_far_from(second, first, minimum_m):
    """True if the middle of path `second` stays at least minimum_m
    metres away from path `first`. (OpenStreetMap draws a divided road
    as two roads side by side; those do not count as parallel roads.)"""
    start = len(second) // 3
    end = len(second) - len(second) // 3
    for node in second[start:end]:
        nearest = min(metres(nodes[node][0], nodes[node][1], nodes[other][0], nodes[other][1])
                      for other in first)
        if nearest < minimum_m:
            return False
    return True


def sample_shape(path):
    """A short list of [lat, lng] points that keeps the shape of the path."""
    shape = []
    last = None
    for node in path:
        point = nodes[node]
        if last is None or metres(last[0], last[1], point[0], point[1]) > 40:
            shape.append([round(point[0], 5), round(point[1], 5)])
            last = point
    end = nodes[path[-1]]
    if shape[-1] != [round(end[0], 5), round(end[1], 5)]:
        shape.append([round(end[0], 5), round(end[1], 5)])
    return shape


# Extra delay for each REAL traffic signal on a road (OpenStreetMap marks
# them) and each speed bump: [night, day, rush] usual minutes, and the
# extra minutes it can add. These numbers are assumptions, not measurements.
SIGNAL_DELAY = {"night": (0.1, 0.0), "day": (0.4, 0.4), "rush": (1.0, 1.2)}
BUMP_DELAY = 0.1


def time_model(path):
    """Modelled minutes [average, extra] for night, day and rush hour.
    average = the usual time; extra = how much longer it can take.
    The time comes from the road class and length, plus a delay for every
    traffic signal and speed bump on the road."""
    night = 0.0
    day_extra = 0.0
    rush = 0.0
    rush_extra = 0.0
    for length, way_number in path_pieces(path):
        way_class = ways[way_number]["class"]
        free = length / 1000.0 / SPEED[way_class] * 60.0          # minutes at free flow
        night += free
        rush += free * RUSH_FACTOR[way_class]
        rush_extra += free * RUSH_FACTOR[way_class] * RUSH_RISK[way_class]
        day_extra += free * 0.15
    day = night * 1.3

    lights = sum(1 for point in path if point in signals)
    bumps = sum(1 for point in path if point in calming)
    night += lights * SIGNAL_DELAY["night"][0] + bumps * BUMP_DELAY
    day += lights * SIGNAL_DELAY["day"][0] + bumps * BUMP_DELAY
    rush += lights * SIGNAL_DELAY["rush"][0] + bumps * BUMP_DELAY
    day_extra += lights * SIGNAL_DELAY["day"][1]
    rush_extra += lights * SIGNAL_DELAY["rush"][1]

    def tidy(average, extra):
        return [max(0.5, round(average, 1)), round(extra, 1)]
    return {"night": tidy(night, 0.0), "day": tidy(day, day_extra), "rush": tidy(rush, rush_extra)}


def make_road(a, b, path):
    name = road_name_of(path)
    return {"id": a + "|" + b + "|" + name, "a": a, "b": b, "name": name,
            "class": road_class_of(path), "km": round(path_length(path) / 1000.0, 2),
            "signals": sum(1 for point in path if point in signals),
            "times": time_model(path), "shape": sample_shape(path)}


def build_roads(junction_node):
    node_name = {node: name for name, node in junction_node.items()}
    names = sorted(junction_node)

    # 1. links: the shortest road path must not pass through a third junction
    links = {}
    for name_a in names:
        found = []
        for name_b in names:
            if name_a == name_b:
                continue
            path = shortest_path(junction_node[name_a], junction_node[name_b], {}, 3000)
            if path is None or any(point in node_name for point in path[1:-1]):
                continue
            found.append((path_length(path), name_a, name_b, path))
        found.sort(key=lambda item: item[0])
        for length, a, b, path in found[:3]:
            if a < b:
                links[(a, b)] = path
            else:
                links[(b, a)] = list(reversed(path))

    # 2. make sure every junction can be reached from every other one
    def groups_of_junctions():
        parent = {name: name for name in names}

        def root(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for a, b in links:
            parent[root(a)] = root(b)
        groups = {}
        for name in names:
            groups.setdefault(root(name), []).append(name)
        return list(groups.values())

    while len(groups_of_junctions()) > 1:
        groups = groups_of_junctions()
        best = None
        for a in groups[0]:
            for b in [n for g in groups[1:] for n in g]:
                path = shortest_path(junction_node[a], junction_node[b], {}, 8000)
                if path is not None:
                    length = path_length(path)
                    if best is None or length < best[0]:
                        best = (length, a, b, path)
        if best is None:
            print("ERROR: the junctions cannot all be joined by road")
            sys.exit(1)
        if best[1] < best[2]:
            links[(best[1], best[2])] = best[3]
        else:
            links[(best[2], best[1])] = list(reversed(best[3]))

    # 3. a second, different road for each link, where one exists
    roads = []
    candidates = []
    for (a, b), path in sorted(links.items()):
        first = make_road(a, b, path)
        roads.append(first)
        penalty = {edge_key(path[i], path[i + 1]): 6.0 for i in range(len(path) - 1)}
        second = shortest_path(junction_node[a], junction_node[b], penalty, 6000)
        if second is None or second == path or any(point in node_name for point in second[1:-1]):
            continue
        first_edges = set(edge_key(path[i], path[i + 1]) for i in range(len(path) - 1))
        overlap = 0.0
        for i in range(len(second) - 1):
            if edge_key(second[i], second[i + 1]) in first_edges:
                for neighbour, length, way_number in graph[second[i]]:
                    if neighbour == second[i + 1]:
                        overlap += length
                        break
        second_length = path_length(second)
        if second_length <= 1.6 * path_length(path) and overlap <= 0.3 * second_length \
                and road_name_of(second) != first["name"] and is_far_from(second, path, 60):
            candidates.append((overlap / second_length, second_length / path_length(path),
                               make_road(a, b, second)))
    candidates.sort(key=lambda item: (item[0], item[1]))        # the most different roads first
    for overlap, ratio, road in candidates[:MAX_PARALLEL]:
        roads.append(road)
    return roads, min(len(candidates), MAX_PARALLEL)


# ---------------------------------------------------------------------
# PART 5: HOSPITALS AND THE SAMPLE SURVEY
# ---------------------------------------------------------------------
def build_hospitals(junctions):
    """Real hospitals (OpenStreetMap) near the junctions."""
    query = ('[out:json][timeout:60];nwr["amenity"="hospital"](' + box_text() + ');out center;')
    elements = download("jayanagar_hospitals.json", query)["elements"]
    found = []
    seen = set()
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name:en", tags.get("name", "")).strip()
        name = name.replace("Emergency Block , NIMHANS", "NIMHANS Emergency Block")
        if name == "" or not name.isascii() or name in seen:
            continue
        emergency = tags.get("emergency") == "yes"
        if EXCLUDE_NAMES.search(name) and not name.startswith("NIMHANS Emergency"):
            continue
        if EXCLUDE_SPECIALITY.search(tags.get("healthcare:speciality", "")):
            continue
        if not emergency and not INCLUDE_NAMES.search(name):
            continue
        if "lat" in element:
            lat, lng = element["lat"], element["lon"]
        else:
            lat, lng = element["center"]["lat"], element["center"]["lon"]
        best, best_distance = None, 1e18
        for junction in junctions:
            distance = metres(lat, lng, junction["lat"], junction["lng"])
            if distance < best_distance:
                best, best_distance = junction["name"], distance
        if best_distance <= HOSPITAL_MAX_DISTANCE_M:
            seen.add(name)
            found.append({"name": name, "osm": element["type"] + "/" + str(element["id"]),
                          "lat": round(lat, 5), "lng": round(lng, 5), "junction": best,
                          "access_m": round(best_distance), "emergency": emergency,
                          "speciality": tags.get("healthcare:speciality", "")})
    found.sort(key=lambda hospital: hospital["name"])
    return found


def number_from(text, low, high):
    """A repeatable pseudo-random number in [low, high] made from a text."""
    digest = hashlib.sha256(text.encode()).hexdigest()
    return low + int(digest[:8], 16) % (high - low + 1)


def facilities_from_name(text):
    """A guess at a hospital's facilities from its name and OpenStreetMap
    speciality (for example a trauma hospital has a trauma unit)."""
    text = text.lower()
    found = []
    if "trauma" in text or "accident" in text:
        found = ["trauma_unit", "blood_bank", "icu", "ct_scan"]
    if "cardio" in text or "heart" in text or "jayadeva" in text or "cardiac" in text:
        found = found + ["cath_lab", "icu"]
    if "nimhans" in text or "neuro" in text:
        found = found + ["stroke_unit", "ct_scan", "icu"]
    return found


def make_sample_survey(hospitals, junctions):
    """SAMPLE beds, waiting times and facilities, and ambulance stations.
    Repeatable: the same hospital always gets the same sample values."""
    survey_hospitals = {}
    for hospital in hospitals:
        name = hospital["name"]
        facilities = ["general"] + facilities_from_name(name + " " + hospital["speciality"])
        for facility in FACILITIES:
            if facility not in facilities and number_from(name + facility, 0, 99) < 35:
                facilities.append(facility)
        survey_hospitals[name] = {"beds_free": number_from(name + "beds", 0, 6),
                                  "wait": number_from(name + "wait", 5, 20),
                                  "facilities": facilities}
    # every kind of emergency must have at least one hospital that can treat it
    names = sorted(survey_hospitals)
    for need in NEEDS.values():
        capable = [n for n in names if all(f in survey_hospitals[n]["facilities"] for f in need)
                   and survey_hospitals[n]["beds_free"] >= 2]
        if len(capable) == 0 and len(names) > 0:
            chosen = names[number_from("".join(need), 0, len(names) - 1)]
            for facility in need:
                if facility not in survey_hospitals[chosen]["facilities"]:
                    survey_hospitals[chosen]["facilities"].append(facility)
            survey_hospitals[chosen]["beds_free"] = max(3, survey_hospitals[chosen]["beds_free"])

    # ambulance stations: junctions spread over the area (farthest-point choice)
    chosen = [junctions[0]]
    while len(chosen) < 6 and len(chosen) < len(junctions):
        best, best_distance = None, -1
        for junction in junctions:
            distance = min(metres(junction["lat"], junction["lng"], c["lat"], c["lng"]) for c in chosen)
            if distance > best_distance:
                best, best_distance = junction, distance
        chosen.append(best)
    ambulances = [{"name": "Ambulance " + str(i + 1), "base": junction["name"]}
                  for i, junction in enumerate(chosen)]
    return {"note": "SAMPLE data. Facilities are a guess from each hospital's name (for example a "
                    "trauma hospital gets a trauma unit); beds and waiting times are random. "
                    "Replace them with a real survey of each hospital, and the stations with the "
                    "real ambulance bases.",
            "sample": True, "hospitals": survey_hospitals, "ambulances": ambulances}


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def build():
    query = ('[out:json][timeout:150][maxsize:536870912];'
             'way["highway"~"^(' + "|".join(CLASSES) + ')$"](' + box_text() + ');'
             '(._;>;);out body qt;')
    load_graph(download("jayanagar_roads.json", query)["elements"])

    junction_node = choose_junctions()
    names = sorted(junction_node)
    print(len(names), "junctions chosen")
    roads, parallel = build_roads(junction_node)
    print(len(roads), "roads between the junctions,", parallel, "of them parallel to another road")

    junctions = [{"name": name, "lat": nodes[junction_node[name]][0],
                  "lng": nodes[junction_node[name]][1]} for name in names]
    hospitals = build_hospitals(junctions)
    print(len(hospitals), "hospitals found:", ", ".join(h["name"] for h in hospitals))

    os.makedirs(DATA_DIR, exist_ok=True)
    city = {
        "area": "Jayanagar, Bangalore",
        "attribution": "Map data (c) OpenStreetMap contributors, ODbL 1.0, "
                       "https://www.openstreetmap.org/copyright",
        "notes": "Junctions, road shapes, names, lengths and hospitals come from OpenStreetMap. "
                 "Travel times are MODELLED from road class, length and time of day. "
                 "One-way streets are ignored.",
        "bbox": list(BBOX),
        "junctions": junctions,
        "roads": roads,
        "hospitals": hospitals,
    }
    with open(MAP_FILE, "w", encoding="utf-8") as file:
        json.dump(city, file, separators=(",", ":"))
    print("Wrote", MAP_FILE, "-", os.path.getsize(MAP_FILE) // 1000, "KB")

    if os.path.exists(SURVEY_FILE):
        print("Kept your existing", SURVEY_FILE)
    else:
        with open(SURVEY_FILE, "w", encoding="utf-8") as file:
            json.dump(make_sample_survey(hospitals, junctions), file, indent=2)
        print("Wrote a SAMPLE survey:", SURVEY_FILE)


if __name__ == "__main__":
    build()
