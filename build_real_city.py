# =====================================================================
#  BUILD REAL CITY - turns OpenStreetMap road data for JAYANAGAR
#  (Bangalore) into a small junction graph the dispatch programs load
# =====================================================================
#  Run this ONCE (it needs the internet and takes a minute or two):
#
#       python build_real_city.py
#
#  It does five things:
#   1. Downloads the roads of the Jayanagar area from OpenStreetMap
#      (saved in the folder osm_cache, so the next run is offline).
#   2. Picks about 30 busy intersections to be the JUNCTIONS and names
#      each one after the two biggest roads that meet there.
#   3. Joins two junctions with a road link when the shortest road
#      path between them does not pass through a third junction.
#   4. Looks for a second, different road between the same two
#      junctions (this makes the PARALLEL roads of our multigraph).
#   5. Writes bangalore_city.json, which map_112.py loads with
#      "python map_112.py real".
#
#  WHAT IS REAL AND WHAT IS NOT
#   Real     : junction positions, road shapes, road names, lengths.
#   Modelled : travel times. OpenStreetMap has no traffic data, so the
#              night / day / rush-hour times come from a simple rule
#              (road class and length). They are NOT measured.
#              (google_traffic.py can replace them with Google's
#              traffic times while the program is running.)
#   Ignored  : one-way streets (every road is treated as two-way).
#
#  Map data (c) OpenStreetMap contributors, available under the
#  Open Database License (ODbL): https://www.openstreetmap.org/copyright
# =====================================================================

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
CACHE_FILE = os.path.join(HERE, "osm_cache", "jayanagar_roads.json")
OUTPUT_FILE = os.path.join(HERE, "bangalore_city.json")

# south, west, north, east: the Jayanagar area of South Bangalore
BBOX = (12.908, 77.570, 12.945, 77.604)

CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
           "residential", "living_street",
           "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"]

# how important a road class is (used to choose junctions)
IMPORTANCE = {"motorway": 6, "trunk": 6, "primary": 5, "secondary": 4, "tertiary": 3,
              "unclassified": 2, "residential": 1, "living_street": 1}
# free-flow speed in km/h for each class of road (an assumption)
SPEED = {"motorway": 60, "trunk": 45, "primary": 35, "secondary": 30, "tertiary": 25,
         "unclassified": 22, "residential": 20, "living_street": 10}
# how much slower rush hour is, and how unpredictable (a model, not data)
RUSH_FACTOR = {"motorway": 2.0, "trunk": 2.2, "primary": 2.2, "secondary": 1.8, "tertiary": 1.5,
               "unclassified": 1.3, "residential": 1.2, "living_street": 1.0}
RUSH_RISK = {"motorway": 0.30, "trunk": 0.35, "primary": 0.30, "secondary": 0.18, "tertiary": 0.10,
             "unclassified": 0.08, "residential": 0.06, "living_street": 0.0}

MAX_JUNCTIONS = 32
MIN_GAP_M = 420              # junctions are at least this far apart
MAX_PARALLEL = 14            # at most this many links get a second road

SERVERS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter"]


