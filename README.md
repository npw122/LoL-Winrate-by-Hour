# LoL Win Rate by Hour

A Flask web application that analyzes your League of Legends match history and visualizes your win rate by hour of day.

Demo: [lol-winrate-by-hour-production.up.railway.app](https://lol-winrate-by-hour-production.up.railway.app)

Use Dun#NA1 as an example id


1. Enter your Riot ID (Name#TAG) and number of matches to analyze
2. The pipeline fetches your match history from the Riot Games API
3. Win rate is computed per hour of day using SQLite and displayed as a bar chart

## Tech stack
- Python, Flask, SQLite
- Riot Games API (match-v5)
- Chart.js
- Deployed on Railway

## Run locally
```bash
pip install -r requirements.txt
# Add your Riot API key to .env
python app.py
```
