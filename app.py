import threading
import logging
from flask import Flask, render_template, request, jsonify, session
from pipeline import run_pipeline, get_winrate_by_hour, get_summary, get_puuid
from riot_client import get_puuid as fetch_puuid

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
app.secret_key = "lol-pipeline-secret"

# simple in-memory job state (single user, local app)
job_state = {
    "running": False,
    "progress": 0,
    "total": 0,
    "done": False,
    "error": None,
    "puuid": None,
    "riot_id": None,
}


def run_job(riot_id, num_matches):
    global job_state
    try:
        def on_progress(i, total):
            job_state["progress"] = i
            job_state["total"] = total

        # resolve puuid first so we can query after
        game_name, tag_line = riot_id.split("#")
        puuid = fetch_puuid(game_name, tag_line)
        job_state["puuid"] = puuid

        run_pipeline(riot_id, num_matches, progress_callback=on_progress)
        job_state["done"] = True
        job_state["running"] = False
    except Exception as e:
        job_state["error"] = str(e)
        job_state["running"] = False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run():
    global job_state
    if job_state["running"]:
        return jsonify({"error": "Pipeline already running"}), 400

    riot_id = request.json.get("riot_id", "").strip()
    num_matches = int(request.json.get("num_matches", 20))
    last_n = int(request.json.get("last_n", num_matches))

    if not riot_id or "#" not in riot_id:
        return jsonify({"error": "Enter a valid Riot ID (Name#TAG)"}), 400

    job_state = {
        "running": True,
        "progress": 0,
        "total": num_matches,
        "done": False,
        "error": None,
        "puuid": None,
        "riot_id": riot_id,
        "last_n": last_n,
    }

    t = threading.Thread(target=run_job, args=(riot_id, num_matches), daemon=True)
    t.start()
    return jsonify({"status": "started"})


@app.route("/status")
def status():
    return jsonify(job_state)


@app.route("/data")
def data():
    puuid = job_state.get("puuid")
    last_n = int(request.args.get("last_n", 20))
    if not puuid:
        return jsonify({"error": "No data yet"}), 404

    winrate = get_winrate_by_hour(puuid, last_n)
    summary = get_summary(puuid, last_n)
    return jsonify({"winrate_by_hour": winrate, "summary": summary})


if __name__ == "__main__":
    app.run(debug=True)
