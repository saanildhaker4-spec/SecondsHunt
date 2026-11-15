# =====================================================================
#  ROUTING - finds routes with the Dijkstar library
# =====================================================================
#  Dijkstar (https://pypi.org/project/Dijkstar/) is a small Python
#  library that implements Dijkstra's shortest-path algorithm. This file
#  uses it in three ways that make it fit an ambulance map:
#
#  1. MULTIGRAPH. Dijkstar keeps ONE edge between two junctions, but an
#     edge can carry any data. We give every edge the LIST of roads
#     between its two junctions. The cost function looks at all of them
#     and charges the cost of the best one, so parallel roads are
#     handled inside Dijkstar's normal search.
#  2. TRAFFIC. The cost of a road depends on the time of day (night, day
#     or rush hour) and on the priority of the patient. See `road_cost`.
#  3. CLOSED ROADS. A closed road is simply left out of the graph, and
#     an edge with no open road left is left out too.
#
#  Simplification: the time of day (period) is fixed when the call is
#  taken and used for the whole journey.
# =====================================================================

from dijkstar import Graph, find_path
from dijkstar.algorithm import NoPathError

# the ways a road can be priced (the priority of the patient picks one)
MODES = ["distance", "average", "balanced", "worst_case"]


def road_cost(road, mode, period):
    """The cost of one road as one number.
       distance   : its length in km (used by the old 'nearest' rule)
       average    : the usual travel time
       balanced   : the usual time plus half of the possible delay
       worst_case : the usual time plus all of the possible delay"""
    average, extra = road["times"][period]
    if mode == "distance":
        return road["km"]
    if mode == "average":
        return average
    if mode == "balanced":
        return average + extra / 2.0
    return average + extra


def best_road(roads, mode, period):
    """The cheapest of several parallel roads. If two cost the same, the
    one with the faster usual time wins, then the name (so the answer is
    always the same)."""
    return min(roads, key=lambda road: (road_cost(road, mode, period),
                                        road["times"][period][0], road["name"]))


def get_graph(world):
    """The Dijkstar graph of the open roads. It is rebuilt only when a
    road has been closed or opened."""
    signature = frozenset(world["blocked"])
    cached = world.get("_graph")
    if cached is not None and cached[0] == signature:
        return cached[1]
    graph = Graph(undirected=True)
    for (a, b), roads in world["between"].items():
        open_roads = [road for road in roads if road["id"] not in world["blocked"]]
        if len(open_roads) > 0:
            graph.add_edge(a, b, open_roads)       # the edge data is the LIST of roads
    world["_graph"] = (signature, graph)
    return graph


def empty_route():
    return {"junctions": [], "roads": [], "cost": 0.0, "average": 0.0, "worst": 0.0, "km": 0.0}


def find_route(world, start, goal, mode, period):
    """The best route from one junction to another, or None if every
    way is closed. Returns a dictionary:
       junctions : the junctions passed, in order
       roads     : the road used for each step
       cost      : the total cost in the chosen mode
       average, worst, km : the usual time, the worst-case time and the length"""
    if start == goal:
        route = empty_route()
        route["junctions"] = [start]
        return route

    graph = get_graph(world)

    def cost_function(u, v, edge, previous_edge):
        # Dijkstar calls this for every edge it looks at. `edge` is the list of roads.
        return road_cost(best_road(edge, mode, period), mode, period)

    try:
        path = find_path(graph, start, goal, cost_func=cost_function)
    except (NoPathError, KeyError):
        return None

    roads = [best_road(edge, mode, period) for edge in path.edges]
    average = sum(road["times"][period][0] for road in roads)
    worst = sum(road["times"][period][0] + road["times"][period][1] for road in roads)
    return {"junctions": list(path.nodes), "roads": roads, "cost": path.total_cost,
            "average": round(average, 1), "worst": round(worst, 1),
            "km": round(sum(road["km"] for road in roads), 2)}


def describe_route(route):
    """A route as text: A -[Road]-> B -[Road]-> C"""
    if route is None:
        return "(no open route)"
    if len(route["roads"]) == 0:
        return "(already there)"
    text = route["junctions"][0]
    for i, road in enumerate(route["roads"]):
        text = text + " -[" + road["name"] + "]-> " + route["junctions"][i + 1]
    return text


def route_road_ids(route):
    """The ids of the roads of a route (used to colour them on the map)."""
    if route is None:
        return set()
    return set(road["id"] for road in route["roads"])
