# =====================================================================
#  GUI - the desktop window (tkinter, which comes with Python)
# =====================================================================
#  Left  : a real map of Jayanagar drawn from OpenStreetMap data.
#          Click a junction to say where the emergency is, click a road
#          to close or open it, click a grey ambulance when it is free.
#  Right : tabs for Dispatch (time, triage questions, result), Fleet
#          (ambulances and hospital beds) and Log (the calls handled).
#
#  The window is built from plain functions and one dictionary, `app`,
#  that remembers everything the window needs.
# =====================================================================

import csv
import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ambulance import __version__, dispatch, mapdata, routing, triage, voice

app = {}                # everything the window needs to remember
view = {}               # how latitude / longitude become pixels
positions = {}          # junction name -> (x, y) on the map
clickable = {}          # canvas item -> ("place" | "road" | "ambulance" | "hospital", name or id)
placed_boxes = []       # boxes of the labels already drawn (so new labels avoid them)

CANVAS_WIDTH = 820
CANVAS_HEIGHT = 720
PRIORITY_COLOURS = {1: "#b00020", 2: "#c77700", 3: "#2a7d3f"}
GREY, BLUE, GREEN, RED = "#9aa0a6", "#1d6fd8", "#2a9d3f", "#d62828"


# ---------------------------------------------------------------------
# PART 1: TIME
# ---------------------------------------------------------------------
def current_clock():
    """The time used for routing: the real time in Bangalore, or the hour
    chosen on the slider."""
    if app["use_now"].get() == 1:
        return dispatch.now_minutes()
    return app["hour"].get() * 60


def update_clock_label():
    clock = current_clock()
    app["clock_label"].config(text="Time " + dispatch.show_clock(clock) + "   ("
                              + dispatch.get_period(clock) + " traffic)")
    app["hour"].config(state="disabled" if app["use_now"].get() == 1 else "normal")


def on_time_change(*ignored):
    update_clock_label()
    draw_map()


def tick():
    """Every 20 seconds: keep the clock right when it follows real time."""
    if app["closed"]:
        return
    if app["use_now"].get() == 1:
        update_clock_label()
    app["root"].after(20000, tick)


# ---------------------------------------------------------------------
# PART 2: DRAWING THE MAP
# ---------------------------------------------------------------------
def setup_view():
    """Work out how to turn latitude and longitude into pixels so that the
    whole area fits in the window."""
    world = app["world"]
    lats, lngs = [], []
    for junction in world["junctions"].values():
        lats.append(junction["lat"])
        lngs.append(junction["lng"])
    for hospital in world["hospitals"].values():
        lats.append(hospital["lat"])
        lngs.append(hospital["lng"])
    for road in world["roads"].values():
        for lat, lng in road["shape"]:
            lats.append(lat)
            lngs.append(lng)
    view["north"] = max(lats)
    view["west"] = min(lngs)
    view["cos"] = math.cos(math.radians((min(lats) + max(lats)) / 2))
    width_m = (max(lngs) - min(lngs)) * 111320 * view["cos"]
    height_m = (max(lats) - min(lats)) * 110574
    scale = min((CANVAS_WIDTH - 210) / width_m, (CANVAS_HEIGHT - 150) / height_m)
    view["scale"] = scale
    view["left"] = (CANVAS_WIDTH - width_m * scale) / 2
    view["top"] = 70 + ((CANVAS_HEIGHT - 150) - height_m * scale) / 2


def project(lat, lng):
    """Latitude and longitude -> (x, y) pixels on the map."""
    x = view["left"] + (lng - view["west"]) * 111320 * view["cos"] * view["scale"]
    y = view["top"] + (view["north"] - lat) * 110574 * view["scale"]
    return x, y


def box_is_free(box):
    canvas = app["canvas"]
    if box[0] < 2 or box[1] < 2 or box[2] > CANVAS_WIDTH - 2 or box[3] > CANVAS_HEIGHT - 24:
        return False                     # it would run off the map
    for other in placed_boxes:
        if not (box[2] < other[0] or box[0] > other[2] or box[3] < other[1] or box[1] > other[3]):
            return False
    return True


