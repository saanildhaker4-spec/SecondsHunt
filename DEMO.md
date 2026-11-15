# Demo cases

Every number here comes from running `python demo_cases.py`, which reproduces them without the window. All data is made up (see [README.md](README.md)).

- **Times** are minutes, written *average / worst case*.
- **SMART** is our dispatcher. **NEAREST** is the old rule: nearest ambulance by kilometres and nearest hospital by kilometres.
- Start the window with `python map_112.py default` for the fixed city, or `python map_112.py <seed>` for a random one. The hour slider starts at 9.
- In the window, a tick means "yes". Setting up each kind of call:

| Call | Triage answers |
|---|---|
| Unconscious with chest pain | untick "conscious", tick "chest pain" |
| Stroke | tick "stroke signs" |
| Injury | tick "injury" |
| No danger signs | leave the defaults |

Restart between cases (ambulances stay busy and beds stay used), or press **DEFAULT CITY**.

## Fixed city

| # | Situation | SMART | NEAREST | What it shows |
|---|---|---|---|---|
| F1 | 09:00, stroke at Palace Grounds | Amb-2 from Manyata Tech Park, **7 / 9**, to Manyata Heart | Amb-1 via Majestic, **16 / 27**, to Majestic General (no stroke unit, no CT scan) | Nearest is not fastest, and the nearest hospital is wrong |
| F2 | 09:00, unconscious with chest pain at Majestic | Amb-1 by Race Course Rd, **8 / 9**, to Manyata Heart | Amb-1 by Seshadri Rd, **6 / 12**, to Majestic General (no cath lab, no ICU) | Priority 1 takes the reliable road; hospital needs the right facilities |
| F3 | 09:00, no danger signs at Majestic | Amb-1 by Seshadri Rd, **6 / 12**, to Majestic General | the same | Priority 3 takes the road that is quickest on average |
| F4 | 02:00, unconscious with chest pain at Majestic | Amb-1, **3 / 3**, to Manyata Heart | Amb-1, **3 / 3**, to Majestic General (wrong) | At night the roads agree; only the hospital differs |
| F5 | 14:00, no danger signs at Bangalore University | Amb-1, **5 / 6**, to Majestic General | Amb-1, **5 / 6**, to University Clinic (no free bed) | A full hospital is skipped |
| F6 | F3 with Seshadri Rd blocked | Amb-1 by Race Course Rd, **8 / 9** | Amb-3 from KR Market, **8 / 12** | A blocked road removes one option; its parallel road is used |

F2 against F3 is the core demonstration: same place, same time, same ambulance, and the only thing that changes is how urgent the caller says it is.

## Random cities

| Seed | Situation (09:00) | SMART | NEAREST |
|---|---|---|---|
| 1 | Unconscious with chest pain at Orion Mall | Amb-5, **7 / 9**, to Alpha Hospital | Amb-2, **13 / 21**, to Echo Hospital (no cath lab) |
| 1 | Stroke at Bangalore University | Amb-5 by Race Course Rd, **8 / 9**, to Echo Hospital | Amb-5 by Seshadri Rd, **6 / 12**, to Bravo Hospital (no stroke unit, no CT scan) |
| 3 | Unconscious with chest pain at Richmond Circle | Amb-5, **11 / 13**, to Charlie Hospital | Amb-1, **12 / 19**, to Echo Hospital (no ICU, no free bed) |
| 3 | Stroke at Richmond Circle | Amb-5, **11 / 13**, to Alpha Hospital | Amb-1, **12 / 19**, to Echo Hospital (no CT scan, no free bed) |
| 6 | Unconscious with chest pain at Majestic | Amb-3, **7 / 9**, to Echo Hospital | Amb-2, **14 / 19**, to Bravo Hospital (no ICU) |

Run `python map_112.py 1` to see seed 1 in the window. The same seed always gives the same city.

## A two-minute demo order

1. **F1** (fixed city): nearest is not fastest, and the nearest hospital is wrong.
2. **F2 then F3**: same place and time, different urgency, different road.
3. **F6**: block Seshadri Rd, dispatch F3 again, and watch it fall back to the parallel road.
4. Press **NEW RANDOM CITY**, place any emergency, and point at the rejection reasons in the WHY list. This shows it is not a rehearsed layout.
5. Optional: press **VOICE CALL** and answer the questions aloud.

## Honest numbers (read these before you present)

The cases above were chosen because they show a difference. To see how often the difference appears, we ran 2,880 cases per priority level over 60 random cities (three hours of the day, all 16 places, no cases skipped). `python honest_numbers.py` reproduces these numbers in a few seconds:

| Priority 1 (cardiac) | Result |
|---|---|
| Smart picks a different ambulance than nearest-by-distance | 14.8% of cases |
| Worst-case time: smart better / same / worse | 26.2% / 73.8% / 0.0% |
| Mean worst-case change | 1.37 minutes faster |
| Average time: smart better / same / slower | 13.6% / 76.5% / 9.9% |
| Nearest hospital by distance cannot treat the case | 69.4% |

Against a **stronger baseline** (same graph and traffic, routes chosen by average time, ignoring priority), the reliable routing for priority 1 improves the worst case in 13.8% of cases, saves 0.52 minutes on average over all cases (3.75 minutes where it differs), and is slower on average in 12.7% of cases.

What this means:
- The travel-time gain is **real but modest and uneven**: most calls get the same ambulance and road as a plain nearest rule, and a minority get a clearly better one.
- The **largest effect is the hospital**, but the baseline there is deliberately naive (nearest hospital, blind to facilities and beds), and the facilities are random, so the 69.4% depends on how we generated hospitals.
- The reliable route is a **trade**: it sometimes costs a little average time to cut the worst case.
- All of this is on synthetic cities and says nothing about real traffic.
