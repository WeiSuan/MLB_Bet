import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
PROBABLE_PITCHERS_URL = "https://www.mlb.com/probable-pitchers"
PREVIEW_URL_TEMPLATE = "https://www.mlb.com/gameday/{game_pk}/preview"


def normalize_pitcher_name(full_name: str) -> str:
    full_name = (full_name or "").strip()
    if not full_name:
        return ""
    parts = full_name.split()
    return parts[-1]


def get_today_schedule(page: Page, run_date_iso: str) -> list[dict[str, Any]]:
    response = page.request.get(
        f"{SCHEDULE_URL}?sportId=1&date={run_date_iso}&hydrate=team,probablePitcher"
    )
    payload = response.json()
    games: list[dict[str, Any]] = []

    for date_item in payload.get("dates", []):
        games.extend(date_item.get("games", []))

    return games


def extract_matchup_rosters(page: Page) -> dict[str, dict[str, Any]]:
    return page.evaluate(
        """
        () => {
          const data = {};
          const tables = Array.from(document.querySelectorAll('table'));

          for (const table of tables) {
            const headerCell = table.querySelector('thead th');
            if (!headerCell) continue;

            const header = headerCell.textContent.replace(/\\s+/g, ' ').trim();
            const upperHeader = header.toUpperCase();
            const vsIndex = upperHeader.indexOf('VS');
            if (vsIndex === -1) continue;

            const leftSide = header.slice(0, vsIndex).trim();
            const rightSide = header.slice(vsIndex).replace(/^vs\\.?\\s*/i, '').trim();

            const teamAbbr = leftSide.replace(/[^A-Z]/g, '').trim();
            const opposingPitcher = rightSide;
            if (!teamAbbr || !opposingPitcher) continue;
            const roster = [];

            const rows = Array.from(table.querySelectorAll('tbody tr'));
            for (const row of rows) {
              const firstCell = row.querySelector('td');
              if (!firstCell) continue;

              const nameEl = firstCell.querySelector('a');
              if (!nameEl) continue;

              const name = nameEl.textContent.trim();
              const cellText = firstCell.textContent.replace(/\\s+/g, ' ').trim();
              const position = cellText.replace(name, '').trim().split(' ')[0] || '';

              if (!name || !position) continue;
              roster.push({ name, position });
            }

            data[teamAbbr] = {
              opposing_pitcher: opposingPitcher,
              roster,
            };
          }

          return data;
        }
        """
    )


def build_team_payload(
    game_data: dict[str, Any],
    matchup_rosters: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str, str]:
    away_abbr = game_data["teams"]["away"]["team"]["abbreviation"]
    home_abbr = game_data["teams"]["home"]["team"]["abbreviation"]

    away_pitcher = normalize_pitcher_name(
        game_data["teams"]["away"].get("probablePitcher", {}).get("fullName", "")
    )
    home_pitcher = normalize_pitcher_name(
        game_data["teams"]["home"].get("probablePitcher", {}).get("fullName", "")
    )

    # Fallback if API does not provide probable pitchers.
    if not away_pitcher or not home_pitcher:
        teams = list(matchup_rosters.keys())
        if len(teams) == 2:
            t0, t1 = teams[0], teams[1]
            if not home_pitcher:
                home_pitcher = matchup_rosters.get(t1 if home_abbr == t0 else t0, {}).get(
                    "opposing_pitcher", ""
                )
            if not away_pitcher:
                away_pitcher = matchup_rosters.get(t1 if away_abbr == t0 else t0, {}).get(
                    "opposing_pitcher", ""
                )

    output = {
        home_abbr: {
            "home_away": "home",
            "starting_pitcher": home_pitcher,
            "roster": matchup_rosters.get(home_abbr, {}).get("roster", []),
        },
        away_abbr: {
            "home_away": "away",
            "starting_pitcher": away_pitcher,
            "roster": matchup_rosters.get(away_abbr, {}).get("roster", []),
        },
    }

    return output, home_abbr, away_abbr


def main() -> None:
    # Resolve paths from file location so execution is stable from any cwd.
    project_root = Path(__file__).resolve().parents[2]
    data_root = project_root / "data"

    run_date = datetime.now()
    run_date_iso = run_date.strftime("%Y-%m-%d")
    run_date_stamp = run_date.strftime("%Y%m%d")

    # Persist raw roster output under data/YYYYMMDD/Roster.
    output_dir = data_root / run_date_stamp / "Roster"
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Enter the page requested by the user and initialize session.
        page.goto(PROBABLE_PITCHERS_URL, wait_until="domcontentloaded")

        games = get_today_schedule(page, run_date_iso)
        if not games:
            print(f"No games found for {run_date_iso}.")
            browser.close()
            return

        saved_files = 0

        for game in games:
            game_pk = game.get("gamePk")
            if not game_pk:
                continue

            # Open game preview page and extract projected lineup table.
            preview_url = PREVIEW_URL_TEMPLATE.format(game_pk=game_pk)
            page.goto(preview_url, wait_until="domcontentloaded")
            page.wait_for_selector("table", timeout=20000)

            matchup_rosters = extract_matchup_rosters(page)
            if not matchup_rosters:
                print(f"Skip game {game_pk}: no matchup roster table found.")
                continue

            payload, home_abbr, away_abbr = build_team_payload(game, matchup_rosters)

            filename = f"{home_abbr}_{away_abbr}_{run_date_stamp}.json"
            file_path = output_dir / filename
            file_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            saved_files += 1
            print(f"Saved {file_path.name}")

        browser.close()

    print(f"Done. Saved {saved_files} game file(s) to: {output_dir}")


if __name__ == "__main__":
    main()