def place_text(x, y, text, colour, size, gap, background="white", bold=False):
    """Write a label next to the point (x, y), at the first spot where it
    does not cover another label. Returns the two canvas items."""
    canvas = app["canvas"]
    # (anchor, dx, dy): the label goes right, left, above, below, then the corners
    spots = [("w", gap, 0), ("e", -gap, 0), ("s", 0, -gap), ("n", 0, gap),
             ("sw", gap, -gap), ("se", -gap, -gap), ("nw", gap, gap), ("ne", -gap, gap)]
    weight = "bold" if bold else "normal"
    chosen, box = None, None
    for anchor, dx, dy in spots:
        item = canvas.create_text(x + dx, y + dy, text=text, fill=colour, anchor=anchor,
                                  font=("Segoe UI", size, weight))
        box = canvas.bbox(item)
        if box_is_free(box):
            chosen = item
            break
        canvas.delete(item)
    if chosen is None:                   # nowhere is free: use the first spot anyway
        anchor, dx, dy = spots[0]
        chosen = canvas.create_text(x + dx, y + dy, text=text, fill=colour, anchor=anchor,
                                    font=("Segoe UI", size, weight))
        box = canvas.bbox(chosen)
    placed_boxes.append(box)
    background_box = canvas.create_rectangle(box, fill=background, outline="")
    canvas.tag_raise(chosen, background_box)
    return background_box, chosen


def short_hospital_name(name):
    """A shorter name for the map label."""
    for word in [" Hospitals", " Hospital", " Multispeciality", " Speciality", " Foundation",
                 " and", " Of ", "Institute"]:
        name = name.replace(word, " ")
    name = " ".join(name.split())
    return name if len(name) <= 20 else name[:19] + "."


def draw_roads():
    world = app["world"]
    canvas = app["canvas"]
    period = dispatch.get_period(current_clock())
    plan = app["plan"]
    to_patient = routing.route_road_ids(plan["route1"]) if plan else set()
    to_hospital = routing.route_road_ids(plan["route2"]) if plan else set()
    show_all = app["show_labels"].get() == 1

    drawn = []
    for road in mapdata.roads_list(world):
        if road["id"] in world["blocked"]:
            colour, width = RED, 5
        elif road["id"] in to_patient:
            colour, width = BLUE, 6
        elif road["id"] in to_hospital:
            colour, width = GREEN, 6
        else:
            colour, width = GREY, 3
        points = []
        for lat, lng in road["shape"]:
            x, y = project(lat, lng)
            points.append(x)
            points.append(y)
        drawn.append((colour, width, points, road))

    labels = []
    for special in [False, True]:                  # grey roads first, so routes are on top
        for colour, width, points, road in drawn:
            if (colour != GREY) != special:
                continue
            line = canvas.create_line(*points, fill=colour, width=width,
                                      capstyle="round", joinstyle="round")
            clickable[line] = ("road", road["id"])
            if special or show_all:
                middle = len(points) // 4 * 2
                average, extra = road["times"][period]
                text = road["name"] + "  " + str(average) + "+" + str(extra)
                if road["id"] in world["blocked"]:
                    text = road["name"] + "  CLOSED"
                labels.append((points[middle], points[middle + 1], text))
    for x, y, text in labels:
        item = canvas.create_text(x, y, text=text, fill="#333333", font=("Segoe UI", 7))
        canvas.create_rectangle(canvas.bbox(item), fill="white", outline="")
        canvas.tag_raise(item)


