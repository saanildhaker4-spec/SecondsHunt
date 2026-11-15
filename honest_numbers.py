# =====================================================================
#  HONEST NUMBERS - how often does the smart dispatcher really win?
# =====================================================================
#  The hand-picked demo cases are chosen because they show a difference.
#  This script measures the difference over many random cities instead:
#  60 random cities x 3 hours of the day x 16 places, for three kinds of
#  emergency. It prints the numbers quoted in DEMO.md:
#
#       python honest_numbers.py        (takes a few seconds)
#
#  All data is made up, so this says nothing about real traffic.
# =====================================================================

from city_engine import *


def mean(numbers):
    return sum(numbers) / len(numbers)


def percent(flags):
    return 100.0 * sum(1 for flag in flags if flag) / len(flags)


# one kind of emergency for each priority level
kinds = [("cardiac", 1), ("accident", 2), ("minor", 3)]
hours = [2, 9, 18]
seeds = range(1, 61)

results = {}           # results["P1_worst"] = list of numbers, and so on
vs_average = {"worst": [], "average": []}


def add(name, value):
    if name not in results:
        results[name] = []
    results[name].append(value)


for seed in seeds:
    random_city(seed)
    for hour in hours:
        clock = hour * 60
        for place in places:
            # the old rule: nearest ambulance and nearest hospital by km
            old_ambulance, old_route = nearest_ambulance_by_distance(place, clock)
            old_average, old_worst = measure_route(old_route, clock)
            nearest_hospital = None
            nearest_km = None
            for name in hospitals:
                km, route = find_route(place, hospitals[name]["at"], clock, "distance", blocked)
                if km is not None and (nearest_km is None or km < nearest_km):
                    nearest_hospital, nearest_km = name, km

            for emergency_type, priority in kinds:
                plan, reasons = smart_dispatch(place, emergency_type, priority, clock)
                tag = "P" + str(priority)
                add(tag + "_worst_saved", old_worst - plan["worst"])
                add(tag + "_average_saved", old_average - plan["average"])
                add(tag + "_other_ambulance", plan["ambulance"] != old_ambulance)
                add(tag + "_wrong_hospital",
                    not hospital_can_treat(nearest_hospital, emergency_type, priority))

            # a stronger baseline for priority 1: same graph and traffic, but
            # the route is chosen by AVERAGE time (it ignores the priority)
            careful, reasons = smart_dispatch(place, "cardiac", 1, clock)
            plain, reasons = smart_dispatch(place, "cardiac", 3, clock)
            vs_average["worst"].append(plain["worst"] - careful["worst"])
            vs_average["average"].append(plain["average"] - careful["average"])

count = len(results["P1_worst_saved"])
print("cases per priority level:", count)
print("(positive 'saved' = the smart dispatcher is faster than the nearest rule)")

for tag in ["P1", "P2", "P3"]:
    worst = results[tag + "_worst_saved"]
    average = results[tag + "_average_saved"]
    print()
    print(tag)
    print("  smart sends a different ambulance : %.1f%% of cases"
          % percent(results[tag + "_other_ambulance"]))
    print("  worst case  : better %.1f%%, same %.1f%%, worse %.1f%%"
          % (percent([x > 0 for x in worst]), percent([x == 0 for x in worst]),
             percent([x < 0 for x in worst])))
    print("                mean saved %.2f min" % mean(worst))
    print("  average time: better %.1f%%, same %.1f%%, slower %.1f%%"
          % (percent([x > 0 for x in average]), percent([x == 0 for x in average]),
             percent([x < 0 for x in average])))
    print("                mean saved %.2f min" % mean(average))
    print("  nearest hospital by km cannot treat the case: %.1f%%"
          % percent(results[tag + "_wrong_hospital"]))

worst = vs_average["worst"]
average = vs_average["average"]
different = [x for x in worst if x != 0]
print()
print("PRIORITY 1 against a stronger baseline (routes chosen by average time)")
print("  worst case  : better %.1f%%, same %.1f%%, worse %.1f%%"
      % (percent([x > 0 for x in worst]), percent([x == 0 for x in worst]),
         percent([x < 0 for x in worst])))
print("                mean saved %.2f min over all cases, %.2f min where it differs"
      % (mean(worst), mean(different)))
print("  average time: slower in %.1f%% of cases, mean change %.2f min"
      % (percent([x < 0 for x in average]), -mean(average)))
