"""Minimal Flask demo app — iTakt Day 2 demo target."""
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/")
def index():
    return jsonify({"message": "Hello from iTakt demo app"})


if __name__ == "__main__":
    app.run(debug=True)
