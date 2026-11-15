# =====================================================================
#  112 EMERGENCY RESPONSE - DISPATCH CONSOLE (map version)
# =====================================================================
#  A window with a live map of the city.
#    - Click a junction  -> that is where the emergency is
#    - Click a road      -> block it / open it again
#    - Click a busy ambulance -> it is back in service
#    - Press DISPATCH    -> the system picks ambulance, route, hospital
#
#  The city and the routing come from city_engine.py.
#  The window is made with tkinter, which comes with Python.
#  Everything here is still plain functions, lists and dictionaries.
# =====================================================================

import math
import tkinter as tk
from city_engine import *
import voice                      # speaking and listening (voice.py)
import google_traffic             # optional Google traffic times (google_traffic.py)
from tkinter import messagebox


# ---------------------------------------------------------------------
# PART 1: WHERE THINGS ARE DRAWN
# ---------------------------------------------------------------------
# (x, y) position of each junction on the map, in pixels
positions = {}


view = {}               # how latitude / longitude become pixels (real city only)


def setup_view():
    """Work out how to turn latitude and longitude into pixels so that
    the whole real city fits in the window."""
    lats = []
    lngs = []
    for name in geo:
        lats.append(geo[name][0])
        lngs.append(geo[name][1])
    for key in roads:
        for option in roads[key]:
            if option["shape"] is not None:
                for lat, lng in option["shape"]:
                    lats.append(lat)
                    lngs.append(lng)
    view["south"] = min(lats)
    view["north"] = max(lats)
    view["west"] = min(lngs)
    view["cos"] = math.cos(math.radians((min(lats) + max(lats)) / 2))
    width_m = (max(lngs) - min(lngs)) * 111320 * view["cos"]
    height_m = (max(lats) - min(lats)) * 110574
    canvas_width = int(canvas.cget("width"))
    canvas_height = int(canvas.cget("height"))
    scale = min((canvas_width - 210) / width_m, (canvas_height - 150) / height_m)
    view["scale"] = scale
    view["left"] = (canvas_width - width_m * scale) / 2
    view["top"] = 75 + ((canvas_height - 150) - height_m * scale) / 2


def project(lat, lng):
    """Latitude and longitude -> (x, y) pixels on the map."""
    x = view["left"] + (lng - view["west"]) * 111320 * view["cos"] * view["scale"]
    y = view["top"] + (view["north"] - lat) * 110574 * view["scale"]
    return x, y


def update_positions():
    """Work out where each junction is drawn. In the grid cities this
    comes from the grid slot; in the real city from latitude and
    longitude. (Both come from city_engine.py and change when a new
    city is made.)"""
    positions.clear()
    if city_info["kind"] == "real":
        setup_view()
        for name in places:
            positions[name] = project(geo[name][0], geo[name][1])
    else:
        for name in places:
            row, column = slot_of[name]
            positions[name] = (90 + 200 * column, 100 + 160 * row)

# things the program needs to remember while the window is open
state = {
    "place": None,      # junction picked for the emergency
    "plan": None,       # the last dispatch plan (to colour its routes)
    "calls": 0,         # how many calls have been handled
    "in_call": False,   # True while a voice call is running
    "stop": False,      # True when the voice call has been told to stop
    "closed": False,    # True once the window has been closed
    "fetching": False,  # True while Google traffic times are being fetched
    "google_stop": False,   # True when that fetch has been told to stop
}

# clickable[item_number] = ("place", name) or ("road", (a, b, name))
#                          or ("ambulance", name)
clickable = {}


# ---------------------------------------------------------------------
# PART 2: DRAWING THE MAP
# ---------------------------------------------------------------------
def get_clock():
    """The time chosen on the slider, in minutes after midnight."""
    return hour_slider.get() * 60


def draw_label(x, y, text, colour, anchor, size=9):
    """Draw text with a white box behind it so it is easy to read."""
    item = canvas.create_text(x, y, text=text, fill=colour, anchor=anchor,
                              font=("Segoe UI", size))
    box = canvas.create_rectangle(canvas.bbox(item), fill="white", outline="")
    canvas.tag_raise(item, box)       # put the text on top of the box


