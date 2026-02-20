import json
import random

def load_drivers():
    with open("data/drivers.json", "r") as file:
        return json.load(file)

def calculate_score(driver, track_factor, weather_factor):
    base_score = (
        driver["performance"] * 0.5 +
        driver["team"] * 0.3 +
        track_factor * 0.1 +
        weather_factor * 0.1
    )

    variability = random.randint(-5, 5)
    return base_score + variability

def simulate_race():
    drivers = load_drivers()

    track_factor = 90
    weather_factor = 85

    results = []

    for driver in drivers:
        score = calculate_score(driver, track_factor, weather_factor)
        results.append((driver["name"], score))

    results.sort(key=lambda x: x[1], reverse=True)

    points_system = [25,18,15,12,10,8,6,4,2,1]

    final_results = []
    for i, (name, score) in enumerate(results):
        points = points_system[i] if i < len(points_system) else 0
        final_results.append((name, round(score,2), points))

    return final_results

if __name__ == "__main__":
    race = simulate_race()

    print("\nRace Results\n")
    for position, result in enumerate(race, start=1):
        print(f"{position}. {result[0]} | Score: {result[1]} | Points: {result[2]}")