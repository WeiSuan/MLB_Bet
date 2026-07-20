# Playwright MLB Probable Pitchers Scraper

This project uses Python + Playwright to scrape MLB probable pitchers preview pages and export per-game JSON files for the current day.

## Features

- Scrape all games for the current date from https://www.mlb.com/probable-pitchers.
- Open each game's Preview page and collect:
  - team abbreviation
  - home/away
  - starting pitcher
  - projected lineup roster (name + position)
- Save one JSON file per game using this naming format:
  - `{HOME}_{AWAY}_{YYMMDD}.json`
- Create a date folder automatically in the project root.
- Daily scheduled script supports auto sync to GitHub (`git add/commit/push`).

## Project Structure

- `mlb_playwright_scraper.py`: main scraper script.
- `run_daily_scraper.ps1`: scheduled entry script (run scraper, write logs, auto git sync).
- `playwright_mcp_install_guide.md`: Playwright MCP setup guide.
- `logs/`: runtime logs from scheduled jobs.
- `<YYMMDD>/`: daily output folder with JSON files.

## Requirements

- Windows
- Python 3.13+
- Node.js 18+ (for Playwright MCP usage in VS Code)
- Git

## Local Run

Run scraper manually:

```powershell
C:/Users/Weihsuan/AppData/Local/Programs/Python/Python313/python.exe .\mlb_playwright_scraper.py
```

Run scheduled wrapper script manually:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_daily_scraper.ps1
```

## Output Format

Example (`NYY_PIT_260720.json`):

```json
{
  "NYY": {
    "home_away": "home",
    "starting_pitcher": "Weathers",
    "roster": [
      { "name": "Bellinger", "position": "LF" }
    ]
  },
  "PIT": {
    "home_away": "away",
    "starting_pitcher": "Ashcraft",
    "roster": [
      { "name": "Callihan, T", "position": "LF" }
    ]
  }
}
```

## Daily Scheduling (Windows Task Scheduler)

The project already includes a scheduled task:

- Task name: `PlaywrightMlbScraperDaily`
- Schedule: Daily at `09:00`

Check task:

```powershell
schtasks /Query /TN PlaywrightMlbScraperDaily /V /FO LIST
```

Run task immediately:

```powershell
schtasks /Run /TN PlaywrightMlbScraperDaily
```

## Auto Git Sync Behavior

After scraper succeeds, `run_daily_scraper.ps1` will:

1. `git add -A`
2. skip commit/push if no changes
3. commit with message: `daily scraper update: YYYY-MM-DD`
4. push to `origin main`

If scraper fails, git sync is skipped.

## Notes

- Ensure your Git credentials are configured so scheduled runs can push without manual input.
- `logs/` is ignored by git (`.gitignore`).
