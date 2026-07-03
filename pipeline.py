import sqlite3
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from riot_client import get_puuid, get_match_ids, get_match

logger = logging.getLogger(__name__)

DB_PATH = Path("data/lol.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id     TEXT PRIMARY KEY,
    puuid        TEXT,
    game_start   INTEGER,
    hour_of_day  INTEGER,
    win          INTEGER,
    champion     TEXT,
    kills        INTEGER,
    deaths       INTEGER,
    assists      INTEGER,
    game_duration INTEGER
);
"""


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _is_valid(match):
    info = match.get("info", {})
    if info.get("gameDuration", 0) < 300:
        return False
    if len(info.get("participants", [])) != 10:
        return False
    return True


def run_pipeline(riot_id: str, num_matches: int, progress_callback=None):
    game_name, tag_line = riot_id.split("#")
    puuid = get_puuid(game_name, tag_line)
    logger.info("Resolved %s -> puuid %s...", riot_id, puuid[:8])

    match_ids = get_match_ids(puuid, count=num_matches)
    total = len(match_ids)
    logger.info("Fetching %d matches...", total)

    conn = get_conn()
    written = skipped = 0

    for i, mid in enumerate(match_ids, 1):
        # skip if already in db
        existing = conn.execute("SELECT 1 FROM matches WHERE match_id=?", (mid,)).fetchone()
        if existing:
            skipped += 1
            if progress_callback:
                progress_callback(i, total)
            continue

        try:
            match = get_match(mid)
        except Exception as e:
            logger.warning("Skipping %s: %s", mid, e)
            skipped += 1
            if progress_callback:
                progress_callback(i, total)
            continue

        if not _is_valid(match):
            skipped += 1
            if progress_callback:
                progress_callback(i, total)
            continue

        info = match["info"]
        # find this player's participant row
        participant = next((p for p in info["participants"] if p["puuid"] == puuid), None)
        if not participant:
            skipped += 1
            continue

        # convert ms timestamp to local hour
        ts_ms = info.get("gameStartTimestamp", 0)
        ts_s = ts_ms / 1000
        hour = datetime.fromtimestamp(ts_s).hour  # local time

        conn.execute(
            """INSERT OR IGNORE INTO matches
               (match_id, puuid, game_start, hour_of_day, win, champion, kills, deaths, assists, game_duration)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                mid, puuid, ts_ms, hour,
                1 if participant.get("win") else 0,
                participant.get("championName"),
                participant.get("kills"),
                participant.get("deaths"),
                participant.get("assists"),
                info.get("gameDuration"),
            )
        )
        conn.commit()
        written += 1

        if progress_callback:
            progress_callback(i, total)

        time.sleep(1.2)

    conn.close()
    logger.info("Done. Wrote %d, skipped %d.", written, skipped)
    return written, skipped


def get_winrate_by_hour(puuid: str, last_n: int):
    """
    Returns a list of 24 dicts {hour, games, wins, win_rate}
    considering only the last_n matches for this puuid.
    """
    conn = get_conn()

    # get the last_n match_ids ordered by game_start desc
    rows = conn.execute(
        """
        WITH recent AS (
            SELECT * FROM matches
            WHERE puuid = ?
            ORDER BY game_start DESC
            LIMIT ?
        )
        SELECT
            hour_of_day,
            COUNT(*) as games,
            SUM(win) as wins
        FROM recent
        GROUP BY hour_of_day
        ORDER BY hour_of_day
        """,
        (puuid, last_n)
    ).fetchall()
    conn.close()

    # build full 24-hour array, filling 0 for hours with no games
    by_hour = {r[0]: {"games": r[1], "wins": r[2]} for r in rows}
    result = []
    for h in range(24):
        d = by_hour.get(h, {"games": 0, "wins": 0})
        win_rate = round(d["wins"] / d["games"] * 100, 1) if d["games"] > 0 else None
        result.append({
            "hour": h,
            "games": d["games"],
            "wins": d["wins"],
            "win_rate": win_rate,
        })
    return result


def get_summary(puuid: str, last_n: int):
    conn = get_conn()
    row = conn.execute(
        """
        WITH recent AS (
            SELECT * FROM matches WHERE puuid=? ORDER BY game_start DESC LIMIT ?
        )
        SELECT COUNT(*), SUM(win),
               ROUND(AVG(kills),1), ROUND(AVG(deaths),1), ROUND(AVG(assists),1)
        FROM recent
        """,
        (puuid, last_n)
    ).fetchone()
    conn.close()
    games, wins, k, d, a = row
    return {
        "games": games or 0,
        "wins": wins or 0,
        "win_rate": round((wins or 0) / games * 100, 1) if games else 0,
        "avg_kills": k or 0,
        "avg_deaths": d or 0,
        "avg_assists": a or 0,
    }


def get_stored_puuid(riot_id: str):
    """Return a cached puuid for this riot_id if we have any matches stored."""
    conn = get_conn()
    row = conn.execute("SELECT puuid FROM matches LIMIT 1").fetchone()
    conn.close()
    return row[0] if row else None
