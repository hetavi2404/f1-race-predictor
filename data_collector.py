"""
F1 Race Predictor — Data Collector
====================================
Fetches race results, driver stats, and track/weather info
using the FastF1 library and saves everything to JSON files
in the ./data/ directory.

Usage:
    python data_collector.py                  # fetch last 2 seasons
    python data_collector.py --year 2024      # fetch a specific year
    python data_collector.py --year 2023 2024 # fetch multiple years
"""

import fastf1
import pandas as pd
import json
import os
import argparse
from datetime import datetime

# ── Output directory ──────────────────────────────────────────────────────────
DATA_DIR = "./data"
CACHE_DIR = "./cache"          # FastF1 caches downloaded data here
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

fastf1.Cache.enable_cache(CACHE_DIR)

# ── F1 points system (P1 → P10) ───────────────────────────────────────────────
POINTS_MAP = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10,
              6: 8,  7: 6,  8: 4,  9: 2,  10: 1}

# ── Track characteristic modifiers ────────────────────────────────────────────
# Values are multipliers applied to a driver's base score.
# > 1.0  = advantage at this track for drivers with that trait
# < 1.0  = disadvantage
TRACK_MODIFIERS = {
    "Monaco": {
        "description": "Tight street circuit — rewards precision, punishes overtaking styles",
        "quali_weight": 1.4,      # qualifying position matters more here
        "overtaking_penalty": 0.85,
        "street_circuit": True
    },
    "Monza": {
        "description": "High-speed temple of speed — rewards straight-line performance",
        "quali_weight": 1.1,
        "slipstream_bonus": 1.05,
        "street_circuit": False
    },
    "Spa": {
        "description": "High-speed mixed circuit — rewards downforce and wet-weather skill",
        "quali_weight": 1.05,
        "wet_sensitivity": 1.2,
        "street_circuit": False
    },
    "Silverstone": {
        "description": "High-speed flowing corners — rewards aerodynamic balance",
        "quali_weight": 1.1,
        "street_circuit": False
    },
    "Bahrain": {
        "description": "Desert circuit — good overtaking, high tyre degradation",
        "quali_weight": 1.0,
        "tyre_deg_sensitivity": 1.1,
        "street_circuit": False
    },
    "Suzuka": {
        "description": "Technical flowing circuit — rewards driver skill",
        "quali_weight": 1.15,
        "street_circuit": False
    },
    "Interlagos": {
        "description": "Anti-clockwise, hilly — high overtaking potential",
        "quali_weight": 0.95,
        "overtaking_bonus": 1.05,
        "street_circuit": False
    },
    "default": {
        "description": "Standard circuit",
        "quali_weight": 1.0,
        "street_circuit": False
    }
}

