"""Minimal Flask demo app — iTakt Day 2 demo target."""
from datetime import datetime, timezone
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/")
def index():
    return jsonify({"message": "Hello from iTakt demo app"})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    app.run(debug=True)