def draw_markers():
    """Junctions, hospitals and ambulances (and their labels)."""
    world = app["world"]
    canvas = app["canvas"]
    placed_boxes.clear()

    # junction circles first, so that labels keep clear of them
    for name in sorted(world["junctions"]):
        x, y = positions[name]
        if name == app["place"]:
            fill, edge, width = "#ffd6d6", RED, 3
        else:
            fill, edge, width = "#ffffff", "#333333", 2
        circle = canvas.create_oval(x - 7, y - 7, x + 7, y + 7, fill=fill, outline=edge, width=width)
        clickable[circle] = ("place", name)
        placed_boxes.append((x - 8, y - 8, x + 8, y + 8))

    # hospitals sit at their real position, with a dotted line to their junction
    hospital_points = {}
    for name in sorted(world["hospitals"]):
        hospital = world["hospitals"][name]
        x, y = project(hospital["lat"], hospital["lng"])
        jx, jy = positions[hospital["junction"]]
        canvas.create_line(x, y, jx, jy, fill="#e08a96", dash=(2, 3))
        colour = "#b00020" if hospital["beds_free"] > 0 else "#9a9a9a"
        marker = canvas.create_rectangle(x - 5, y - 5, x + 5, y + 5, fill=colour, outline="white")
        cross = canvas.create_text(x, y, text="+", fill="white", font=("Segoe UI", 9, "bold"))
        clickable[marker] = ("hospital", name)
        clickable[cross] = ("hospital", name)
        placed_boxes.append((x - 6, y - 6, x + 6, y + 6))
        hospital_points[name] = (x, y)

    for name in sorted(world["junctions"]):
        x, y = positions[name]
        label = name.replace(" & ", "\n& ")
        background, text = place_text(x, y, label, "#111111", 8, 10, bold=True)
        clickable[background] = ("place", name)
        clickable[text] = ("place", name)

    for name in sorted(world["hospitals"]):
        hospital = world["hospitals"][name]
        x, y = hospital_points[name]
        colour = "#b00020" if hospital["beds_free"] > 0 else "#777777"
        text = short_hospital_name(name) + " (" + str(hospital["beds_free"]) + ")"
        background, label = place_text(x, y, text, colour, 7, 9)
        clickable[background] = ("hospital", name)
        clickable[label] = ("hospital", name)

    for name in sorted(world["ambulances"]):
        ambulance = world["ambulances"][name]
        x, y = positions[ambulance["at"]]
        short = "A" + name.split()[-1]
        if ambulance["busy"]:
            colour, text = "#c8c8c8", short + " busy"
        else:
            colour, text = "#ffd23f", short
        background, label = place_text(x, y, text, "#111111", 7, 11, background=colour)
        clickable[background] = ("ambulance", name)
        clickable[label] = ("ambulance", name)


def draw_map():
    """Wipe the map and draw everything again."""
    canvas = app["canvas"]
    canvas.delete("all")
    clickable.clear()
    setup_view()
    positions.clear()
    for name, junction in app["world"]["junctions"].items():
        positions[name] = project(junction["lat"], junction["lng"])
    draw_roads()
    draw_markers()
    if app["world"]["sample_survey"]:
        survey_text = "Hospital beds and facilities are SAMPLE data."
    else:
        survey_text = "Hospital beds and facilities come from data/survey.json."
    canvas.create_text(CANVAS_WIDTH / 2, CANVAS_HEIGHT - 20, fill="#555555", font=("Segoe UI", 8),
                       text="Map data (c) OpenStreetMap contributors (ODbL). Travel times are MODELLED. "
                            + survey_text)
    canvas.create_text(CANVAS_WIDTH / 2, CANVAS_HEIGHT - 8, fill="#555555", font=("Segoe UI", 8),
                       text="Blue: route to the patient   Green: route to the hospital   "
                            "Red: closed road   Red + : hospital (number = free beds)")
    if app["place"] is None:
        app["place_label"].config(text="Emergency at: (click a junction on the map)")
    else:
        app["place_label"].config(text="Emergency at: " + app["place"])


# ---------------------------------------------------------------------
# PART 3: CLICKS ON THE MAP
# ---------------------------------------------------------------------
def say(text):
    """A line in the status bar under the map."""
    app["status"].config(text=text)