# ---------------------------------------------------------------------
# PART 1: DOWNLOAD THE ROADS
# ---------------------------------------------------------------------
def fetch_roads():
    """Download the roads from OpenStreetMap (Overpass API) once."""
    if os.path.exists(CACHE_FILE):
        print("Using the saved download:", CACHE_FILE)
        return
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    query = ('[out:json][timeout:150][maxsize:536870912];'
             'way["highway"~"^(' + "|".join(CLASSES) + ')$"]'
             '(' + ",".join(str(x) for x in BBOX) + ');'
             '(._;>;);out body qt;')
    data = None
    for attempt in range(6):
        server = SERVERS[attempt % len(SERVERS)]
        print("Downloading the roads of Jayanagar from OpenStreetMap (attempt "
              + str(attempt + 1) + ")...")
        try:
            request = urllib.request.Request(
                server, data=urllib.parse.urlencode({"data": query}).encode(),
                headers={"User-Agent": "ZeroHourAmbulanceDemo/1.0"})
            started = time.time()
            with urllib.request.urlopen(request, timeout=200) as response:
                data = response.read()
            json.loads(data)                       # make sure it is complete
            print("  got", len(data) // 1000, "KB in", round(time.time() - started), "seconds")
            break
        except Exception as error:
            data = None
            print("  failed:", type(error).__name__, str(error)[:70])
            time.sleep(10)
    if data is None:
        print("Could not download the roads. Try again in a few minutes.")
        sys.exit(1)
    with open(CACHE_FILE, "wb") as file:
        file.write(data)


# ---------------------------------------------------------------------
# PART 2: MAKE A ROAD GRAPH
# ---------------------------------------------------------------------
def metres(lat1, lng1, lat2, lng2):
    """Distance in metres between two points (good enough for a city)."""
    dy = (lat2 - lat1) * 110574
    dx = (lng2 - lng1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dx * dx + dy * dy)


nodes = {}          # node id -> (latitude, longitude)
graph = {}          # node id -> list of (neighbour id, length in metres, way number)
ways = []           # one dictionary per way: {"class", "name"}


def clean_name(tags):
    """A short English-looking road name, or '' if there is none."""
    for key in ["name:en", "name", "ref"]:
        text = tags.get(key, "")
        if text != "" and text.isascii():
            text = text.split(";")[0].strip()
            text = text.replace("Road", "Rd").replace("Street", "St")
            return text
    return ""


def load_graph():
    with open(CACHE_FILE, encoding="utf-8") as file:
        elements = json.load(file)["elements"]
    for element in elements:
        if element["type"] == "node":
            nodes[element["id"]] = (element["lat"], element["lon"])
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
    """Dijkstra's algorithm on the road graph. `penalty` makes some road
    pieces more expensive (used to find a different second road).
    Returns the list of points from start to goal, or None."""
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
            extra = penalty.get(edge_key(here, neighbour), 1.0)
            new_cost = cost + length * extra
            if new_cost < best.get(neighbour, 1e18):
                best[neighbour] = new_cost
                came_from[neighbour] = here
                heapq.heappush(queue, (new_cost, neighbour))
    return None


def path_pieces(path):
    """The (length, way number) of every piece of a path."""
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
# PART 3: CHOOSE THE JUNCTIONS
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
    """The busiest intersections, at least MIN_GAP_M apart. Returns a
    dictionary: junction name -> OpenStreetMap point."""
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
        here = roads_at(node)
        top = distinct_roads(here)[:2]
        name = top[0] + " & " + top[1]
        number = 2
        while name in result:
            name = top[0] + " & " + top[1] + " (" + str(number) + ")"
            number = number + 1
        result[name] = node
    return result


# ---------------------------------------------------------------------
# PART 4: JOIN THEM, FIND PARALLEL ROADS, MODEL THE TIMES
# ---------------------------------------------------------------------
def is_far_from(second, first, minimum_m):
    """True if the middle part of path `second` stays at least
    minimum_m metres away from path `first`. (OpenStreetMap draws a
    divided road as two roads side by side; those do not count as
    parallel roads.)"""
    start = len(second) // 3
    end = len(second) - len(second) // 3
    for node in second[start:end]:
        nearest = min(metres(nodes[node][0], nodes[node][1], nodes[other][0], nodes[other][1])
                      for other in first)
        if nearest < minimum_m:
            return False
    return True


def road_name_of(path):
    """The road that covers most of the length of a path."""
    totals = {}
    for length, way_number in path_pieces(path):
        label = ways[way_number]["name"]
        if label == "":
            label = "unnamed " + ways[way_number]["class"] + " road"
        totals[label] = totals.get(label, 0) + length
    return max(totals, key=totals.get)


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


def time_model(path):
    """Modelled minutes [average, extra] for night, day and rush hour."""
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

    def tidy(average, extra):
        return [max(0.5, round(average, 1)), round(extra, 1)]
    return {"night": tidy(night, 0.0), "day": tidy(day, day_extra), "rush": tidy(rush, rush_extra)}


def build():
    fetch_roads()
    load_graph()

    junction_node = choose_junctions()
    node_name = {node: name for name, node in junction_node.items()}
    print()
    print(len(junction_node), "junctions chosen:")
    for name in sorted(junction_node):
        print("  ", name)

    # 1. candidate links: the shortest road path must not pass through a third junction
    print()
    print("Joining the junctions...")
    links = {}                       # (name a, name b) -> path (list of points)
    names = sorted(junction_node)
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

    # 2. make sure the junction graph is connected
    def components():
        parent = {name: name for name in junction_node}

        def root(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for a, b in links:
            parent[root(a)] = root(b)
        groups = {}
        for name in junction_node:
            groups.setdefault(root(name), []).append(name)
        return list(groups.values())

    while len(components()) > 1:
        groups = components()
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
        print("  joined two separate groups with", best[1], "-", best[2])
    print("  ", len(links), "road links between", len(junction_node), "junctions")

    # 3. a second, different road for each link, where one exists
    print()
    print("Looking for parallel roads...")
    candidates = []
    edges = []
    for (a, b), path in sorted(links.items()):
        first_length = path_length(path)
        first_name = road_name_of(path)
        first = {"name": first_name, "km": round(first_length / 1000.0, 2),
                 "times": time_model(path), "shape": sample_shape(path), "source": "modelled"}
        edge = {"a": a, "b": b, "options": [first]}
        edges.append(edge)
        penalty = {edge_key(path[i], path[i + 1]): 6.0 for i in range(len(path) - 1)}
        second = shortest_path(junction_node[a], junction_node[b], penalty, 6000)
        if second is None or second == path or any(point in node_name for point in second[1:-1]):
            continue
        second_length = path_length(second)
        first_edges = set(edge_key(path[i], path[i + 1]) for i in range(len(path) - 1))
        overlap = 0.0
        for i in range(len(second) - 1):
            if edge_key(second[i], second[i + 1]) in first_edges:
                for neighbour, length, way_number in graph[second[i]]:
                    if neighbour == second[i + 1]:
                        overlap += length
                        break
        second_name = road_name_of(second)
        if second_length <= 1.6 * first_length and overlap <= 0.3 * second_length                 and second_name != first_name and is_far_from(second, path, 60):
            option = {"name": second_name, "km": round(second_length / 1000.0, 2),
                      "times": time_model(second), "shape": sample_shape(second),
                      "source": "modelled"}
            candidates.append((overlap / second_length, second_length / first_length, edge, option))
    candidates.sort(key=lambda item: (item[0], item[1]))     # the most different roads first
    for overlap, ratio, edge, option in candidates[:MAX_PARALLEL]:
        edge["options"].append(option)
    print("  ", min(len(candidates), MAX_PARALLEL), "of", len(edges),
          "links got a parallel road (", len(candidates), "possible )")

    # 4. checks
    print()
    ratios = []
    for edge in edges:
        a_lat, a_lng = nodes[junction_node[edge["a"]]]
        b_lat, b_lng = nodes[junction_node[edge["b"]]]
        straight = metres(a_lat, a_lng, b_lat, b_lng) / 1000.0
        for option in edge["options"]:
            ratios.append((option["km"] / max(straight, 0.05), edge["a"], edge["b"], option["name"]))
    ratios.sort(reverse=True)
    print("Longest detours (road length / straight line):")
    for ratio, a, b, name in ratios[:4]:
        print("  %.2f  %s - %s via %s" % (ratio, a, b, name))
    lengths = sorted(option["km"] for edge in edges for option in edge["options"])
    print("Link lengths: shortest %.2f km, median %.2f km, longest %.2f km"
          % (lengths[0], lengths[len(lengths) // 2], lengths[-1]))

    city = {
        "attribution": "Road data (c) OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright",
        "notes": "Junction positions, road shapes, names and lengths come from OpenStreetMap. "
                 "Travel times are MODELLED from road class and length, not measured. One-way streets are ignored.",
        "area": "Jayanagar, Bangalore",
        "junctions": [{"name": name, "lat": nodes[junction_node[name]][0],
                       "lng": nodes[junction_node[name]][1]} for name in names],
        "edges": edges,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(city, file, separators=(",", ":"))
    print()
    print("Wrote", OUTPUT_FILE, "-", os.path.getsize(OUTPUT_FILE) // 1000, "KB")


if __name__ == "__main__":
    build()