def road_colour(a, b, name):
    """Colour and thickness of a road on the map."""
    plan = state["plan"]
    if (a, b, name) in blocked:
        return "#d62828", 4           # red = blocked
    if plan is not None:
        for step in plan["route1"]:
            if step == (a, b, name) or step == (b, a, name):
                return "#1d6fd8", 8   # blue = route to the patient
        for step in plan["route2"]:
            if step == (a, b, name) or step == (b, a, name):
                return "#2a9d3f", 8   # green = route to the hospital
    return "#9aa0a6", 4               # grey = normal road


def draw_roads():
    period = get_period(get_clock())
    done = set()                      # pairs of junctions already drawn
    for key in roads:
        a, b = key
        if (b, a) in done:
            continue
        done.add((a, b))
        x1, y1 = positions[a]
        x2, y2 = positions[b]
        sideways = (y1 == y2)         # True for a left-right road
        options = roads[key]

        number = 0
        for option in options:
            # parallel roads are drawn a little apart from each other
            shift = (number - (len(options) - 1) / 2) * 18
            number = number + 1
            name = option["name"]
            colour, width = road_colour(a, b, name)
            average, extra = option["times"][period]
            text = name + "  " + str(average) + "+" + str(extra)
            if (a, b, name) in blocked:
                text = name + "  BLOCKED"

            if sideways:
                line = canvas.create_line(x1, y1 + shift, x2, y2 + shift,
                                          fill=colour, width=width)
                if shift > 0:
                    draw_label((x1 + x2) / 2, y1 + shift + 13, text, "#333333", "center")
                else:
                    draw_label((x1 + x2) / 2, y1 + shift - 13, text, "#333333", "center")
            else:
                line = canvas.create_line(x1 + shift, y1, x2 + shift, y2,
                                          fill=colour, width=width)
                # The label goes to the right of the ambulance boxes, a
                # little above the middle of the road, so that it does
                # not cover the hospital label of the junction below.
                # Parallel roads get their labels stacked.
                label_y = min(y1, y2) + abs(y2 - y1) * 0.46
                label_y = label_y + (number - 1 - (len(options) - 1) / 2) * 14
                draw_label(x1 + 46, label_y, text, "#333333", "w")
            clickable[line] = ("road", (a, b, name))


def draw_junctions():
    for name in positions:
        x, y = positions[name]
        if name == state["place"]:
            fill, edge, width = "#ffd6d6", "#d62828", 5     # the emergency
        else:
            fill, edge, width = "#ffffff", "#333333", 2
        circle = canvas.create_oval(x - 40, y - 40, x + 40, y + 40,
                                    fill=fill, outline=edge, width=width)
        # two-word names are written on two lines so they fit in the circle
        text = canvas.create_text(x, y, text=name.replace(" ", "\n"),
                                  justify="center", font=("Segoe UI", 8, "bold"))
        clickable[circle] = ("place", name)
        clickable[text] = ("place", name)


def draw_hospitals():
    for name in hospitals:
        hospital = hospitals[name]
        x, y = positions[hospital["at"]]
        codes = []
        for facility in sorted(hospital["facilities"]):
            if facility != "general":
                codes.append(facility_short[facility])
        if len(codes) == 0:
            codes.append("general only")
        short_name = name.replace(" Hospital", "")      # keeps the label small
        text = ("[H] " + short_name + " - " + str(hospital["beds_free"]) + " beds\n"
                + " ".join(codes))
        draw_label(x, y - 58, text, "#b00020", "center", 8)


