"""
F1 Race Predictor — Prediction Engine
=======================================
Loads driver stats, track modifiers, and weather modifiers from JSON,
then produces a predicted finishing order for any upcoming race.

Usage (standalone test):
    python predictor.py --race "Bahrain Grand Prix" --weather dry --year 2025
"""

import json
import os
import argparse
from datetime import datetime

DATA_DIR = "./data"

# F1 points system
POINTS_MAP = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10,
              6: 8,  7: 6,  8: 4,  9: 2,  10: 1}


# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────

def load_json(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found: {path}. Run data_collector.py first.")
    with open(path, "r") as f:
        content = f.read().strip()
    if not content:
        raise ValueError(f"Data file is empty: {path}. Run data_collector.py first.")
    return json.loads(content)


def load_all_data():
    races   = load_json(os.path.join(DATA_DIR, "races.json"))
    drivers = load_json(os.path.join(DATA_DIR, "drivers.json"))
    tracks  = load_json(os.path.join(DATA_DIR, "tracks.json"))
    return races, drivers, tracks


# ─────────────────────────────────────────────────────────────────────────────
# SCORING ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def get_track_modifier(tracks: dict, race_name: str) -> dict:
    modifiers = tracks.get("modifiers", {})
    for track_key, mod in modifiers.items():
        if track_key.lower() in race_name.lower() or race_name.lower() in track_key.lower():
            return mod
    return modifiers.get("default", {"quali_weight": 1.0, "street_circuit": False})


def get_weather_modifier(tracks: dict, weather: str, driver_code: str) -> float:
    weather_mods = tracks.get("weather_modifiers", {})
    condition    = weather_mods.get(weather, weather_mods.get("dry", {}))
    skill_bonuses = condition.get("driver_skill_bonus", {})
    default_mult  = condition.get("default_multiplier", 1.0)
    return skill_bonuses.get(driver_code, default_mult)


def get_recent_form(races: list, driver_code: str, last_n: int = 5) -> float:
    recent_positions = []
    for race in reversed(races):
        if len(recent_positions) >= last_n:
            break
        for result in race["results"]:
            if result["driver_code"] == driver_code:
                pos = result.get("position", 0)
                if pos > 0:
                    recent_positions.append(pos)
                break
    if not recent_positions:
        return 15.0
    return sum(recent_positions) / len(recent_positions)


def get_track_history(races: list, driver_code: str, race_name: str) -> float | None:
    positions = []
    for race in races:
        if race_name.lower() not in race["event_name"].lower():
            continue
        for result in race["results"]:
            if result["driver_code"] == driver_code:
                pos = result.get("position", 0)
                if pos > 0:
                    positions.append(pos)
                break
    if not positions:
        return None
    return sum(positions) / len(positions)


def score_driver(
    driver: dict,
    driver_code: str,
    races: list,
    tracks: dict,
    race_name: str,
    weather: str,
    quali_position: int | None = None
) -> float:
    """
    Score breakdown:
      Base score        40%  — career avg finish
      Recent form       25%  — last 5 races
      Track history     15%  — avg at this circuit
      Qualifying        10%  — grid position (weighted by track)
      Reliability        5%  — DNF rate penalty
      Weather modifier   5%  — wet/dry skill multiplier
      Track modifier     +%  — circuit-specific bonuses
    """
    base         = driver.get("base_score", 50.0)
    recent_avg   = get_recent_form(races, driver_code, last_n=5)
    recent_score = max(5.0, 100 - (recent_avg - 1) * (95 / 19))

    track_hist = get_track_history(races, driver_code, race_name)
    track_history_score = (
        max(5.0, 100 - (track_hist - 1) * (95 / 19))
        if track_hist is not None else recent_score
    )

    track_mod    = get_track_modifier(tracks, race_name)
    quali_weight = track_mod.get("quali_weight", 1.0)

    if quali_position is not None and quali_position > 0:
        quali_score  = max(5.0, 100 - (quali_position - 1) * (95 / 19))
        quali_impact = quali_score * quali_weight * 0.10
    else:
        avg_grid     = driver.get("avg_grid", 10.0)
        quali_score  = max(5.0, 100 - (avg_grid - 1) * (95 / 19))
        quali_impact = quali_score * 0.05

    dnf_rate        = driver.get("dnf_rate", 0.05)
    reliability_mod = 1.0 - (dnf_rate * 0.5)
    weather_mult    = get_weather_modifier(tracks, weather, driver_code)

    circuit_bonus = 1.0
    if track_mod.get("street_circuit") and driver.get("podium_rate", 0) > 0.3:
        circuit_bonus *= 1.03
    if "overtaking_bonus" in track_mod and driver.get("avg_finish", 10) < 8:
        circuit_bonus *= track_mod["overtaking_bonus"]
    if "overtaking_penalty" in track_mod and driver.get("avg_finish", 10) > 10:
        circuit_bonus *= track_mod["overtaking_penalty"]

    weighted = (
        base                * 0.40 +
        recent_score        * 0.25 +
        track_history_score * 0.15 +
        quali_impact        * 1.00 +
        (100 * reliability_mod) * 0.05
    )

    return round(weighted * weather_mult * circuit_bonus, 4)


# ─────────────────────────────────────────────────────────────────────────────
# PREDICT A RACE
# ─────────────────────────────────────────────────────────────────────────────

def predict_race(
    race_name: str,
    weather: str = "dry",
    quali_results: dict | None = None,
    year: int | None = None
) -> list[dict]:
    """
    Predict the full finishing order for a race.

    Args:
        race_name:     e.g. "Bahrain Grand Prix"
        weather:       "dry", "light_rain", or "wet"
        quali_results: optional dict of driver_code -> qualifying position
        year:          filter historical data up to this year

    Returns:
        List of dicts sorted by predicted position, with points assigned.
    """
    races, drivers, tracks = load_all_data()

    if year:
        races = [r for r in races if r["year"] <= year]

    if not drivers:
        raise ValueError("No driver data found. Run data_collector.py first.")

    quali_results = quali_results or {}

    scored = []
    for code, driver in drivers.items():
        score = score_driver(
            driver         = driver,
            driver_code    = code,
            races          = races,
            tracks         = tracks,
            race_name      = race_name,
            weather        = weather,
            quali_position = quali_results.get(code)
        )
        scored.append({
            "driver_code": code,
            "driver_name": driver.get("driver_name", code),
            "team":        driver.get("team", "Unknown"),
            "score":       score,
            "quali_pos":   quali_results.get(code)
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    predictions = []
    for i, entry in enumerate(scored):
        pos = i + 1
        predictions.append({
            "predicted_position": pos,
            "driver_code":        entry["driver_code"],
            "driver_name":        entry["driver_name"],
            "team":               entry["team"],
            "score":              entry["score"],
            "quali_pos":          entry["quali_pos"],
            "predicted_points":   POINTS_MAP.get(pos, 0)
        })

    return predictions


# ─────────────────────────────────────────────────────────────────────────────
# STANDINGS
# ─────────────────────────────────────────────────────────────────────────────

def calculate_standings(races: list, year: int | None = None) -> list[dict]:
    """Driver championship standings from actual race results."""
    if year:
        races = [r for r in races if r["year"] == year]

    standings = {}
    for race in races:
        for result in race["results"]:
            code = result["driver_code"]
            if code not in standings:
                standings[code] = {
                    "driver_code": code,
                    "driver_name": result["driver_name"],
                    "team":        result["team"],
                    "points":      0.0,
                    "wins":        0,
                    "podiums":     0,
                    "races":       0
                }
            s   = standings[code]
            pos = result.get("position", 0)
            s["points"] += result.get("points", 0)
            s["races"]  += 1
            s["team"]    = result["team"]
            if pos == 1:   s["wins"]   += 1
            if 1 <= pos <= 3: s["podiums"] += 1

    sorted_standings = sorted(standings.values(), key=lambda x: x["points"], reverse=True)
    for i, entry in enumerate(sorted_standings):
        entry["position"] = i + 1
        entry["points"]   = round(entry["points"], 1)

    return sorted_standings


def calculate_constructor_standings(races: list, year: int | None = None) -> list[dict]:
    """Constructor championship standings from actual race results."""
    if year:
        races = [r for r in races if r["year"] == year]

    teams = {}
    for race in races:
        for result in race["results"]:
            team = result["team"]
            if team not in teams:
                teams[team] = {"team": team, "points": 0.0, "wins": 0, "races": 0}
            t = teams[team]
            t["points"] += result.get("points", 0)
            t["races"]  += 1
            if result.get("position", 0) == 1:
                t["wins"] += 1

    sorted_teams = sorted(teams.values(), key=lambda x: x["points"], reverse=True)
    for i, entry in enumerate(sorted_teams):
        entry["position"] = i + 1
        entry["points"]   = round(entry["points"], 1)

    return sorted_teams


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE TEST
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="F1 Race Predictor")
    parser.add_argument("--race",    default="Bahrain Grand Prix")
    parser.add_argument("--weather", default="dry",
                        choices=["dry", "light_rain", "wet"])
    parser.add_argument("--year",    type=int, default=datetime.now().year)
    args = parser.parse_args()

    print(f"\nPredicting: {args.race}  |  Weather: {args.weather}  |  Year: {args.year}\n")

    try:
        predictions = predict_race(args.race, args.weather, year=args.year)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        return

    print(f"{'Pos':<5} {'Driver':<25} {'Team':<28} {'Score':<10} {'Pts'}")
    print("─" * 75)
    for p in predictions:
        pts = f"+{p['predicted_points']}" if p['predicted_points'] > 0 else ""
        print(f"P{p['predicted_position']:<4} {p['driver_name']:<25} {p['team']:<28} "
              f"{p['score']:<10.2f} {pts}")

    print(f"\n── Driver Standings ({args.year}) ──────────────────────────────────────")
    races, _, _ = load_all_data()
    standings = calculate_standings(races, year=args.year)
    print(f"{'Pos':<5} {'Driver':<25} {'Team':<28} {'Pts'}")
    print("─" * 65)
    for s in standings[:10]:
        print(f"P{s['position']:<4} {s['driver_name']:<25} {s['team']:<28} {s['points']}")


if __name__ == "__main__":
    main()