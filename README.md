# SecondsHunt - 112 Ambulance Dispatch

A prototype 112 emergency control room. A dispatcher enters where the emergency is and answers six triage questions (or answers them by voice). The system then picks **which ambulance** to send, **which route** it takes, and **which hospital** the patient goes to, and it explains each decision.

It was built for the Zero Hour hackathon (Optimization, Graph Theory and Intelligent Systems track). It is a demonstration on **made-up data**, not a tool for real emergencies.

## What is new compared with "send the nearest ambulance"

1. **Time-dependent multigraph city.** Two neighbouring junctions can be joined by several parallel roads. Every road has a travel time that changes between night, day and rush hour, written `average+extra` (for example `6+6` means 6 minutes on average, up to 6 more in bad traffic). The idea of parallel arcs with different trade-offs comes from the multigraph model in *The Electric Vehicle Routing and Overnight Charging Scheduling Problem on a Multigraph* (Yamin, Desaulniers, Mendoza); the battery part was left out.
2. **Priority-aware routing.** Triage gives a priority of 1, 2 or 3. Priority 1 cases take the route with the best *worst-case* time (most reliable), priority 3 cases take the fastest *average* route, and priority 2 is in between.
3. **Hospital choice by capability.** A hospital is only considered if it has the facilities the case needs **and** a free bed. Among the rest, the best total of travel time plus waiting time wins.
4. **Explainable decisions.** Every dispatch lists each ambulance and hospital that was considered, with the reason for each rejection, and compares the result with a "nearest by distance" baseline.
5. **Random cities.** Every run builds a new random 4 x 4 city (junctions, roads, hospital places, beds and facilities), and a seed number replays any city.
6. **Voice call.** The program asks the time, the location and the six triage questions aloud and listens to the answers.

## How the decision works

### Triage questions

| Question | A "yes" means |
|---|---|
| Is the person conscious? | (a "no" is a danger sign) |
| Is the person breathing normally? | (a "no" is a danger sign) |
| Is there chest pain or pressure? | danger sign |
| Face drooping, slurred speech or one-side weakness? | danger sign (stroke) |
| Is there heavy bleeding that will not stop? | danger sign |
| Was there a road accident, fall or serious injury? | injury |

| Result | Priority | Route chosen by |
|---|---|---|
| One or more danger signs | 1 - life-threatening | worst-case time |
| No danger sign, but an injury | 2 - urgent | average plus half the possible delay |
| Neither | 3 - not urgent | average time |

The care type is chosen in this order: injury or heavy bleeding means **accident**; stroke signs means **stroke**; chest pain, unconscious or not breathing means **cardiac**; otherwise **minor**.

### Facilities a hospital must have

| Care type | Required facilities |
|---|---|
| cardiac | cath lab, ICU |
| stroke | stroke unit, CT scan |
| accident | trauma unit (plus a blood bank at priority 1) |
| minor | general |

The triage rules and facility requirements are a simplified example written for this project. **They are not a real medical protocol.**

## How the routing works (Dijkstra on a time-dependent multigraph)

The route finder is `find_route` in `city_engine.py`. It is **Dijkstra's shortest-path algorithm written by hand** with plain loops and dictionaries (no routing library such as NetworkX is used), extended in two ways: roads are a multigraph, and a road's cost depends on the time of day.

### The basic idea of Dijkstra

Dijkstra finds the cheapest way from a start junction to every other junction, working outwards from the start:

1. Give every junction a *cost so far*: 0 for the start, "unknown" for the rest.
2. Pick the junction with the **lowest cost so far that is not finished yet**. Its cost can no longer be improved, because every road costs a positive amount, so any other way to reach it must pass through a junction that is at least as expensive. Mark it finished.
3. For every road leaving that junction, work out the cost of reaching the road's other end *through this junction*. If that is cheaper than what we knew, remember the new cost and which road we used to get there.
4. Repeat from step 2. Stop as soon as the junction we pick is the destination.
5. Walk backwards from the destination, following the remembered roads, to rebuild the route.

The code keeps these in three dictionaries: `best_cost` (cost so far), `came_from` (the road used to arrive) and `clock_at` (the time of day we arrive), plus a set `finished`.

### What makes it a multigraph

Between two neighbouring junctions there can be **several roads**. `roads[(a, b)]` holds a list of road options, and step 3 loops over *every* option in that list, so the cheapest option wins each time. A pair of parallel roads is built as one quick-but-unpredictable road and one longer, steady road, so the choice between them is a real decision.

### What makes it time-dependent

Each road stores `(average, extra)` minutes for night, day and rush hour. When the search leaves a junction it first works out the time of day we reach it (`clock_at`) and looks up the traffic period for that moment, so the same road can cost different amounts depending on when the ambulance gets there. The clock moves forward by the road's average time each step.

### The cost of a road depends on the priority

`road_cost` turns the `(average, extra)` pair into one number. The mode comes from the triage priority:

| Mode | Cost of a road | Used for |
|---|---|---|
| `distance` | its length in km | the baseline ("nearest by distance") |
| `average` | average | priority 3 |
| `balanced` | average + extra / 2 | priority 2 |
| `worst_case` | average + extra | priority 1 |

The algorithm itself never changes; only the number each road is given does. That is how one routine serves both the baseline and the smart dispatcher.