def draw_ambulances():
    count_at = {}                     # how many ambulances at each junction
    for name in ambulances:
        junction = ambulances[name]
        if junction not in count_at:
            count_at[junction] = 0
        x, y = positions[junction]
        x = x - 50                    # a little to the left of the junction
        top = y + 43 + count_at[junction] * 20
        count_at[junction] = count_at[junction] + 1
        if name in busy:
            fill, text = "#c8c8c8", name + " busy"
        else:
            fill, text = "#ffd23f", name + " free"
        box = canvas.create_rectangle(x - 40, top, x + 40, top + 18,
                                      fill=fill, outline="#333333")
        label = canvas.create_text(x, top + 9, text=text, font=("Segoe UI", 9))
        clickable[box] = ("ambulance", name)
        clickable[label] = ("ambulance", name)


# ---- drawing the REAL city: roads follow their real shapes ----------
placed_boxes = []       # boxes of the labels already drawn (so new labels avoid them)


def box_is_free(box):
    if box[0] < 2 or box[1] < 2 or box[2] > int(canvas.cget("width")) - 2 \
            or box[3] > int(canvas.cget("height")) - 22:
        return False                     # it would run off the map
    for other in placed_boxes:
        if not (box[2] < other[0] or box[0] > other[2] or box[3] < other[1] or box[1] > other[3]):
            return False
    return True


def place_text(x, y, text, colour, size, gap, background="white", bold=False):
    """Write a label next to the point (x, y), at the first spot where it
    does not cover another label. Returns the two canvas items (box, text)."""
    # (anchor, dx, dy): the label goes right, left, above, below, then the corners
    spots = [("w", gap, 0), ("e", -gap, 0), ("s", 0, -gap), ("n", 0, gap),
             ("sw", gap, -gap), ("se", -gap, -gap), ("nw", gap, gap), ("ne", -gap, gap)]
    weight = "bold" if bold else "normal"
    chosen = None
    for anchor, dx, dy in spots:
        item = canvas.create_text(x + dx, y + dy, text=text, fill=colour, anchor=anchor,
                                  font=("Segoe UI", size, weight))
        box = canvas.bbox(item)
        if box_is_free(box):
            chosen = item
            break
        canvas.delete(item)
    if chosen is None:                  # nowhere is free: use the first spot anyway
        anchor, dx, dy = spots[0]
        chosen = canvas.create_text(x + dx, y + dy, text=text, fill=colour, anchor=anchor,
                                    font=("Segoe UI", size, weight))
        box = canvas.bbox(chosen)
    placed_boxes.append(box)
    background_box = canvas.create_rectangle(box, fill=background, outline="")
    canvas.tag_raise(chosen, background_box)
    return background_box, chosen


def draw_real_roads():
    period = get_period(get_clock())
    show_all = (show_labels.get() == 1)
    done = set()
    drawn = []                           # (colour, width, points, key, option)
    for key in roads:
        a, b = key
        if (b, a) in done:
            continue
        done.add((a, b))
        for option in roads[key]:
            colour, width = road_colour(a, b, option["name"])
            if colour == "#9aa0a6":
                width = 3
            elif colour == "#d62828":
                width = 5
            else:
                width = 6
            points = []
            for lat, lng in option["shape"]:
                x, y = project(lat, lng)
                points.append(x)
                points.append(y)
            drawn.append((colour, width, points, key, option))
    # grey roads first, so the coloured route is drawn on top of them
    for special in [False, True]:
        for colour, width, points, key, option in drawn:
            if (colour != "#9aa0a6") != special:
                continue
            a, b = key
            line = canvas.create_line(*points, fill=colour, width=width,
                                      capstyle="round", joinstyle="round")
            clickable[line] = ("road", (a, b, option["name"]))
            if special or show_all:
                middle = len(points) // 4 * 2
                average, extra = option["times"][period]
                text = option["name"] + "  " + str(average) + "+" + str(extra)
                if (a, b, option["name"]) in blocked:
                    text = option["name"] + "  BLOCKED"
                draw_label(points[middle], points[middle + 1], text, "#333333", "center", 7)


