import os
import time
import logging
import requests
from dotenv import load_dotenv

from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REGIONAL_ROUTE = "americas"
MAX_RETRIES = 5


def _headers():
    key = os.environ.get("RIOT_API_KEY")
    if not key:
        raise RuntimeError("Set RIOT_API_KEY in your .env file.")
    return {"X-Riot-Token": key}


def _get(url, params=None):
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.get(url, headers=_headers(), params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            logger.warning("Rate limited. Sleeping %ss", retry_after)
            time.sleep(retry_after)
            continue
        if 500 <= resp.status_code < 600:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Max retries exceeded for {url}")


def get_puuid(game_name, tag_line):
    url = f"https://{REGIONAL_ROUTE}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    return _get(url)["puuid"]


def get_match_ids(puuid, count=20):
    url = f"https://{REGIONAL_ROUTE}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    return _get(url, params={"start": 0, "count": count})


def get_match(match_id):
    url = f"https://{REGIONAL_ROUTE}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return _get(url)