def on_map_click(event):
    canvas = app["canvas"]
    world = app["world"]
    items = canvas.find_overlapping(event.x - 4, event.y - 4, event.x + 4, event.y + 4)
    # when several things are under the mouse: ambulances, hospitals, junctions, then roads
    found = None
    for wanted in ["ambulance", "hospital", "place", "road"]:
        for item in items:
            if found is None and item in clickable and clickable[item][0] == wanted:
                found = clickable[item]
    if found is None:
        return
    kind, value = found

    if kind == "place":
        app["place"] = value
        say("Emergency location: " + value)
    elif kind == "road":
        road = world["roads"][value]
        if value in world["blocked"]:
            world["blocked"].remove(value)
            say(road["name"] + " is open again.")
        else:
            world["blocked"].add(value)
            say(road["name"] + " is now CLOSED. Routes will avoid it.")
    elif kind == "ambulance":
        ambulance = world["ambulances"][value]
        if ambulance["busy"]:
            dispatch.finish_job(world, value)
            say(value + " is back in service at " + ambulance["at"] + ".")
            refresh_fleet()
        else:
            say(value + " is free at " + ambulance["at"] + ".")
    elif kind == "hospital":
        hospital = world["hospitals"][value]
        facilities = [triage.FACILITY_NAMES[f] for f in sorted(hospital["facilities"])]
        source = " (SAMPLE survey)" if world["sample_survey"] else ""
        say(value + ": " + str(hospital["beds_free"]) + " free beds, wait " + str(hospital["wait"])
            + " min, has " + ", ".join(facilities) + source)
    draw_map()


# ---------------------------------------------------------------------
# PART 4: TRIAGE AND DISPATCH
# ---------------------------------------------------------------------
def read_answers():
    answers = {}
    for key in app["answers"]:
        answers[key] = app["answers"][key].get() == 1
    return answers


def on_answer_change():
    """Show the priority as soon as an answer is ticked or unticked."""
    result = triage.triage(read_answers())
    needs = ", ".join(triage.FACILITY_NAMES[f]
                      for f in triage.required_facilities(result["care"], result["priority"]))
    app["priority_label"].config(
        fg=PRIORITY_COLOURS[result["priority"]],
        text=triage.PRIORITY_NAMES[result["priority"]] + "\nHospital needs: " + needs
             + "   (" + ", ".join(result["why"]) + ")")


def write_result(lines, title=None):
    box = app["result"]
    box.config(state="normal")
    box.delete("1.0", "end")
    if title is not None:
        box.insert("end", title + "\n", "title")
    for line in lines:
        box.insert("end", line + "\n")
    box.config(state="disabled")


def on_dispatch():
    """The DISPATCH button."""
    world = app["world"]
    place = app["place"]
    if place is None:
        messagebox.showinfo("Emergency location", "First click the emergency's junction on the map.")
        return False
    result = triage.triage(read_answers())
    clock = current_clock()
    plan, reasons = dispatch.plan_dispatch(world, place, result, clock)
    if plan is None:
        app["plan"] = None
        write_result(reasons + ["", "!! NO AMBULANCE CAN REACH THE PATIENT.",
                                "All ambulances are busy or the roads are closed.",
                                "Free an ambulance (click it on the map or use the Fleet tab)."],
                     "NO AMBULANCE AVAILABLE")
        draw_map()
        return False

    baseline = dispatch.nearest_baseline(world, place, result["care"], result["priority"], plan["period"])
    entry = dispatch.commit_dispatch(world, plan)
    app["plan"] = plan

    route1, route2 = plan["route1"], plan["route2"]
    lines = [triage.PRIORITY_NAMES[plan["priority"]] + "  (" + ", ".join(plan["why"]) + ")", ""]
    lines.append("SEND     : " + plan["ambulance"])
    lines.append("ROUTE    : " + routing.describe_route(route1))
    lines.append("ARRIVES  : in " + str(route1["average"]) + " min (worst case " + str(route1["worst"]) + " min)")
    lines.append("")
    if plan["hospital"] is None:
        lines.append("HOSPITAL : !! NONE can treat this case right now. Call the hospitals directly.")
    else:
        hospital = world["hospitals"][plan["hospital"]]
        lines.append("TAKE TO  : " + plan["hospital"])
        lines.append("ROUTE    : " + routing.describe_route(route2))
        total = (route1["average"] + dispatch.SCENE_TIME + route2["average"]
                 + dispatch.access_minutes(hospital) + hospital["wait"])
        lines.append("TIME     : about " + str(round(total)) + " min until treatment starts "
                     "(drive " + str(route1["average"]) + " + scene " + str(dispatch.SCENE_TIME)
                     + " + drive " + str(route2["average"]) + " + door "
                     + str(dispatch.access_minutes(hospital)) + " + wait " + str(hospital["wait"]) + ")")
    lines.append("")
    if baseline["ambulance"] is not None:
        text = ("COMPARE  : a plain 'nearest' rule would send " + baseline["ambulance"] + " ("
                + str(baseline["average"]) + " min, worst " + str(baseline["worst"]) + ")")
        if baseline["hospital"] is not None:
            if len(baseline["missing"]) == 0:
                text = text + " to " + baseline["hospital"]
            else:
                text = text + " to " + baseline["hospital"] + " - WRONG: " + ", ".join(baseline["missing"])
        lines.append(text)
    lines.append("")
    lines.append("WHY:")
    lines = lines + reasons
    write_result(lines, "DISPATCH ORDER " + entry["id"] + "   " + entry["time"] + "   "
                 + plan["care"] + " at " + place)
    say(entry["id"] + ": " + plan["ambulance"] + " sent.")
    refresh_fleet()
    refresh_log()
    draw_map()
    return True