def draw_real_markers():
    """Junctions, their names, hospitals and ambulances of the real city."""
    placed_boxes.clear()
    hospital_at = {}
    for name in hospitals:
        hospital_at[hospitals[name]["at"]] = name
    # junction circles first, so that labels keep clear of them
    for name in places:
        x, y = positions[name]
        if name == state["place"]:
            fill, edge, width = "#ffd6d6", "#d62828", 3
        elif name in hospital_at:
            fill, edge, width = "#ffffff", "#b00020", 3
        else:
            fill, edge, width = "#ffffff", "#333333", 2
        circle = canvas.create_oval(x - 7, y - 7, x + 7, y + 7, fill=fill, outline=edge, width=width)
        clickable[circle] = ("place", name)
        placed_boxes.append((x - 8, y - 8, x + 8, y + 8))
    for name in places:
        x, y = positions[name]
        # long names are written on two lines: "A & B" becomes "A" and "& B"
        label = name.replace(" & ", "\n& ")
        background, text = place_text(x, y, label, "#111111", 8, 10, bold=True)
        clickable[background] = ("place", name)
        clickable[text] = ("place", name)
    for name in hospitals:
        hospital = hospitals[name]
        x, y = positions[hospital["at"]]
        codes = []
        for facility in sorted(hospital["facilities"]):
            if facility != "general":
                codes.append(facility_short[facility])
        if len(codes) == 0:
            codes.append("general only")
        short_name = name.replace(" Hospital", "")
        place_text(x, y, "[H] " + short_name + " - " + str(hospital["beds_free"]) + " beds\n"
                   + " ".join(codes), "#b00020", 7, 11)
    for name in ambulances:
        x, y = positions[ambulances[name]]
        if name in busy:
            colour, text = "#c8c8c8", name + " busy"
        else:
            colour, text = "#ffd23f", name + " free"
        background, label = place_text(x, y, text, "#111111", 7, 11, background=colour)
        clickable[background] = ("ambulance", name)
        clickable[label] = ("ambulance", name)


def draw_map():
    """Wipe the map and draw everything again."""
    canvas.delete("all")
    clickable.clear()
    update_positions()
    if city_info["kind"] == "real":
        draw_real_roads()
        draw_real_markers()
        google_roads = city_info.get("google_roads", 0)
        if google_roads > 0:
            times_text = ("Travel times: Google traffic for " + str(google_roads) + " of "
                          + str(len(google_traffic.road_options())) + " roads, modelled for the rest.")
        else:
            times_text = "Travel times are MODELLED, not measured."
        canvas.create_text(430, 686, fill="#555555", font=("Segoe UI", 8),
                           text="Roads (c) OpenStreetMap contributors (ODbL). " + times_text)
        canvas.create_text(430, 700, fill="#555555", font=("Segoe UI", 8),
                           text="Blue: to patient.   Green: to hospital.   Red: blocked.")
    else:
        draw_roads()
        draw_junctions()
        draw_hospitals()
        draw_ambulances()
        canvas.create_text(430, 693, fill="#555555", font=("Segoe UI", 9),
                           text="Road numbers: average + possible delay, in minutes."
                                "   Blue: to patient.   Green: to hospital.   Red: blocked.")
    clock = get_clock()
    time_label.config(text="Time " + show_clock(clock) + "  (" + get_period(clock) + " traffic)")
    if state["place"] is None:
        place_label.config(text="Emergency at: (click a junction)")
    else:
        place_label.config(text="Emergency at: " + state["place"])


# ---------------------------------------------------------------------
# PART 3: WHAT HAPPENS WHEN THE OPERATOR CLICKS
# ---------------------------------------------------------------------
def write(lines):
    """Replace the text in the message box with these lines."""
    message_box.delete("1.0", "end")
    for line in lines:
        message_box.insert("end", line + "\n")


