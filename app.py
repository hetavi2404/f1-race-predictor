"""
F1 Race Predictor — Flask Web Server
======================================
Routes:
  GET  /                        → main page (standings + prediction form)
  GET  /predict?race=...&weather=...&year=...   → prediction results page
  POST /predict                 → same, accepts form POST
  GET  /api/predict             → JSON API endpoint
  GET  /api/standings           → JSON standings
  GET  /refresh                 → re-run data_collector for latest data
  GET  /races                   → list all available races in the data
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for

from predictor import (
    predict_race,
    calculate_standings,
    calculate_constructor_standings,
    load_all_data,
)

app = Flask(__name__)
DATA_DIR = "./data"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_available_races() -> list[dict]:
    """Return a sorted list of unique races from races.json."""
    try:
        races, _, _ = load_all_data()
    except Exception:
        return []

    seen = {}
    for race in races:
        key = race["event_name"]
        if key not in seen:
            seen[key] = {
                "event_name": race["event_name"],
                "country":    race.get("country", ""),
                "location":   race.get("location", ""),
            }
    return sorted(seen.values(), key=lambda x: x["event_name"])


def get_available_years() -> list[int]:
    """Return sorted list of season years in the data."""
    try:
        races, _, _ = load_all_data()
        return sorted({r["year"] for r in races}, reverse=True)
    except Exception:
        return [datetime.now().year]


def data_exists() -> bool:
    return (
        os.path.exists(os.path.join(DATA_DIR, "races.json")) and
        os.path.getsize(os.path.join(DATA_DIR, "races.json")) > 10
    )


def get_drivers() -> list[dict]:
    """Return list of drivers sorted by code, for the quali input grid."""
    try:
        _, drivers, _ = load_all_data()
        return sorted(
            [{"code": code, "name": d.get("driver_name", code), "team": d.get("team", "")}
             for code, d in drivers.items()],
            key=lambda x: x["name"]
        )
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if not data_exists():
        return render_template("index.html",
                               no_data=True,
                               races=[],
                               years=[],
                               drivers=[],
                               standings=[],
                               constructor_standings=[],
                               current_year=datetime.now().year)

    try:
        all_races, _, _ = load_all_data()
        year = request.args.get("year", type=int, default=max(get_available_years()))
        standings = calculate_standings(all_races, year=year)
        constructor_standings = calculate_constructor_standings(all_races, year=year)
    except Exception as e:
        standings = []
        constructor_standings = []
        year = datetime.now().year

    return render_template("index.html",
                           no_data=False,
                           races=get_available_races(),
                           years=get_available_years(),
                           drivers=get_drivers(),
                           standings=standings,
                           constructor_standings=constructor_standings,
                           current_year=year,
                           selected_year=year)


@app.route("/predict", methods=["GET", "POST"])
def predict():
    if request.method == "POST":
        race_name = request.form.get("race", "Bahrain Grand Prix")
        weather   = request.form.get("weather", "dry")
        year      = request.form.get("year", type=int, default=datetime.now().year)
    else:
        race_name = request.args.get("race", "Bahrain Grand Prix")
        weather   = request.args.get("weather", "dry")
        year      = request.args.get("year", type=int, default=datetime.now().year)

    # Optional: parse qualifying positions from form
    # Format: quali_VER=1&quali_HAM=2 etc.
    quali_results = {}
    form_data = request.form if request.method == "POST" else request.args
    for key, value in form_data.items():
        if key.startswith("quali_") and value.strip().isdigit():
            driver_code = key.replace("quali_", "").upper()
            quali_results[driver_code] = int(value)

    error = None
    predictions = []
    try:
        predictions = predict_race(
            race_name     = race_name,
            weather       = weather,
            quali_results = quali_results or None,
            year          = year
        )
    except (FileNotFoundError, ValueError) as e:
        error = str(e)

    return render_template("index.html",
                           no_data=not data_exists(),
                           races=get_available_races(),
                           years=get_available_years(),
                           drivers=get_drivers(),
                           standings=[],
                           constructor_standings=[],
                           predictions=predictions,
                           selected_race=race_name,
                           selected_weather=weather,
                           selected_year=year,
                           current_year=year,
                           show_predictions=True,
                           quali_results=quali_results,
                           error=error)


@app.route("/api/predict")
def api_predict():
    race_name = request.args.get("race", "Bahrain Grand Prix")
    weather   = request.args.get("weather", "dry")
    year      = request.args.get("year", type=int, default=datetime.now().year)

    try:
        predictions = predict_race(race_name, weather, year=year)
        return jsonify({"status": "ok", "race": race_name, "weather": weather,
                        "year": year, "predictions": predictions})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/standings")
def api_standings():
    year = request.args.get("year", type=int, default=datetime.now().year)
    try:
        races, _, _ = load_all_data()
        driver_standings = calculate_standings(races, year=year)
        constructor_standings = calculate_constructor_standings(races, year=year)
        return jsonify({
            "status": "ok",
            "year":   year,
            "drivers": driver_standings,
            "constructors": constructor_standings
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/races")
def races_list():
    try:
        available = get_available_races()
        years = get_available_years()
        return jsonify({"races": available, "years": years})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/refresh")
def refresh_data():
    """Trigger data_collector.py to fetch latest race data."""
    try:
        result = subprocess.run(
            [sys.executable, "data_collector.py"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            return jsonify({"status": "ok", "message": "Data refreshed successfully.",
                            "output": result.stdout[-2000:]})
        else:
            return jsonify({"status": "error", "message": result.stderr[-1000:]}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "message": "Refresh timed out (>5 min)."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# CALENDAR
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/calendar")
def calendar():
    year = request.args.get("year", type=int, default=datetime.now().year)

    try:
        import fastf1
        import pandas as pd

        schedule = fastf1.get_event_schedule(year, include_testing=False)
        now = pd.Timestamp.now(tz="UTC").tz_localize(None)

        events = []
        for _, row in schedule.iterrows():
            round_num  = int(row.get("RoundNumber", 0))
            if round_num == 0:
                continue

            event_name = str(row.get("EventName", ""))
            country    = str(row.get("Country", ""))
            location   = str(row.get("Location", ""))
            event_date = row.get("EventDate")

            try:
                dt = pd.to_datetime(event_date)
                if dt.tzinfo is not None:
                    dt = dt.tz_localize(None)
                date_str   = dt.strftime("%d %b %Y")
                is_past    = dt < now
                days_away  = (dt - now).days
            except Exception:
                date_str  = str(event_date)[:10]
                is_past   = False
                days_away = None

            # Session dates
            sessions = {}
            for session_key, label in [
                ("Session1Date", "FP1"), ("Session2Date", "FP2"),
                ("Session3Date", "FP3"), ("Session4Date", "Sprint"),
                ("Session5Date", "Qualifying"), ("EventDate", "Race"),
            ]:
                val = row.get(session_key)
                if val and str(val) not in ("NaT", "nan", "None"):
                    try:
                        sdt = pd.to_datetime(val)
                        if sdt.tzinfo is not None:
                            sdt = sdt.tz_localize(None)
                        sessions[label] = sdt.strftime("%d %b, %H:%M")
                    except Exception:
                        pass

            # Is sprint weekend?
            is_sprint = "Sprint" in sessions

            events.append({
                "round":      round_num,
                "event_name": event_name,
                "country":    country,
                "location":   location,
                "date":       date_str,
                "is_past":    is_past,
                "days_away":  days_away,
                "sessions":   sessions,
                "is_sprint":  is_sprint,
            })

        # Find the next upcoming race
        upcoming_idx = next(
            (i for i, e in enumerate(events) if not e["is_past"]), None
        )

    except Exception as ex:
        events       = []
        upcoming_idx = None
        error        = str(ex)
    else:
        error = None

    return render_template(
        "calendar.html",
        events=events,
        year=year,
        years=get_available_years() or [datetime.now().year],
        upcoming_idx=upcoming_idx,
        error=error,
    )


# ─────────────────────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    print("\nF1 Race Predictor running at http://127.0.0.1:5000\n")
    app.run(debug=True, port=5000)