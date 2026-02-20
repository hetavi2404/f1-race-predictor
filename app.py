from flask import Flask, render_template, request
from predictor import simulate_race, load_tracks

app = Flask(__name__)

@app.route("/")
def home():
    tracks = load_tracks()
    return render_template("index.html", tracks=tracks)

@app.route("/predict", methods=["POST"])
def predict():
    track = request.form["track"]
    weather = request.form["weather"]

    results = simulate_race(track, weather)

    return render_template("result.html", results=results, track=track, weather=weather)

if __name__ == "__main__":
    app.run(debug=True)