def on_map_click(event):
    """Work out what was clicked on the map and react to it."""
    items = canvas.find_overlapping(event.x - 4, event.y - 4, event.x + 4, event.y + 4)
    # if several things are under the mouse, ambulances win, then
    # junctions, then roads
    found = None
    for wanted in ["ambulance", "place", "road"]:
        for item in items:
            if found is None and item in clickable and clickable[item][0] == wanted:
                found = clickable[item]
    if found is None:
        return

    kind, value = found
    if kind == "place":
        state["place"] = value
    elif kind == "road":
        a, b, name = value
        if (a, b, name) in blocked:
            blocked.remove((a, b, name))
            blocked.remove((b, a, name))
            write([name + " (" + a + " - " + b + ") is OPEN again."])
        else:
            blocked.add((a, b, name))
            blocked.add((b, a, name))
            write([name + " (" + a + " - " + b + ") is now BLOCKED."])
    elif kind == "ambulance":
        if value in busy:
            busy.remove(value)
            write([value + " is back in service at " + ambulances[value] + "."])
    draw_map()


def read_triage():
    """Read the ticked answers and work out the type and priority."""
    answers = {}
    for key in answer_boxes:
        answers[key] = (answer_boxes[key].get() == 1)
    return triage(answers)


def on_answer_change():
    """Show the priority as soon as an answer is ticked or unticked."""
    emergency_type, priority, why = read_triage()
    colours = {1: "#b00020", 2: "#c77700", 3: "#2a7d3f"}
    priority_label.config(fg=colours[priority],
                          text=priority_names[priority] + "\nCare needed: "
                               + ", ".join(required_facilities(emergency_type, priority))
                               + "   (" + ", ".join(why) + ")")


def on_time_change(value):
    draw_map()


def on_dispatch():
    """The DISPATCH button."""
    place = state["place"]
    if place is None:
        write(["First click a junction on the map to say where the emergency is."])
        return
    clock = get_clock()
    emergency_type, priority, why = read_triage()

    plan, reasons = smart_dispatch(place, emergency_type, priority, clock)
    if plan is None:
        write(reasons + ["", "!! NO AMBULANCE AVAILABLE.",
                         "Click a busy ambulance on the map when it is back in service."])
        return

    state["calls"] = state["calls"] + 1
    lines = ["DISPATCH ORDER  INC-" + str(state["calls"]).rjust(3, "0")
             + "   " + show_clock(clock) + "   " + emergency_type + " at " + place]
    lines.append(priority_names[priority] + " (" + ", ".join(why) + ")")
    lines.append("Send     : " + plan["ambulance"])
    lines.append("Route    : " + show_route(plan["route1"]))
    lines.append("Arrives in " + str(plan["average"]) + " min (worst case "
                 + str(plan["worst"]) + " min)")
    if plan["hospital"] is None:
        lines.append("Hospital : !! NONE can treat this case right now.")
    else:
        lines.append("Take to  : " + plan["hospital"])
        lines.append("Route    : " + show_route(plan["route2"]))

    # comparison with the old "nearest by distance" rule
    old_name, old_route = nearest_ambulance_by_distance(place, clock)
    old_average, old_worst = measure_route(old_route, clock)
    lines.append("")
    lines.append("Nearest-by-distance would send " + old_name + ": "
                 + str(old_average) + " min (worst case " + str(old_worst) + " min)")
    lines.append("")
    lines.append("WHY:")

    commit_dispatch(plan)
    state["plan"] = plan
    write(lines + reasons)
    draw_map()


VOICE_BUTTON_TEXT = "VOICE CALL  (ask the questions aloud)"


def keep_window_alive():
    """Called while the computer is speaking or listening.
    Returns False if the call must stop (STOP pressed or window closed)."""
    if state["closed"]:
        return False
    window.update()
    if state["closed"] or state["stop"]:
        return False
    return True


def end_voice_call():
    """Tidy up when a voice call finishes or is stopped."""
    was_stopped = state["stop"]
    state["in_call"] = False
    state["stop"] = False
    if state["closed"]:
        return                        # the window is gone: touch nothing
    voice_button.config(text=VOICE_BUTTON_TEXT)
    if was_stopped:
        write(["Voice call stopped."])