# ---------------------------------------------------------------------
# PART 5: THE VOICE CALL
# ---------------------------------------------------------------------
VOICE_TEXT = "VOICE CALL  (ask the questions aloud)"


def keep_alive():
    """Called while the computer is speaking or listening. Returns False
    if the call must stop (STOP pressed or window closed)."""
    if app["closed"]:
        return False
    app["root"].update()
    return not (app["closed"] or app["stop"])


def end_voice_call():
    stopped = app["stop"]
    app["in_call"] = False
    app["stop"] = False
    if app["closed"]:
        return
    app["voice_button"].config(text=VOICE_TEXT)
    if stopped:
        say("Voice call stopped.")


def on_voice_call():
    """Ask the six triage questions aloud, fill in the answers, dispatch,
    and say the result. Pressing the button again stops the call."""
    if app["in_call"]:
        app["stop"] = True
        return
    if not voice.available():
        messagebox.showinfo("Voice call", "Spoken questions need Windows. Use the tick boxes instead.")
        return
    if app["place"] is None:
        messagebox.showinfo("Voice call", "First click the emergency's junction on the map.\n"
                            "The voice call then asks the six triage questions aloud.")
        return
    app["in_call"] = True
    app["voice_button"].config(text="STOP VOICE CALL")
    missed = []
    voice.speak("One one two emergency.", keep_alive)
    for key, question, usual in triage.QUESTIONS:
        answer = voice.ask_yes_no(question, keep_alive)
        if app["stop"] or app["closed"]:
            end_voice_call()
            return
        if answer is None:
            missed.append(key)
        else:
            app["answers"][key].set(int(answer))
            on_answer_change()
    end_voice_call()
    if app["closed"]:
        return
    if len(missed) > 0:
        say("Voice call: could not understand " + ", ".join(missed) + ". Set those by hand.")
        voice.speak("I could not understand everything. Please check the screen.", keep_alive)
        return
    if on_dispatch():
        plan = app["plan"]
        text = ("Ambulance " + plan["ambulance"].split()[-1] + " is on the way to "
                + voice.spoken(plan["place"]) + ". It will arrive in about "
                + str(round(plan["route1"]["average"])) + " minutes.")
        if plan["hospital"] is not None:
            text = text + " The patient will be taken to " + plan["hospital"] + "."
        else:
            text = text + " No hospital can treat this case right now. Please check the screen."
        voice.speak(text, keep_alive)
    else:
        voice.speak("No ambulance is available right now.", keep_alive)


# ---------------------------------------------------------------------
# PART 6: THE FLEET AND LOG TABS
# ---------------------------------------------------------------------
def refresh_fleet():
    world = app["world"]
    table = app["ambulance_table"]
    table.delete(*table.get_children())
    for name in sorted(world["ambulances"]):
        ambulance = world["ambulances"][name]
        if ambulance["busy"]:
            status = "on call -> " + (ambulance["job"]["hospital"] or "no hospital")
        else:
            status = "free"
        table.insert("", "end", iid=name, values=(name, ambulance["at"], status))
    table = app["hospital_table"]
    table.delete(*table.get_children())
    for name in sorted(world["hospitals"]):
        hospital = world["hospitals"][name]
        facilities = ", ".join(f for f in sorted(hospital["facilities"]) if f != "general")
        table.insert("", "end", iid=name, values=(name, hospital["beds_free"], hospital["wait"],
                                                  facilities if facilities else "general only"))


