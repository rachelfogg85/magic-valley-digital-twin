"""Flask server: serves the web/ frontend, data/processed/ data files,
POST /api/optimize (the scenario tool), and POST /api/agent (the chat agent).
"""
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data" / "processed"

sys.path.insert(0, str(ROOT / "agent"))
import agent as chat_agent  # noqa: E402
import tools as agent_tools  # noqa: E402

app = Flask(__name__, static_folder=None)


@app.route("/api/optimize", methods=["POST"])
def api_optimize():
    body = request.get_json(force=True) or {}
    result = agent_tools.run_optimizer(
        water_pct=float(body.get("water_pct", 100)),
        year=int(body.get("year", 2021)),
        price_case=body.get("price_case", "mid"),
    )
    return jsonify(result)


@app.route("/api/agent/status")
def api_agent_status():
    return jsonify({"available": chat_agent.key_is_set()})


@app.route("/api/agent", methods=["POST"])
def api_agent():
    if not chat_agent.key_is_set():
        return jsonify({"error": "No PORTKEY_API_KEY configured on the server."}), 503
    body = request.get_json(force=True) or {}
    messages = body.get("messages", [])
    try:
        reply, plan = chat_agent.chat(messages)
    except Exception as e:  # noqa: BLE001 -- surface any failure to the chat box, don't 500 silently
        return jsonify({"error": str(e)}), 500
    return jsonify({"reply": reply, "plan": plan})


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