def city_summary_lines():
    """The hospitals of the current city, as lines of text."""
    lines = []
    if city_info["kind"] == "real":
        lines = ["Roads: real, from OpenStreetMap (c) contributors (ODbL).",
                 "Travel times: MODELLED from road class and length, not measured.",
                 "Hospitals and ambulances are invented.", ""]
    lines = lines + ["HOSPITALS in this city:"]
    for name in hospitals:
        hospital = hospitals[name]
        lines.append("  " + name + " at " + hospital["at"] + ": "
                     + str(hospital["beds_free"]) + " beds, wait "
                     + str(hospital["wait"]) + " min")
        lines.append("      has: " + ", ".join(sorted(hospital["facilities"])))
    return lines


def show_city_info():
    window.title("112 Emergency Response - Dispatch Console  (" + describe_city() + ")")
    if city_info["kind"] == "random":
        hint = "   (python map_112.py " + str(city_info["seed"]) + "  replays it)"
    elif city_info["kind"] == "real":
        hint = "   (python map_112.py real " + str(city_info["seed"]) + ")"
        if city_info.get("google_roads", 0) > 0:
            hint = hint + "  Google traffic: " + str(city_info["google_roads"]) + " roads"
    else:
        hint = "   (python map_112.py default)"
    city_label.config(text="City: " + describe_city() + hint)


def after_city_change():
    """Reset the screen after a new city has been built."""
    state["place"] = None
    state["plan"] = None
    show_city_info()
    write(["NEW CITY: " + describe_city(), ""] + city_summary_lines())
    draw_map()


def on_new_city():
    """NEW RANDOM CITY button."""
    if state["in_call"]:
        return
    random_city(new_seed())
    after_city_change()


GOOGLE_BUTTON_TEXT = "GOOGLE TRAFFIC  (real city, needs your key)"


def google_progress(done, total):
    """Called after each Google request."""
    if state["closed"]:
        return
    if done % 5 == 0 or done == total:
        write(["Asking Google for traffic times...",
               str(done) + " of " + str(total) + " requests done.",
               "Press the button again to stop."])
    window.update()                   # keeps the window alive (and the stop button working)


def on_google_traffic():
    """GOOGLE TRAFFIC button: replace the modelled times with Google's."""
    if state["fetching"]:
        state["google_stop"] = True       # the running fetch will notice this
        return
    if city_info["kind"] != "real":
        write(["Google traffic works only in the real city.",
               "Press REAL BANGALORE first."])
        return
    key = google_traffic.get_key()
    if key is None:
        write(["No Google key was found.",
               "1. In the Google Cloud console, create an API key and enable the",
               "   Routes API (billing must be switched on).",
               "2. Store it in the environment variable GOOGLE_MAPS_API_KEY, for",
               "   example in PowerShell:  setx GOOGLE_MAPS_API_KEY \"your-key\"",
               "3. Close and reopen the terminal, then start this program again.",
               "Never paste the key into this program, a file or a chat."])
        return
    count = google_traffic.count_requests()
    question = ("This sends about " + str(count) + " Google Routes API requests "
                "(traffic-aware).\n\nThey are BILLABLE beyond Google's free monthly "
                "allowance. Set a budget alert in your Google Cloud console first.\n\n"
                "The times are kept in memory only; nothing from Google is saved.\n\n"
                "Continue?")
    if not messagebox.askyesno("Google Maps Platform", question):
        return

    state["fetching"] = True
    state["google_stop"] = False
    google_button.config(text="STOP GOOGLE TRAFFIC")
    write(["Asking Google for traffic times..."])
    result = None
    problem = None
    try:
        result = google_traffic.fetch_traffic(
            key, google_progress, lambda: state["google_stop"] or state["closed"])
    except google_traffic.GoogleError as error:
        problem = str(error)
    state["fetching"] = False
    state["google_stop"] = False
    if state["closed"]:
        return                            # the window is gone: touch nothing
    google_button.config(text=GOOGLE_BUTTON_TEXT)

    google_roads = 0
    for a, b, option in google_traffic.road_options():
        if option["source"] == "google":
            google_roads = google_roads + 1
    city_info["google_roads"] = google_roads
    lines = []
    if problem is not None:
        lines = ["Google problem: " + problem, "The roads that were not updated keep their modelled times.", ""]
    elif result["stopped"]:
        lines = ["Stopped. Roads done so far keep Google's times.", ""]
    if result is not None:
        lines = lines + ["Google traffic times now used for " + str(google_roads) + " of "
                         + str(len(google_traffic.road_options())) + " roads.",
                         "Kept modelled times: " + str(result["different_road"])
                         + " roads where Google used a different road, "
                         + str(result["no_route"]) + " with no route.",
                         "Requests sent: " + str(result["requests"]) + "."]
    write(lines)
    show_city_info()
    draw_map()


