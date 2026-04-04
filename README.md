# F1 Race Predictor

A Flask web application that predicts Formula 1 race finishing order using historical driver performance, track characteristics, and weather conditions — powered by the FastF1 API.

---

## Features

- **Full race prediction** — predicts all 20 drivers' finishing order for any Grand Prix
- **Qualifying position input** — enter real grid positions before a race to improve accuracy
- **Track + weather modifiers** — circuit-specific bonuses (Monaco, Monza, Spa) and wet-weather driver skill adjustments
- **Driver & constructor standings** — actual championship points table from historical data
- **Race calendar** — full season schedule with session times, sprint weekends, and countdown
- **One-click predict** — jump from calendar directly to a race prediction
- **JSON data store** — no database needed, all data stored in flat JSON files
- **REST API** — `/api/predict` and `/api/standings` endpoints for programmatic access

---

## Tech Stack

| Layer           | Technology                       |
|-----------------|----------------------------------|
| Language        | Python 3.10+                     |
| Web framework   | Flask                            |
| F1 data         | FastF1                           |
| Data processing | Pandas                           |
| Storage         | JSON flat files                  |
| Frontend        | Jinja2 templates, vanilla CSS/JS |

---

## Project Structure

```
f1-race-predictor/
├── app.py                  # Flask server — all routes
├── predictor.py            # Scoring + prediction engine
├── data_collector.py       # FastF1 data fetcher
├── data/
│   ├── races.json          # Historical race results
│   ├── drivers.json        # Aggregated driver stats
│   └── tracks.json         # Track + weather modifiers
├── templates/
│   ├── index.html          # Main page (predict + standings)
│   └── calendar.html       # Season calendar page
├── cache/                  # FastF1 local cache (auto-created)
└── README.md
```

---

## Setup & Installation

### 1. Clone the repository

```bash
git clone https://github.com/hetavi2404/f1-race-predictor.git
cd f1-race-predictor
```

### 2. Install dependencies

```bash
pip install flask fastf1 pandas requests
```

### 3. Fetch race data

This downloads historical race data from FastF1 and saves it to `./data/`. First run takes 10–20 minutes (data is cached after that).

```bash
# Fetch last 2 seasons (default)
python data_collector.py

# Or fetch specific years
python data_collector.py --year 2022 2023 2024
```

### 4. Run the app

```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

---

## Usage

### Predicting a race

1. Go to the home page
2. Select a **race**, **weather condition**, and **season year**
3. Optionally click **"Enter qualifying positions"** and fill in the real grid order
4. Click **Predict**

### Viewing the calendar

- Visit `/calendar` for the full season schedule
- Click **"Predict this race"** on any card to jump straight to the predictor

### Refreshing data

Click **Refresh Data** in the header (or visit `/refresh`) to pull the latest completed races from FastF1 without restarting the server.

---

## How the Prediction Works

Each driver is scored out of ~100 points using five weighted components:

| Component | Weight | Description |
|-----------|--------|-------------|
| Career avg finish | 40% | Historical average finishing position converted to score |
| Recent form | 25% | Average of last 5 race results |
| Track history | 15% | Average finish at this specific circuit |
| Qualifying position | 10% | Grid position × track-specific qualifying weight |
| Reliability | 5% | DNF rate penalty |

Two multipliers are then applied on top:

- **Weather modifier** — wet-weather specialists (Hamilton, Verstappen, Alonso) get a bonus in rain
- **Track modifier** — circuit-specific bonuses e.g. Monaco rewards consistency, Monza rewards straight-line speed

Drivers are then ranked by final score (highest = P1 predicted).

---

## API Endpoints

```
GET /api/predict?race=Bahrain Grand Prix&weather=dry&year=2024
GET /api/standings?year=2024
GET /races
GET /refresh
```

---

## Data Files

### `races.json`
List of all race results fetched from FastF1.
```json
{
  "year": 2024, "round": 1,
  "event_name": "Bahrain Grand Prix",
  "weather": "dry",
  "results": [
    { "position": 1, "driver_code": "VER", "points": 25, "finished": true }
  ]
}
```

### `drivers.json`
Aggregated performance stats per driver, keyed by driver code.
```json
"VER": {
  "avg_finish": 2.1,
  "base_score": 94.5,
  "win_rate": 0.56,
  "dnf_rate": 0.04,
  "avg_wet_finish": 3.2
}
```

### `tracks.json`
Track and weather modifier tables used by the prediction engine.

---

## Limitations

- Predictions are based on historical data only — does not account for car upgrades mid-season, driver transfers, or real-time telemetry
- Weather modifiers are manually calibrated, not ML-trained
- FastF1 data availability depends on the F1 data feed; some older seasons may be incomplete

---

## License

For educational use only. F1 data is sourced via the FastF1 library which uses the official Formula 1 timing data feed.