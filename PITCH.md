# Pitch - answers to the hard questions

Short, honest answers for judges. Numbers come from the fixed test city (`python ambulance_dispatch.py`) or from the random cities (`python map_112.py <seed>`). All data is made up, and we say so.

## The pitch in one breath

> "Most dispatch systems send the nearest ambulance along one road graph. We model every road as parallel options whose travel times change through the day, ask the caller triage questions, and then choose the ambulance, the route and the hospital by how urgent the case is, so a life-threatening case gets the most reliable route to a hospital that can actually treat it."

## 30-second version

Ambulances lose minutes in two places: on the way to the patient and on the way to a hospital that cannot help. We fix both. The city is a graph where each road has night, day and rush-hour times, with parallel roads between some junctions (an idea from multigraph routing research). Six triage questions turn into a priority. Priority 1 takes the most reliable route, priority 3 the fastest on average. The hospital must have the right facilities and a free bed. Every decision is explained on screen and compared with "nearest by distance".

## Questions we expect

### Everyone else is doing ambulance routing. Why you?
Many teams will run Dijkstra on a city graph, and so do we. That part is not our claim. Our claim is the **combination**: parallel roads with time-of-day travel times, routing that depends on the patient's priority, and hospital choice by required facilities and beds, all in one decision that explains itself. Each idea exists separately in research; we put them together in one small system that can be demonstrated and tested.

### Blinkit already offers ambulances. What is special about yours?
Blinkit sells a fleet: you book a Basic Life Support ambulance in an app. Reports say it began in Gurugram in January 2025 and has since covered parts of Delhi NCR. We are not an ambulance service. We are the **decision layer behind any ambulance**: which unit to send, by which route, to which hospital. It could sit inside a service like Blinkit's or inside a 112 control room. How Blinkit chooses its ambulances is not public, so we do not claim to beat it.

### India's 108 and 112 already dispatch the nearest ambulance by GPS. What do you add?
Nearest is not always fastest. In our test city, for a stroke at Palace Grounds in the evening rush, the nearest unit takes 16 minutes (worst case 27), while a unit one junction farther away on a better road takes 7 (worst case 9). And the nearest *hospital* is often the wrong one: it may have no stroke unit, no CT scan or no free bed. We check that before the ambulance leaves.

### What exactly is new?
1. Parallel roads between junctions, each with its own time-of-day profile.
2. Route reliability chosen by triage priority.
3. Hospital choice that requires specific facilities and a free bed.
4. A full explanation for every decision.

We do not claim any single part is unknown to researchers. We claim the integrated, explainable whole.

### Why would a life-threatening case take a slower route?
Because average time hides risk. Example at 09:00 in the fixed city: one road is 6 minutes on average but can take 12; the parallel road is 8 and never worse than 9. For a priority 1 case we take the 8-minute road, because being late costs more than 2 extra minutes. For a priority 3 case we take the 6-minute road.

### Doesn't every caller need help immediately?
Yes. Every case gets the fastest response the system can give. Priority does not decide who is helped. It decides how the system handles **uncertainty and conflict**: how much risk to accept on the route, and which case a limited resource protects first.

### How do you know it works?
On the eight fixed test cases (chosen to show where the systems differ), the smart dispatcher's total worst-case response was 72 minutes against 100 for nearest-by-distance, and it sent 0 of 8 patients to a hospital that could not treat them against 4 of 8 for the baseline. We also generated 120 random cities and checked they are valid, and in 256 of 300 random cities we tried, all three effects (nearest is not fastest, priority changes the route, nearest hospital rejected) can be demonstrated. These show the method works on test data. They are not measurements of real traffic.

### Is the data real?
No. The junction and road names in the fixed city are real Bangalore names, but the layout is a simplified grid and all travel times, ambulances, beds and facilities are invented. Hospital names are invented on purpose, so we never make claims about real hospitals. In a random city even the geography is shuffled.

### Is the triage medically valid?
No. The six questions and priority rules are a simplified example we wrote for the demonstration. A real deployment would use the control room's own clinical protocol. Our system only needs the questions to produce a priority and a care type, so the protocol can be swapped without changing the routing.

### How does it relate to the research paper from the mentoring round?
The paper models electric-vehicle routing on a **multigraph**: several arcs between the same two places, each trading time against energy. We kept the multigraph idea and used it for roads, where each arc has its own time-of-day profile. We dropped the battery and charging part. The paper is about delivery fleets, so we do not claim to extend its results.

### Which algorithm do you use?
Dijkstra's shortest path. The cost of a road depends on the arrival time, so it is a time-dependent version, and on the priority: distance for the baseline, average time, average plus half the delay, or the worst case. When two options tie, the faster average wins.

### Why not machine learning or live traffic data?
For a first version, explainability matters more than a black box. A dispatcher must be able to see why an ambulance was chosen. Live traffic feeds would replace our invented times with real ones without changing the logic, and learning could later predict the delay on each road.

### What happens when things go wrong?
- **Road blocked:** one parallel road is closed and the system uses the sibling road, or a detour.
- **All ambulances busy:** the system says so instead of guessing.
- **No hospital can treat the case:** it says so and tells the operator to call hospitals directly.
- **Voice not understood:** it asks twice, then asks the operator to use the tick boxes.

### What would it take to use this for real?
Real road data with time-of-day travel times, live ambulance positions, a live feed of hospital beds and facilities, and the control room's clinical protocol. A human dispatcher stays in charge. This is decision support, not an autopilot.

### What are the limits?
- Calls are handled one at a time, with no queue where a priority 1 call overtakes a waiting one.
- A dispatched ambulance jumps to its hospital instead of driving along the route.
- The ambulance is chosen by time to the patient only, not by the whole trip.
- "Worst case" is average plus possible delay, not a real probability.
- The voice recogniser is American English, so some junction names may need repeating.

### What would you build next?
A queue for simultaneous emergencies, coverage-aware choices that keep ambulances spread across the city, repositioning ambulances in quiet hours, and testing on a real road network.

## Demo flow (about two minutes)

Use `python map_112.py default` for a repeatable demo, at hour 9 unless stated.

1. **Nearest is not fastest.** Click Palace Grounds, tick only "stroke signs", dispatch (this works at hour 9 and at hour 18). Amb-2 arrives in 7 / 9 minutes against 16 / 27 for the nearest. The patient goes to Manyata Heart, which has a stroke unit and a CT scan.
2. **Priority changes the route.** Click Majestic, untick "conscious", tick "chest pain", dispatch: the steady road, 8 / 9. Restart, leave the default answers, dispatch: the quick road, 6 / 12.
3. **Facilities matter.** Point at the hospital rejections in the WHY list, for example "rejected (no cath_lab, no icu)".
4. **A blocked road.** Click the Seshadri Rd line between Race Course and Majestic to block it. Click Majestic, leave the default answers, and dispatch: Amb-1 falls back to the parallel Race Course Rd (8 / 9), while nearest-by-distance switches to a different ambulance at 8 / 12.
5. **Random city.** Press NEW RANDOM CITY and dispatch again to show it works on a layout nobody rehearsed.

Times are average / worst case in minutes.