def on_real_city():
    """REAL BANGALORE button."""
    if state["in_call"]:
        return
    try:
        real_city(new_seed())
    except FileNotFoundError:
        write(["bangalore_city.json was not found.",
               "Run  python build_real_city.py  once (it needs the internet),",
               "then press this button again."])
        return
    after_city_change()


def on_default_city():
    """DEFAULT CITY button."""
    if state["in_call"]:
        return
    default_city()
    after_city_change()


def on_close():
    """The window's X button: stop any voice call, then close."""
    state["stop"] = True
    state["closed"] = True
    window.destroy()


def on_voice_call():
    """The VOICE CALL button: ask everything aloud, then dispatch.
    Pressing it again during a call stops the call."""
    if state["in_call"]:
        state["stop"] = True          # the running call will notice this
        return
    if city_info["kind"] == "real" and state["place"] is None:
        write(["In the real city, click the emergency's junction on the map first.",
               "Then press VOICE CALL: it asks the time and the six questions aloud.",
               "(Road names are too hard for the voice recogniser.)"])
        return
    state["in_call"] = True
    voice_button.config(text="STOP VOICE CALL")
    missed = []                       # questions that were not understood

    write(["VOICE CALL in progress...",
           "Wait for the beep, then answer.",
           "Time: say it like 'nine A M' or 'six P M'.",
           "Questions: answer 'yes' or 'no'."])
    voice.speak("One one two emergency.", keep_window_alive)

    # 1. the time
    hour = voice.ask_hour("What is the time now?", keep_window_alive)
    if state["stop"]:
        end_voice_call()
        return
    if hour is None:
        missed.append("time")
    else:
        hour_slider.set(hour)
    draw_map()

    # 2. the place (in the real city it was chosen by clicking the map,
    # because road names like "9th Cross Rd & Ayodhyarama Rd" are too
    # hard for the voice recogniser)
    if city_info["kind"] == "real":
        place = state["place"]
    else:
        place = voice.ask_place("Where is the emergency?", places, keep_window_alive)
    if state["stop"]:
        end_voice_call()
        return
    if place is None:
        missed.append("location")
    else:
        state["place"] = place
    draw_map()

    # 3. the six triage questions
    for key, question, usual in triage_questions:
        answer = voice.ask_yes_no(question, keep_window_alive)
        if state["stop"]:
            end_voice_call()
            return
        if answer is None:
            missed.append(key)
        else:
            answer_boxes[key].set(int(answer))
        on_answer_change()

    # 4. dispatch, unless something important was missed
    end_voice_call()
    if len(missed) > 0:
        write(["I could not understand: " + ", ".join(missed) + ".",
               "Please set those on the screen, then press DISPATCH."])
        voice.speak("I could not understand everything. Please check the screen.",
                    keep_window_alive)
        return

    calls_before = state["calls"]
    on_dispatch()
    if state["calls"] == calls_before:
        voice.speak("All ambulances are busy right now.", keep_window_alive)
    else:
        plan = state["plan"]
        text = ("Ambulance " + plan["ambulance"][-1] + " is on the way to "
                + voice.spoken_name(place) + ". It will arrive in about "
                + str(plan["average"]) + " minutes.")
        if plan["hospital"] is not None:
            text = text + " The patient will be taken to " + plan["hospital"] + "."
        else:
            text = text + " No hospital can treat this case right now. Please check the screen."
        voice.speak(text, keep_window_alive)


