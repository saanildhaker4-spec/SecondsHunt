# =====================================================================
#  GOOGLE TRAFFIC - replaces the MODELLED travel times of the real
#  city with traffic-aware times from the Google Routes API
# =====================================================================
#  The map and the roads always come from OpenStreetMap. Google is used
#  for ONE thing only: how long each road link takes at night, in the
#  day and in the rush hour, with and without bad traffic.
#
#  HOW IT WORKS
#   For every road in the real city we ask the Google Routes API for the
#   drive from one junction to the other, forced along our road by a few
#   "via" points, at three departure times (02:00, 14:00, 09:00 on a
#   future weekday). We ask twice for each time:
#       BEST_GUESS  -> becomes the AVERAGE time of the road
#       PESSIMISTIC -> minus BEST_GUESS becomes the EXTRA (possible delay)
#
#  RULES THIS FILE FOLLOWS
#   - The API key is read from the environment variable GOOGLE_MAPS_API_KEY.
#     It is never typed into the program, printed or saved anywhere.
#   - Each request is BILLABLE beyond Google's free monthly allowance, so
#     the map window asks you to confirm the number of requests first.
#   - The answers are kept in MEMORY ONLY. Nothing from Google is written
#     to a file or to git, because Google's terms limit storing its data.
#   - If a Google route is much longer or shorter than our OpenStreetMap
#     road (so Google probably used a different road), that road keeps
#     its modelled times.
#   - Without a key, or without internet, nothing changes.
#
#  PLEASE CHECK Google's current Maps Platform terms yourself, including
#  the rules about using Google data with a map that is not a Google map.
# =====================================================================

import datetime
import json
import os
import time
import urllib.error
import urllib.request

from city_engine import *

API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
KEY_NAME = "GOOGLE_MAPS_API_KEY"

# the three traffic periods and the local (Bangalore) time we ask about
PERIOD_TIMES = {"night": (2, 0), "day": (14, 0), "rush": (9, 0)}
TRAFFIC_MODELS = ["BEST_GUESS", "PESSIMISTIC"]
MAX_DIFFERENCE = 0.30            # a Google route 30% longer or shorter is a different road


class GoogleError(Exception):
    """Something went wrong that makes it pointless to continue."""


def get_key():
    """The API key from the environment, or None. (Never print it.)"""
    key = os.environ.get(KEY_NAME, "").strip()
    if key == "":
        return None
    return key


def departure_time(hour, minute):
    """A time in the FUTURE on a weekday, as Google wants it, for example
    2026-11-17T09:00:00+05:30 (Bangalore time)."""
    bangalore = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    day = datetime.datetime.now(bangalore).date() + datetime.timedelta(days=2)
    while day.weekday() > 3:                 # Monday to Thursday only
        day = day + datetime.timedelta(days=1)
    moment = datetime.datetime(day.year, day.month, day.day, hour, minute, tzinfo=bangalore)
    return moment.isoformat()


def road_options():
    """Every road of the real city once: a list of (junction a, junction b, option)."""
    found = []
    for key in roads:
        a, b = key
        if a < b:
            for option in roads[key]:
                found.append((a, b, option))
    return found


def count_requests():
    """How many Google requests a full run sends."""
    return len(road_options()) * len(PERIOD_TIMES) * len(TRAFFIC_MODELS)


def lat_lng(point):
    return {"location": {"latLng": {"latitude": point[0], "longitude": point[1]}}}


def make_body(a, b, option, period, model):
    """The request for one road, one period and one traffic model."""
    hour, minute = PERIOD_TIMES[period]
    body = {
        "origin": lat_lng(geo[a]),
        "destination": lat_lng(geo[b]),
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "trafficModel": model,
        "departureTime": departure_time(hour, minute),
    }
    # up to three "via" points along our OpenStreetMap road, so that
    # Google drives along the same road and not another one
    shape = option["shape"]
    if shape is not None and len(shape) >= 5:
        via = []
        for part in [1, 2, 3]:
            via.append(dict(lat_lng(shape[len(shape) * part // 4]), via=True))
        body["intermediates"] = via
    return body


def post_json(body, key):
    """Send one request to Google and return the answer as a dictionary.
    (This is the only function that uses the internet, and the only one
    that sees the key. It puts the key in a header, never in the address.)"""
    request = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "X-Goog-Api-Key": key,
                 "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read().decode())["error"]["message"]
        except Exception:
            message = "no details"
        raise GoogleError("Google answered " + str(error.code) + ": " + message)
    except urllib.error.URLError:
        raise GoogleError("Could not reach Google (no internet?)")


def read_answer(answer):
    """(minutes, metres) from a Google answer, or None if it has no route."""
    routes = answer.get("routes", [])
    if len(routes) == 0:
        return None
    text = routes[0]["duration"]                 # for example "123s" or "123.5s"
    seconds = float(text.rstrip("s"))
    return seconds / 60.0, routes[0].get("distanceMeters", 0)


def fetch_traffic(key, progress, should_stop):
    """Ask Google for every road and update the travel times IN MEMORY.
    progress(done, total) is called after each request; should_stop() is
    asked before each one. Returns a dictionary with the results."""
    options = road_options()
    total = count_requests()
    done = 0
    result = {"applied": 0, "different_road": 0, "no_route": 0, "stopped": False, "requests": 0}

    for a, b, option in options:
        new_times = {}
        usable = True
        for period in PERIOD_TIMES:
            minutes = {}
            for model in TRAFFIC_MODELS:
                if should_stop():
                    result["stopped"] = True
                    return result
                answer = post_json(make_body(a, b, option, period, model), key)
                result["requests"] = result["requests"] + 1
                done = done + 1
                progress(done, total)
                read = read_answer(answer)
                if read is None:
                    usable = False
                    result["no_route"] = result["no_route"] + 1
                    break
                minutes[model] = read[0]
                metres = read[1]
                # a very different length means Google used another road
                if abs(metres / 1000.0 - option["km"]) > MAX_DIFFERENCE * option["km"]:
                    usable = False
                    result["different_road"] = result["different_road"] + 1
                    break
            if not usable:
                break
            average = round(minutes["BEST_GUESS"], 1)
            extra = round(max(0.0, minutes["PESSIMISTIC"] - minutes["BEST_GUESS"]), 1)
            new_times[period] = (max(0.5, average), extra)
        if usable and len(new_times) == len(PERIOD_TIMES):
            for period in new_times:
                option["times"][period] = new_times[period]
            option["source"] = "google"
            result["applied"] = result["applied"] + 1
        time.sleep(0.05)
    return result