# ── Weather modifiers ─────────────────────────────────────────────────────────
# Applied as a multiplier to driver score based on known wet-weather skill.
# Drivers not listed get a 1.0 (neutral) modifier.
WEATHER_MODIFIERS = {
    "wet": {
        "description": "Wet / heavy rain conditions",
        "driver_skill_bonus": {
            # Drivers known for exceptional wet-weather performance
            "HAM": 1.15,
            "VER": 1.12,
            "ALO": 1.10,
            "RUS": 1.05,
            "SAI": 1.03,
        },
        "default_multiplier": 0.97   # slight chaos penalty for rest
    },
    "light_rain": {
        "description": "Light rain / damp track",
        "driver_skill_bonus": {
            "HAM": 1.07,
            "VER": 1.06,
            "ALO": 1.05,
        },
        "default_multiplier": 0.99
    },
    "dry": {
        "description": "Dry conditions",
        "driver_skill_bonus": {},
        "default_multiplier": 1.0
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def safe_float(value, default=0.0):
    """Convert a value to float safely, returning default on failure."""
    try:
        v = float(value)
        return v if pd.notna(v) else default
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    """Convert a value to int safely."""
    try:
        v = int(value)
        return v if pd.notna(v) else default
    except (TypeError, ValueError):
        return default


def get_points(position):
    """Return F1 championship points for a given finishing position."""
    return POINTS_MAP.get(position, 0)


# ─────────────────────────────────────────────────────────────────────────────
# FETCH RACE RESULTS FOR A SEASON
# ─────────────────────────────────────────────────────────────────────────────

def fetch_season(year: int) -> list[dict]:
    """
    Fetch all race results for a given season year.
    Returns a list of race dictionaries.
    """
    print(f"\n[{year}] Fetching season schedule...")
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    races = []

    for _, event in schedule.iterrows():
        round_num = safe_int(event.get("RoundNumber", 0))
        if round_num == 0:
            continue

        event_name = str(event.get("EventName", "Unknown"))
        country    = str(event.get("Country", "Unknown"))
        location   = str(event.get("Location", "Unknown"))
        event_date = str(event.get("EventDate", ""))

        # Skip future races (no results yet)
        try:
            race_date = pd.to_datetime(event_date)
            if race_date > pd.Timestamp.now():
                print(f"  Skipping future race: {event_name}")
                continue
        except Exception:
            pass

        print(f"  Fetching round {round_num}: {event_name}...", end=" ")

        try:
            session = fastf1.get_session(year, round_num, "R")
            session.load(telemetry=False, weather=True, messages=False)

            results = session.results
            if results is None or results.empty:
                print("no results.")
                continue

            weather_data = session.weather_data
            weather_condition = classify_weather(weather_data)

            driver_results = []
            for _, row in results.iterrows():
                pos   = safe_int(row.get("Position", 0))
                grid  = safe_int(row.get("GridPosition", 0))
                abbr  = str(row.get("Abbreviation", "???"))
                name  = f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip()
                team  = str(row.get("TeamName", "Unknown"))
                status = str(row.get("Status", "Finished"))
                pts   = safe_float(row.get("Points", get_points(pos)))

                driver_results.append({
                    "position":     pos,
                    "grid_position": grid,
                    "driver_code":  abbr,
                    "driver_name":  name,
                    "team":         team,
                    "status":       status,   # "Finished", "DNF", "+1 Lap", etc.
                    "points":       pts,
                    "finished":     status == "Finished" or status.startswith("+")
                })

            # Sort by finishing position
            driver_results.sort(key=lambda x: x["position"] if x["position"] > 0 else 99)

            races.append({
                "year":       year,
                "round":      round_num,
                "event_name": event_name,
                "country":    country,
                "location":   location,
                "date":       event_date,
                "weather":    weather_condition,
                "results":    driver_results
            })
            print(f"done ({len(driver_results)} drivers).")

        except Exception as e:
            print(f"ERROR — {e}")
            continue

    return races


def classify_weather(weather_data) -> str:
    """
    Classify weather from FastF1 weather_data DataFrame.
    Returns 'wet', 'light_rain', or 'dry'.
    """
    if weather_data is None or weather_data.empty:
        return "dry"
    try:
        rain_laps = weather_data["Rainfall"].sum() if "Rainfall" in weather_data.columns else 0
        total = len(weather_data)
        rain_ratio = rain_laps / total if total > 0 else 0

        if rain_ratio > 0.4:
            return "wet"
        elif rain_ratio > 0.1:
            return "light_rain"
        return "dry"
    except Exception:
        return "dry"


# ─────────────────────────────────────────────────────────────────────────────
# BUILD DRIVER STATS FROM RACE RESULTS
# ─────────────────────────────────────────────────────────────────────────────

def build_driver_stats(all_races: list[dict]) -> dict:
    """
    Aggregate per-driver stats from all race results.
    Returns a dict keyed by driver code (e.g. "VER", "HAM").
    """
    drivers = {}

    for race in all_races:
        for r in race["results"]:
            code = r["driver_code"]
            if code not in drivers:
                drivers[code] = {
                    "driver_code": code,
                    "driver_name": r["driver_name"],
                    "team":        r["team"],
                    "races":       0,
                    "total_points": 0.0,
                    "wins":        0,
                    "podiums":     0,
                    "dnfs":        0,
                    "positions":   [],   # list of finishing positions
                    "grid_positions": [],
                    "wet_positions": [],  # finishing positions in wet races
                }

            d = drivers[code]
            d["races"]        += 1
            d["total_points"] += r["points"]
            d["team"]          = r["team"]   # keep most recent team

            pos = r["position"]
            if pos > 0:
                d["positions"].append(pos)
                if race["weather"] in ("wet", "light_rain"):
                    d["wet_positions"].append(pos)

            grid = r["grid_position"]
            if grid > 0:
                d["grid_positions"].append(grid)

            if pos == 1:
                d["wins"] += 1
            if 1 <= pos <= 3:
                d["podiums"] += 1
            if not r["finished"]:
                d["dnfs"] += 1

    # ── Compute derived stats ─────────────────────────────────────────────────
    for code, d in drivers.items():
        positions = d["positions"]
        d["avg_finish"]     = round(sum(positions) / len(positions), 2) if positions else 15.0
        d["avg_grid"]       = round(sum(d["grid_positions"]) / len(d["grid_positions"]), 2) if d["grid_positions"] else 10.0
        d["dnf_rate"]       = round(d["dnfs"] / d["races"], 3) if d["races"] > 0 else 0.0
        d["win_rate"]       = round(d["wins"] / d["races"], 3) if d["races"] > 0 else 0.0
        d["podium_rate"]    = round(d["podiums"] / d["races"], 3) if d["races"] > 0 else 0.0
        d["avg_wet_finish"] = round(sum(d["wet_positions"]) / len(d["wet_positions"]), 2) if d["wet_positions"] else d["avg_finish"]

        # Base performance score (lower avg finish = better, so we invert)
        # Score out of 100: a P1 average = 100, P20 average ≈ 10
        d["base_score"] = round(max(0, 100 - (d["avg_finish"] - 1) * (90 / 19)), 2)

        # Remove raw lists from output (too large for JSON)
        del d["positions"]
        del d["grid_positions"]
        del d["wet_positions"]

    return drivers


# ─────────────────────────────────────────────────────────────────────────────
# SAVE / LOAD HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def load_json(path: str) -> list | dict:
    """Load existing JSON file if it exists, else return empty structure."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            content = f.read().strip()
        if not content:
            print(f"  Warning: {path} is empty, starting fresh.")
            return []
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  Warning: {path} is corrupt ({e}), starting fresh.")
        return []


def save_json(path: str, data):
    """Save data to a JSON file with pretty formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Saved → {path}  ({os.path.getsize(path) // 1024} KB)")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main(years: list[int]):
    races_path   = os.path.join(DATA_DIR, "races.json")
    drivers_path = os.path.join(DATA_DIR, "drivers.json")
    tracks_path  = os.path.join(DATA_DIR, "tracks.json")

    # ── Load any existing data ────────────────────────────────────────────────
    existing_races = load_json(races_path)
    existing_keys  = {(r["year"], r["round"]) for r in existing_races}

    # ── Fetch new seasons ─────────────────────────────────────────────────────
    all_new_races = []
    for year in years:
        season_races = fetch_season(year)
        # Only add races we don't already have
        new = [r for r in season_races if (r["year"], r["round"]) not in existing_keys]
        all_new_races.extend(new)
        print(f"  [{year}] {len(new)} new race(s) fetched.")

    all_races = existing_races + all_new_races

    if not all_races:
        print("\nNo race data collected. Check your year range or network connection.")
        return

    # ── Build and save races.json ─────────────────────────────────────────────
    print("\nSaving data files...")
    save_json(races_path, all_races)

    # ── Build and save drivers.json ───────────────────────────────────────────
    driver_stats = build_driver_stats(all_races)
    save_json(drivers_path, driver_stats)

    # ── Save tracks.json (modifiers + circuit list) ───────────────────────────
    # Extract unique circuit names from race data
    circuits_seen = {}
    for race in all_races:
        loc = race["location"]
        if loc not in circuits_seen:
            circuits_seen[loc] = race["event_name"]

    tracks_data = {
        "modifiers": TRACK_MODIFIERS,
        "weather_modifiers": WEATHER_MODIFIERS,
        "circuits": {loc: {"event_name": name} for loc, name in circuits_seen.items()}
    }
    save_json(tracks_path, tracks_data)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Data collection complete!
  Total races:   {len(all_races)}
  Total drivers: {len(driver_stats)}
  Circuits seen: {len(circuits_seen)}

Files saved to ./data/
  races.json    — full race-by-race results
  drivers.json  — aggregated driver performance stats
  tracks.json   — track + weather modifiers
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 Data Collector")
    parser.add_argument(
        "--year", type=int, nargs="+",
        default=[datetime.now().year - 1, datetime.now().year],
        help="Season year(s) to fetch (default: last 2 seasons)"
    )
    args = parser.parse_args()
    main(args.year)