"""Minimal Flask server: serves the web/ frontend and data/processed/ data files."""
from pathlib import Path

from flask import Flask, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data" / "processed"

app = Flask(__name__, static_folder=None)


@app.route("/data/<path:path>")
def data_files(path):
    return send_from_directory(DATA_DIR, path)


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:path>")
def web_files(path):
    return send_from_directory(WEB_DIR, path)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