# ---------------------------------------------------------------------
# PART 4: BUILDING THE WINDOW
# ---------------------------------------------------------------------
start_city()                      # choose the city (random unless told otherwise)
window = tk.Tk()
window.title("112 Emergency Response - Dispatch Console")

# left side: the map
canvas = tk.Canvas(window, width=860, height=710, bg="#f4f6f8")
canvas.pack(side="left", padx=8, pady=8)
canvas.bind("<Button-1>", on_map_click)

# right side: the controls
panel = tk.Frame(window)
panel.pack(side="right", fill="y", padx=8, pady=8)

tk.Label(panel, text="112 DISPATCH CONSOLE", font=("Segoe UI", 15, "bold"),
         fg="#b00020").pack(anchor="w")

city_label = tk.Label(panel, text="", font=("Segoe UI", 9), fg="#555555",
                      wraplength=470, justify="left")
city_label.pack(anchor="w")

time_label = tk.Label(panel, text="", font=("Segoe UI", 11, "bold"))
time_label.pack(anchor="w", pady=(10, 0))
hour_slider = tk.Scale(panel, from_=0, to=23, orient="horizontal", length=380,
                       label="Hour of the day")
hour_slider.set(9)
hour_slider.pack(anchor="w")

show_labels = tk.IntVar(value=0)
tk.Checkbutton(panel, text="Show every road's name and times (real city)",
               variable=show_labels, command=lambda: draw_map()).pack(anchor="w")

place_label = tk.Label(panel, text="", font=("Segoe UI", 11, "bold"))
place_label.pack(anchor="w", pady=(10, 0))

# the triage questions: a ticked box means the caller answered YES
tk.Label(panel, text="Ask the caller (tick = yes):").pack(anchor="w", pady=(8, 0))
answer_boxes = {}                 # key -> the tick box's value (1 or 0)
for key, question, usual in triage_questions:
    answer_boxes[key] = tk.IntVar(value=int(usual))
    tk.Checkbutton(panel, text=question, variable=answer_boxes[key],
                   command=on_answer_change).pack(anchor="w")

priority_label = tk.Label(panel, text="", font=("Segoe UI", 10, "bold"), justify="left")
priority_label.pack(anchor="w", pady=(6, 0))
on_answer_change()

tk.Button(panel, text="DISPATCH", font=("Segoe UI", 13, "bold"), bg="#b00020",
          fg="white", command=on_dispatch).pack(fill="x", pady=(8, 4))
voice_button = tk.Button(panel, text=VOICE_BUTTON_TEXT, font=("Segoe UI", 10, "bold"),
                         command=on_voice_call)
voice_button.pack(fill="x", pady=(0, 4))

city_row = tk.Frame(panel)
city_row.pack(fill="x", pady=(0, 8))
tk.Button(city_row, text="RANDOM CITY", command=on_new_city).pack(
    side="left", expand=True, fill="x", padx=(0, 4))
tk.Button(city_row, text="DEFAULT CITY", command=on_default_city).pack(
    side="left", expand=True, fill="x", padx=(0, 4))
tk.Button(city_row, text="REAL BANGALORE", command=on_real_city).pack(
    side="left", expand=True, fill="x")
google_button = tk.Button(panel, text=GOOGLE_BUTTON_TEXT, command=on_google_traffic)
google_button.pack(fill="x", pady=(0, 8))
window.protocol("WM_DELETE_WINDOW", on_close)     # what the X button does

message_box = tk.Text(panel, width=62, height=12, font=("Consolas", 9), wrap="word")
scroll_bar = tk.Scrollbar(panel, command=message_box.yview)
message_box.config(yscrollcommand=scroll_bar.set)
scroll_bar.pack(side="right", fill="y")
message_box.pack(side="left")

write(["Click a junction on the map to place an emergency.",
       "Click a road to block it or open it again.",
       "Click a busy ambulance when it is back in service.",
       "Move the slider to change the time of day.",
       ""] + city_summary_lines())
show_city_info()
draw_map()
hour_slider.config(command=on_time_change)    # redraw when the slider moves
window.mainloop()