### Worked example

Rush hour in the fixed city, from Race Course to Majestic. Two parallel roads join them: Seshadri Rd costs `6+6` and Race Course Rd costs `8+1` (average + extra).

- Priority 3 (`average`): 6 against 8, so the route takes **Seshadri Rd**.
- Priority 1 (`worst_case`): 12 against 9, so the route takes **Race Course Rd**.

Same graph, same algorithm, different priority, different road. In the test city that gives 8 / 9 minutes (average / worst case) for the steady road against 6 / 12 for the quick one.

### Details

- **Ties:** if two ways reach a junction at the same cost, the one with the faster average time wins (except in `distance` mode).
- **Blocked roads:** any `(from, to, road name)` in the `blocked` set is skipped. A blocked road removes only that option, so its parallel sibling can still be used. If no route remains, `find_route` returns `None`.
- **Used twice per dispatch:** once from each free ambulance to the patient, and once from the patient to each eligible hospital. `measure_route` then replays a finished route to report its real average and worst-case time.
- **Size:** the grid has 16 junctions, so the simple "scan every junction for the lowest cost" step is fast enough. A larger city would use a priority queue instead.

### Simplifications to know about

- The traffic period at a junction is looked up from the *average* arrival time along the cheapest path found so far, even in `worst_case` mode. Strictly, a time-dependent shortest path can need more than one label per junction; we keep one for simplicity.
- Roads are assumed never to get faster by waiting, which is the usual condition for Dijkstra to stay correct with time-dependent costs. Our travel times are made up, but they respect this.

## Files

| File | What it does |
|---|---|
| `city_engine.py` | The brain: city and roads, route finder (Dijkstra), ambulances, hospitals, triage, dispatch decision, random city generator. Has no screen of its own. |
| `map_112.py` | The main program: a window with a live map, clickable junctions and roads, tick boxes for the triage questions, the DISPATCH button and the VOICE CALL button. |
| `dispatch_112.py` | The same control room as a text menu in the terminal. |
| `ambulance_dispatch.py` | Runs eight fixed test emergencies on the fixed city and prints a table comparing the baseline with the smart dispatcher. |
| `voice.py`, `voice_helper.ps1` | Speaking and listening, using the speech tools built into Windows. |

## Running it

Requirements: Python 3 with `tkinter` (included with the standard Python installer). The voice call needs **Windows** (it uses the built-in speech engine, so nothing has to be installed and it works offline). It was tested on Python 3.15 on Windows 11.

```bash
python map_112.py            # map window, a NEW random city every run
python map_112.py 1          # replay the random city with seed 1
python map_112.py default    # the fixed city
python dispatch_112.py       # text version (same seed options)
python ambulance_dispatch.py # baseline vs smart comparison (fixed city)
```

In the map window:
- Click a junction to set where the emergency is.
- Tick the triage answers (a tick means "yes") and press **DISPATCH**.
- Click a road to block it or open it again, and click a busy ambulance to put it back in service.
- Move the slider to change the hour of the day.
- **NEW RANDOM CITY** and **DEFAULT CITY** switch cities without restarting. The seed is shown under the heading.
- **VOICE CALL** asks everything aloud. Wait for the beep, then say "yes" or "no", a time like "nine A M", or a junction name. Press the button again, or close the window, to stop.

## Example demo cases

All at 09:00 (rush hour). "Nearest" means the ambulance with the fewest kilometres. Times are average / worst case in minutes.

**Seed 1** (unconscious with chest pain at Orion Mall): the smart system sends Amb-5 at 7 / 9, while nearest-by-distance would send Amb-2 at 13 / 21. With stroke signs at Bangalore University, the nearest hospital (Bravo) is rejected for having no stroke unit and no CT scan, and the patient goes to Echo Hospital.

**Seed 3** (unconscious with chest pain at Richmond Circle): Amb-5 at 11 / 13 against Amb-1 at 12 / 19. With stroke signs at Richmond Circle, Echo Hospital is rejected (no CT scan, no free bed) and the patient goes to Alpha Hospital.

**Fixed city** (`python map_112.py default`, or `python ambulance_dispatch.py` for the full table): unconscious with chest pain at Majestic takes the steadier Race Course Rd (8 / 9) instead of the quicker-on-average Seshadri Rd (6 / 12), and goes to Manyata Heart because Majestic General has no cath lab. A stroke at Palace Grounds in the evening rush gets Amb-2 at 7 / 9, against 16 / 27 for nearest-by-distance.

## Limitations

- **All data is made up.** Junction and road names are real Bangalore names in the fixed city, but the layout is a simplified grid and the travel times, ambulances and hospitals are invented. Hospital names are invented on purpose. In a random city the road and junction names no longer match real geography.
- The results show the method working on test data. They are not measurements of real Bangalore traffic.
- Calls are handled one at a time. There is no queue where a priority 1 call overtakes a waiting priority 3 call.
- A dispatched ambulance jumps straight to its hospital and shows as busy there; it does not move along its route.
- The ambulance is chosen by time to the patient only, not by the whole trip to the hospital.
- "Worst case" is the average plus the possible delay on each road, not a real probability.
- Voice recognition uses an American English engine, so some junction names may need repeating. The tick boxes always work as a fallback.