def selected(table):
    chosen = table.selection()
    return chosen[0] if len(chosen) > 0 else None


def on_free_ambulance():
    name = selected(app["ambulance_table"])
    if name is None:
        say("Select an ambulance in the table first.")
        return
    if app["world"]["ambulances"][name]["busy"]:
        dispatch.finish_job(app["world"], name)
        say(name + " is back in service.")
    refresh_fleet()
    draw_map()


def on_change_beds(change):
    name = selected(app["hospital_table"])
    if name is None:
        say("Select a hospital in the table first.")
        return
    hospital = app["world"]["hospitals"][name]
    hospital["beds_free"] = max(0, hospital["beds_free"] + change)
    refresh_fleet()
    app["hospital_table"].selection_set(name)
    draw_map()


def on_reset_all():
    if not messagebox.askyesno("Reset everything",
                               "Free all ambulances, open all roads, restore the surveyed beds "
                               "and clear the call log?"):
        return
    mapdata.reset_world(app["world"])
    app["plan"] = None
    write_result(["Everything was reset."], "RESET")
    refresh_fleet()
    refresh_log()
    draw_map()


def refresh_log():
    table = app["log_table"]
    table.delete(*table.get_children())
    for entry in app["world"]["log"]:
        table.insert("", "end", values=(entry["id"], entry["time"], entry["place"], entry["care"],
                                        entry["priority"], entry["ambulance"], entry["hospital"],
                                        entry["minutes_to_patient"]))


def on_save_log():
    path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="call_log.csv",
                                        filetypes=[("CSV file", "*.csv")])
    if path == "":
        return
    columns = ["id", "time", "place", "care", "priority", "ambulance", "hospital",
               "minutes_to_patient", "worst_minutes_to_patient"]
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for entry in app["world"]["log"]:
            writer.writerow(entry)
    say("Saved " + str(len(app["world"]["log"])) + " calls to " + path)


# ---------------------------------------------------------------------
# PART 7: MENUS AND HELP
# ---------------------------------------------------------------------
def show_about():
    world = app["world"]
    if world["sample_survey"]:
        survey_line = "SAMPLE: hospital beds, waiting times, facilities and ambulance stations.\n\n"
    else:
        survey_line = "Survey: hospital beds, facilities and stations from data/survey.json.\n\n"
    messagebox.showinfo(
        "About",
        "Ambulance Dispatch - Jayanagar, Bangalore   version " + __version__ + "\n\n"
        "Picks the ambulance, the route and the hospital for an emergency.\n\n"
        "Routing: the Dijkstar library (Dijkstra's algorithm) on a multigraph of real roads.\n"
        + world["attribution"] + "\n\n"
        "Real: junctions, roads, road names and lengths, hospital names and positions.\n"
        "Modelled: travel times.\n"
        + survey_line +
        "This is a prototype and not a medical or emergency-service tool.")


def show_how_it_works():
    messagebox.showinfo(
        "How it works",
        "1. Click the emergency's junction on the map.\n"
        "2. Tick the answers the caller gives to the six questions.\n"
        "   They give a priority: 1 life-threatening, 2 urgent, 3 not urgent.\n"
        "3. Press DISPATCH.\n\n"
        "Priority 1 uses the most RELIABLE roads (usual time plus possible delay),\n"
        "priority 3 the fastest roads on average.\n"
        "A hospital is only chosen if it has the facilities the case needs and a free bed.\n\n"
        "Click a road to close it, and a grey ambulance to put it back in service.")


def build_menu(root):
    menubar = tk.Menu(root)
    file_menu = tk.Menu(menubar, tearoff=0)
    file_menu.add_command(label="Save call log...", command=on_save_log)
    file_menu.add_command(label="Reset everything", command=on_reset_all)
    file_menu.add_separator()
    file_menu.add_command(label="Quit", command=on_close)
    menubar.add_cascade(label="File", menu=file_menu)
    view_menu = tk.Menu(menubar, tearoff=0)
    view_menu.add_checkbutton(label="Show every road's name and times",
                              variable=app["show_labels"], command=draw_map)
    menubar.add_cascade(label="View", menu=view_menu)
    help_menu = tk.Menu(menubar, tearoff=0)
    help_menu.add_command(label="How it works", command=show_how_it_works)
    help_menu.add_command(label="About", command=show_about)
    menubar.add_cascade(label="Help", menu=help_menu)
    root.config(menu=menubar)


