"""Ambulance dispatch for Jayanagar, Bangalore (real OpenStreetMap roads).

Modules
    mapdata   loads the map and the hospital survey into a "world" dictionary
    routing   finds routes with the Dijkstar library (roads are a multigraph)
    triage    turns the caller's answers into a priority and a care type
    dispatch  picks the ambulance, the route and the hospital
    voice     optional spoken questions (Windows)
    gui       the desktop window
"""

__version__ = "1.0.0"
