# MLB Betting Data Pipeline

This project focuses on MLB betting-related data collection and enrichment.
It builds daily datasets under `data/YYYYMMDD` with three layers:

1. `Roster`: lineup and probable pitcher data
2. `Bet`: Taiwan Sports Lottery MLB market odds
3. `PlayerData`: enriched player/team metrics for modeling and analysis

## Project Structure

```text
PlaywrightMCP/
├─ src/
│  ├─ scrapers/
│  │  ├─ mlb_playwright_scraper.py
│  │  └─ sportslottery_baseball_bet_scraper.py
│  └─ enrichers/
│     └─ roster_player_data_enricher.py
├─ scripts/
│  └─ run_daily_scraper.ps1
├─ data/
│  └─ YYYYMMDD/
│     ├─ Roster/
│     ├─ Bet/
│     └─ PlayerData/
├─ runtime/
│  └─ logs/
├─ docs/
└─ README.md
```

## Requirements

1. Windows
2. Python 3.13+
3. Playwright for Python
4. Git

## Core Scripts

1. `src/scrapers/mlb_playwright_scraper.py`
- Scrapes MLB probable pitcher preview pages and writes `Roster` JSON files.

2. `src/scrapers/sportslottery_baseball_bet_scraper.py`
- Scrapes MLB betting markets and odds from Taiwan Sports Lottery and writes `Bet` JSON files.

3. `src/enrichers/roster_player_data_enricher.py`
- Reads `Roster` JSON files and enriches player/team data with season, advanced, and recent performance metrics.

## Local Run

Run MLB roster scraper:

```powershell
C:/Users/Weihsuan/AppData/Local/Programs/Python/Python313/python.exe .\src\scrapers\mlb_playwright_scraper.py
```

Run betting market scraper:

```powershell
C:/Users/Weihsuan/AppData/Local/Programs/Python/Python313/python.exe .\src\scrapers\sportslottery_baseball_bet_scraper.py
```

Run enrichment for one matchup file:

```powershell
C:/Users/Weihsuan/Desktop/PlaywrightMCP/.venv/Scripts/python.exe .\src\enrichers\roster_player_data_enricher.py --date 20260721 --file TOR_TB_20260721.json
```

Run enrichment for all files in one date:

```powershell
C:/Users/Weihsuan/Desktop/PlaywrightMCP/.venv/Scripts/python.exe .\src\enrichers\roster_player_data_enricher.py --date 20260721 --all
```

Run scheduled wrapper manually:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_daily_scraper.ps1
```

## Notes

1. Daily outputs are written under `data/YYYYMMDD`.
2. Runtime logs are written under `runtime/logs`.
3. This repository is scoped to MLB betting workflows; Playwright MCP config files are excluded from future updates via `.gitignore`.