def on_close():
    app["stop"] = True
    app["closed"] = True
    app["root"].destroy()


# ---------------------------------------------------------------------
# PART 8: BUILDING THE WINDOW
# ---------------------------------------------------------------------
def build_window(world):
    """Create the window for a world. Returns the `app` dictionary."""
    app.clear()
    root = tk.Tk()
    root.title("Ambulance Dispatch - Jayanagar, Bangalore")
    app.update({"root": root, "world": world, "place": None, "plan": None,
                "stop": False, "closed": False, "in_call": False})
    app["use_now"] = tk.IntVar(value=1)
    app["show_labels"] = tk.IntVar(value=0)
    root.protocol("WM_DELETE_WINDOW", on_close)
    build_menu(root)

    # ---- left: the map
    left = tk.Frame(root)
    left.pack(side="left", padx=8, pady=8)
    app["canvas"] = tk.Canvas(left, width=CANVAS_WIDTH, height=CANVAS_HEIGHT, bg="#f4f6f8",
                              highlightthickness=1, highlightbackground="#c8ccd0")
    app["canvas"].pack()
    app["canvas"].bind("<Button-1>", on_map_click)
    app["status"] = tk.Label(left, text="Click a junction to place an emergency.", anchor="w",
                             fg="#333333", font=("Segoe UI", 9))
    app["status"].pack(fill="x", pady=(4, 0))

    # ---- right: tabs
    notebook = ttk.Notebook(root)
    notebook.pack(side="right", fill="both", padx=(0, 8), pady=8)
    dispatch_tab = tk.Frame(notebook)
    fleet_tab = tk.Frame(notebook)
    log_tab = tk.Frame(notebook)
    notebook.add(dispatch_tab, text="  Dispatch  ")
    notebook.add(fleet_tab, text="  Fleet  ")
    notebook.add(log_tab, text="  Log  ")

    # -- Dispatch tab
    tk.Label(dispatch_tab, text="112 DISPATCH", font=("Segoe UI", 15, "bold"),
             fg="#b00020").pack(anchor="w", padx=8, pady=(8, 0))
    app["clock_label"] = tk.Label(dispatch_tab, text="", font=("Segoe UI", 11, "bold"))
    app["clock_label"].pack(anchor="w", padx=8, pady=(6, 0))
    tk.Checkbutton(dispatch_tab, text="Use the current time in Bangalore",
                   variable=app["use_now"], command=on_time_change).pack(anchor="w", padx=8)
    app["hour"] = tk.Scale(dispatch_tab, from_=0, to=23, orient="horizontal", length=360,
                           label="Hour of the day (when not using the current time)",
                           command=on_time_change)
    app["hour"].set(9)
    app["hour"].pack(anchor="w", padx=8)

    app["place_label"] = tk.Label(dispatch_tab, text="", font=("Segoe UI", 10, "bold"),
                                  wraplength=400, justify="left")
    app["place_label"].pack(anchor="w", padx=8, pady=(6, 0))

    tk.Label(dispatch_tab, text="Ask the caller (tick = yes):").pack(anchor="w", padx=8, pady=(6, 0))
    app["answers"] = {}
    for key, question, usual in triage.QUESTIONS:
        app["answers"][key] = tk.IntVar(value=int(usual))
        tk.Checkbutton(dispatch_tab, text=question, variable=app["answers"][key],
                       command=on_answer_change).pack(anchor="w", padx=8)
    app["priority_label"] = tk.Label(dispatch_tab, text="", font=("Segoe UI", 10, "bold"),
                                     justify="left", wraplength=400)
    app["priority_label"].pack(anchor="w", padx=8, pady=(6, 0))

    tk.Button(dispatch_tab, text="DISPATCH", font=("Segoe UI", 13, "bold"), bg="#b00020",
              fg="white", command=on_dispatch).pack(fill="x", padx=8, pady=(8, 4))
    app["voice_button"] = tk.Button(dispatch_tab, text=VOICE_TEXT, font=("Segoe UI", 10, "bold"),
                                    command=on_voice_call)
    app["voice_button"].pack(fill="x", padx=8, pady=(0, 6))

    result_frame = tk.Frame(dispatch_tab)
    result_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    app["result"] = tk.Text(result_frame, width=52, height=15, font=("Consolas", 9), wrap="word",
                            state="disabled")
    scroll = tk.Scrollbar(result_frame, command=app["result"].yview)
    app["result"].config(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    app["result"].pack(side="left", fill="both", expand=True)
    app["result"].tag_config("title", font=("Consolas", 10, "bold"), foreground="#b00020")

    # -- Fleet tab
    tk.Label(fleet_tab, text="Ambulances", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=8, pady=(8, 0))
    app["ambulance_table"] = ttk.Treeview(fleet_tab, columns=("name", "at", "status"),
                                          show="headings", height=6, selectmode="browse")
    for column, title, width in [("name", "Ambulance", 100), ("at", "At junction", 210), ("status", "Status", 120)]:
        app["ambulance_table"].heading(column, text=title)
        app["ambulance_table"].column(column, width=width)
    app["ambulance_table"].pack(fill="x", padx=8)
    tk.Button(fleet_tab, text="Back in service", command=on_free_ambulance).pack(anchor="w", padx=8, pady=4)

    tk.Label(fleet_tab, text="Hospitals", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=8, pady=(8, 0))
    app["hospital_table"] = ttk.Treeview(fleet_tab, columns=("name", "beds", "wait", "has"),
                                         show="headings", height=14, selectmode="browse")
    for column, title, width in [("name", "Hospital", 170), ("beds", "Beds", 40),
                                 ("wait", "Wait", 40), ("has", "Facilities", 190)]:
        app["hospital_table"].heading(column, text=title)
        app["hospital_table"].column(column, width=width)
    app["hospital_table"].pack(fill="x", padx=8)
    buttons = tk.Frame(fleet_tab)
    buttons.pack(anchor="w", padx=8, pady=4)
    tk.Button(buttons, text="+ bed", command=lambda: on_change_beds(1)).pack(side="left", padx=(0, 4))
    tk.Button(buttons, text="- bed", command=lambda: on_change_beds(-1)).pack(side="left", padx=(0, 12))
    tk.Button(buttons, text="Reset everything", command=on_reset_all).pack(side="left")
    note = "Hospital names and positions are real (OpenStreetMap). Beds, waiting times and facilities are SAMPLE data."
    if not world["sample_survey"]:
        note = "Beds, waiting times and facilities come from data/survey.json."
    tk.Label(fleet_tab, text=note, wraplength=400, justify="left", fg="#7a5200").pack(anchor="w", padx=8, pady=4)

    # -- Log tab
    columns = [("id", "Call", 55), ("time", "Time", 45), ("place", "Place", 120), ("care", "Care", 55),
               ("priority", "Pri", 28), ("ambulance", "Ambulance", 75), ("hospital", "Hospital", 100),
               ("minutes", "Min", 35)]
    app["log_table"] = ttk.Treeview(log_tab, columns=[c[0] for c in columns], show="headings", height=28)
    for column, title, width in columns:
        app["log_table"].heading(column, text=title)
        app["log_table"].column(column, width=width)
    app["log_table"].pack(fill="both", expand=True, padx=8, pady=8)
    tk.Button(log_tab, text="Save log as CSV...", command=on_save_log).pack(anchor="w", padx=8, pady=(0, 8))

    write_result(["Click a junction on the map to place an emergency,",
                  "tick the caller's answers, and press DISPATCH.", "",
                  "Click a road to close or open it.",
                  "Click a grey ambulance when it is back in service."], "READY")
    on_answer_change()
    update_clock_label()
    refresh_fleet()
    refresh_log()
    draw_map()
    root.after(20000, tick)
    return app


def run():
    """Start the program."""
    world = mapdata.load_world()
    build_window(world)
    app["root"].mainloop()
