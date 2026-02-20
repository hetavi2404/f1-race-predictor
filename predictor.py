import random

#sample driver data (temporary — later from JSON/API)
drivers = [
    {"name": "Verstappen", "performance": 95, "team": 94},
    {"name": "Hamilton", "performance": 92, "team": 90},
    {"name": "Leclerc", "performance": 90, "team": 89},
    {"name": "Norris", "performance": 88, "team": 87},
    {"name": "Alonso", "performance": 89, "team": 86},
]

def calculate_score(driver, track_factor, weather_factor):
    base_score = (
        driver["performance"] * 0.5 +
        driver["team"] * 0.3 +
        track_factor * 0.1 +
        weather_factor * 0.1
    )

    #controlled randomness
    variability = random.randint(-5, 5)

    return base_score + variability

def simulate_race():
    track_factor = 90
    weather_factor = 85

    results = []

    for driver in drivers:
        score = calculate_score(driver, track_factor, weather_factor)
        results.append((driver["name"], score))

    #sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)

    #assign points
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