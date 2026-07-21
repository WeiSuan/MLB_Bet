import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


MLB_API_BASE = "https://statsapi.mlb.com/api/v1"


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_json(session: requests.Session, url: str, params: dict[str, Any]) -> dict[str, Any]:
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def load_team_map(session: requests.Session) -> dict[str, dict[str, Any]]:
    payload = get_json(session, f"{MLB_API_BASE}/teams", {"sportId": 1})

    team_map: dict[str, dict[str, Any]] = {}
    for team in payload.get("teams", []):
        abbr = (team.get("abbreviation") or "").upper()
        if not abbr:
            continue
        team_map[abbr] = {
            "id": team.get("id"),
            "name": team.get("name"),
        }
    return team_map


def parse_roster_name(name: str) -> tuple[str, str]:
    raw = (name or "").strip()
    if not raw:
        return "", ""

    if "," in raw:
        last = raw.split(",", 1)[0].strip()
        query = last
    else:
        query = raw
        tokens = raw.split()
        last = tokens[-1] if tokens else raw

    # Remove punctuation and common suffixes for more stable name matching.
    last = re.sub(r"\b(JR|SR|II|III|IV)\.?$", "", last, flags=re.IGNORECASE).strip()
    query = re.sub(r"\b(JR|SR|II|III|IV)\.?$", "", query, flags=re.IGNORECASE).strip()

    return query, last


def search_player(
    session: requests.Session,
    name_query: str,
    team_id: int | None,
    last_name_hint: str,
) -> dict[str, Any] | None:
    if not name_query:
        return None

    payload = get_json(
        session,
        f"{MLB_API_BASE}/people/search",
        {"sportId": 1, "names": name_query},
    )
    people = payload.get("people", [])
    if not people:
        return None

    filtered = people
    if team_id is not None:
        by_team = [p for p in people if p.get("currentTeam", {}).get("id") == team_id]
        if by_team:
            filtered = by_team

    if last_name_hint:
        by_last = [
            p
            for p in filtered
            if (p.get("lastName") or "").lower().startswith(last_name_hint.lower())
        ]
        if by_last:
            filtered = by_last

    return filtered[0] if filtered else None


def fetch_player_stats(
    session: requests.Session,
    player_id: int,
    season: int,
    group: str,
) -> dict[str, Any]:
    payload = get_json(
        session,
        f"{MLB_API_BASE}/people/{player_id}/stats",
        {
            "stats": "season,seasonAdvanced",
            "group": group,
            "season": season,
        },
    )
    stats_data = payload.get("stats", [])

    result = {
        "season": {},
        "seasonAdvanced": {},
    }

    for item in stats_data:
        stat_type = (item.get("type", {}).get("displayName") or "").lower()
        splits = item.get("splits", [])
        if not splits:
            continue
        stat = splits[0].get("stat", {})

        if "advanced" in stat_type:
            result["seasonAdvanced"] = stat
        elif "season" in stat_type:
            result["season"] = stat

    return result


def fetch_player_game_log(
    session: requests.Session,
    player_id: int,
    season: int,
    group: str,
) -> list[dict[str, Any]]:
    payload = get_json(
        session,
        f"{MLB_API_BASE}/people/{player_id}/stats",
        {
            "stats": "gameLog",
            "group": group,
            "season": season,
        },
    )

    stats_data = payload.get("stats", [])
    if not stats_data:
        return []

    splits = stats_data[0].get("splits", [])
    normalized = []
    for row in splits:
        normalized.append(
            {
                "date": row.get("date"),
                "opponent": row.get("opponent", {}).get("name"),
                "isHome": row.get("isHome"),
                "stat": row.get("stat", {}),
            }
        )

    normalized.sort(key=lambda x: x.get("date") or "", reverse=True)
    return normalized


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("."):
        text = f"0{text}"
    try:
        return float(text)
    except ValueError:
        return None


def summarize_recent_games(game_logs: list[dict[str, Any]], window: int, group: str) -> dict[str, Any]:
    recent_games = game_logs[:window]

    if group == "pitching":
        allowed_keys = {
            "runs",
            "earnedRuns",
            "hits",
            "baseOnBalls",
            "strikeOuts",
            "homeRuns",
            "battersFaced",
        }
    else:
        allowed_keys = {
            "atBats",
            "hits",
            "baseOnBalls",
            "hitByPitch",
            "sacFlies",
            "strikeOuts",
            "homeRuns",
            "doubles",
            "triples",
            "rbi",
            "runs",
            "stolenBases",
            "caughtStealing",
        }

    sums: dict[str, float] = {"inningsPitchedOuts": 0.0} if group == "pitching" else {}
    for game in recent_games:
        for key, value in game.get("stat", {}).items():
            if group == "pitching" and key == "inningsPitched":
                sums["inningsPitchedOuts"] = sums.get("inningsPitchedOuts", 0.0) + innings_to_outs(value)
                continue
            if key not in allowed_keys:
                continue
            number = _to_float(value)
            if number is None:
                continue
            sums[key] = sums.get(key, 0.0) + number

    if group == "pitching":
        outs = sums.get("inningsPitchedOuts", 0.0)
        sums["inningsPitched"] = round(outs / 3, 3)

    for k, v in list(sums.items()):
        if float(v).is_integer():
            sums[k] = int(v)

    return {
        "games_count": len(recent_games),
        "summary": sums,
    }


def innings_to_outs(innings_pitched: Any) -> int:
    text = str(innings_pitched or "0").strip()
    if not text:
        return 0
    if "." in text:
        whole, frac = text.split(".", 1)
        whole_outs = int(whole) * 3 if whole.isdigit() else 0
        frac_outs = int(frac[:1]) if frac[:1].isdigit() else 0
        return whole_outs + frac_outs
    if text.isdigit():
        return int(text) * 3
    return 0


def build_hitter_recent_indicators(summary: dict[str, Any], games_count: int) -> dict[str, Any]:
    ab = float(summary.get("atBats", 0) or 0)
    h = float(summary.get("hits", 0) or 0)
    bb = float(summary.get("baseOnBalls", 0) or 0)
    hbp = float(summary.get("hitByPitch", 0) or 0)
    sf = float(summary.get("sacFlies", 0) or 0)
    k = float(summary.get("strikeOuts", 0) or 0)
    hr = float(summary.get("homeRuns", 0) or 0)
    doubles = float(summary.get("doubles", 0) or 0)
    triples = float(summary.get("triples", 0) or 0)

    singles = max(h - doubles - triples - hr, 0)
    total_bases = singles + doubles * 2 + triples * 3 + hr * 4

    avg = round(h / ab, 3) if ab else None
    obp_den = ab + bb + hbp + sf
    obp = round((h + bb + hbp) / obp_den, 3) if obp_den else None
    slg = round(total_bases / ab, 3) if ab else None
    ops = round((obp or 0) + (slg or 0), 3) if obp is not None and slg is not None else None
    iso = round((slg or 0) - (avg or 0), 3) if slg is not None and avg is not None else None
    k_rate = round(k / (ab + bb + hbp), 3) if (ab + bb + hbp) else None
    bb_rate = round(bb / (ab + bb + hbp), 3) if (ab + bb + hbp) else None
    hr_rate = round(hr / (ab + bb + hbp), 3) if (ab + bb + hbp) else None

    return {
        "games_count": games_count,
        "AVG": avg,
        "OBP": obp,
        "SLG": slg,
        "OPS": ops,
        "ISO": iso,
        "K_rate": k_rate,
        "BB_rate": bb_rate,
        "HR_rate": hr_rate,
        "RBI_per_game": round(float(summary.get("rbi", 0) or 0) / games_count, 3)
        if games_count
        else None,
        "Runs_per_game": round(float(summary.get("runs", 0) or 0) / games_count, 3)
        if games_count
        else None,
    }


def build_pitcher_recent_indicators(summary: dict[str, Any], games_count: int) -> dict[str, Any]:
    ip_outs = innings_to_outs(summary.get("inningsPitched", "0"))
    ip = ip_outs / 3 if ip_outs else 0

    er = float(summary.get("earnedRuns", 0) or 0)
    hits = float(summary.get("hits", 0) or 0)
    bb = float(summary.get("baseOnBalls", 0) or 0)
    k = float(summary.get("strikeOuts", 0) or 0)
    hr = float(summary.get("homeRuns", 0) or 0)

    era = round((er * 9) / ip, 3) if ip else None
    whip = round((hits + bb) / ip, 3) if ip else None
    k9 = round((k * 9) / ip, 3) if ip else None
    bb9 = round((bb * 9) / ip, 3) if ip else None
    hr9 = round((hr * 9) / ip, 3) if ip else None
    kbb = round(k / bb, 3) if bb else None

    return {
        "games_count": games_count,
        "innings_pitched": round(ip, 3) if ip else 0,
        "ERA": era,
        "WHIP": whip,
        "K_per_9": k9,
        "BB_per_9": bb9,
        "HR_per_9": hr9,
        "K_BB_ratio": kbb,
        "ER_per_game": round(er / games_count, 3) if games_count else None,
        "Hits_per_game": round(hits / games_count, 3) if games_count else None,
    }


def fetch_pitcher_handedness_splits(
    session: requests.Session,
    player_id: int,
    season: int,
) -> dict[str, Any]:
    output: dict[str, Any] = {}

    for code, key in [("vl", "vs_left_handed_batters"), ("vr", "vs_right_handed_batters")]:
        payload = get_json(
            session,
            f"{MLB_API_BASE}/people/{player_id}/stats",
            {
                "stats": "statSplits",
                "group": "pitching",
                "season": season,
                "sitCodes": code,
            },
        )

        stats = payload.get("stats", [])
        splits = stats[0].get("splits", []) if stats else []
        if not splits:
            output[key] = {}
            continue

        stat = splits[0].get("stat", {})
        output[key] = {
            "AVG": stat.get("avg"),
            "OBP": stat.get("obp"),
            "SLG": stat.get("slg"),
            "OPS": stat.get("ops"),
            "ERA": stat.get("era"),
            "WHIP": stat.get("whip"),
            "inningsPitched": stat.get("inningsPitched"),
            "plateAppearances": stat.get("plateAppearances"),
            "strikeOuts": stat.get("strikeOuts"),
            "baseOnBalls": stat.get("baseOnBalls"),
            "homeRuns": stat.get("homeRuns"),
            "hits": stat.get("hits"),
        }

    return output


def fetch_team_group_stats(
    session: requests.Session,
    team_id: int,
    season: int,
    group: str,
) -> dict[str, Any]:
    payload = get_json(
        session,
        f"{MLB_API_BASE}/teams/{team_id}/stats",
        {
            "stats": "season,seasonAdvanced",
            "group": group,
            "season": season,
        },
    )

    output = {"season": {}, "seasonAdvanced": {}}
    for item in payload.get("stats", []):
        stat_type = (item.get("type", {}).get("displayName") or "").lower()
        splits = item.get("splits", [])
        if not splits:
            continue
        stat = splits[0].get("stat", {})
        if "advanced" in stat_type:
            output["seasonAdvanced"] = stat
        elif "season" in stat_type:
            output["season"] = stat
    return output


def fetch_team_last_n_games(
    session: requests.Session,
    team_id: int,
    end_date: str,
    n_games: int = 10,
) -> dict[str, Any]:
    dt_end = datetime.strptime(end_date, "%Y-%m-%d")
    dt_start = dt_end - timedelta(days=40)

    payload = get_json(
        session,
        f"{MLB_API_BASE}/schedule",
        {
            "sportId": 1,
            "teamId": team_id,
            "startDate": dt_start.strftime("%Y-%m-%d"),
            "endDate": end_date,
        },
    )

    all_games = []
    for d in payload.get("dates", []):
        all_games.extend(d.get("games", []))

    all_games.sort(key=lambda g: g.get("gameDate") or "", reverse=True)

    recent = []
    wins = 0
    losses = 0
    runs_for = 0
    runs_against = 0

    for game in all_games:
        if len(recent) >= n_games:
            break

        detailed = game.get("status", {}).get("detailedState", "")
        if "Final" not in detailed:
            continue

        home_team = game.get("teams", {}).get("home", {}).get("team", {}).get("id")
        away_team = game.get("teams", {}).get("away", {}).get("team", {}).get("id")
        home_score = game.get("teams", {}).get("home", {}).get("score")
        away_score = game.get("teams", {}).get("away", {}).get("score")

        if home_score is None or away_score is None:
            continue

        is_home = home_team == team_id
        team_score = home_score if is_home else away_score
        opp_score = away_score if is_home else home_score
        result = "W" if team_score > opp_score else "L"

        if result == "W":
            wins += 1
        else:
            losses += 1

        runs_for += int(team_score)
        runs_against += int(opp_score)

        opponent_name = (
            game.get("teams", {}).get("away", {}).get("team", {}).get("name")
            if is_home
            else game.get("teams", {}).get("home", {}).get("team", {}).get("name")
        )

        recent.append(
            {
                "date": game.get("gameDate", "")[:10],
                "home_away": "home" if is_home else "away",
                "opponent": opponent_name,
                "team_score": team_score,
                "opponent_score": opp_score,
                "result": result,
            }
        )

    game_count = len(recent)
    return {
        "games_count": game_count,
        "record": f"{wins}-{losses}",
        "win_pct": round(wins / game_count, 3) if game_count else None,
        "runs_for": runs_for,
        "runs_against": runs_against,
        "run_diff": runs_for - runs_against,
        "runs_for_per_game": round(runs_for / game_count, 3) if game_count else None,
        "runs_against_per_game": round(runs_against / game_count, 3) if game_count else None,
        "games": recent,
    }


def fetch_team_metrics(
    session: requests.Session,
    team_id: int,
    season: int,
    end_date: str,
) -> dict[str, Any]:
    return {
        "season": {
            "hitting": fetch_team_group_stats(session, team_id, season, "hitting"),
            "pitching": fetch_team_group_stats(session, team_id, season, "pitching"),
            "fielding": fetch_team_group_stats(session, team_id, season, "fielding"),
        },
        "recent_10_games": fetch_team_last_n_games(session, team_id, end_date, n_games=10),
    }


def build_player_record(
    session: requests.Session,
    player_name: str,
    position: str,
    team_abbr: str,
    season: int,
    team_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    team_info = team_map.get(team_abbr.upper(), {})
    team_id = team_info.get("id")

    query, last_hint = parse_roster_name(player_name)
    person = search_player(session, query, team_id, last_hint)

    if not person:
        return {
            "input_name": player_name,
            "position": position,
            "team": team_abbr,
            "matched": False,
            "error": "Player not found in MLB API search.",
        }

    player_id = person.get("id")
    basic_info = {
        "id": player_id,
        "fullName": person.get("fullName"),
        "firstName": person.get("firstName"),
        "lastName": person.get("lastName"),
        "primaryNumber": person.get("primaryNumber"),
        "birthDate": person.get("birthDate"),
        "currentAge": person.get("currentAge"),
        "height": person.get("height"),
        "weight": person.get("weight"),
        "batSide": person.get("batSide", {}).get("description"),
        "pitchHand": person.get("pitchHand", {}).get("description"),
        "currentTeam": person.get("currentTeam", {}).get("name"),
        "primaryPosition": person.get("primaryPosition", {}).get("abbreviation"),
        "status": person.get("status", {}).get("description"),
    }

    hitting_stats = fetch_player_stats(session, player_id, season, "hitting") if player_id else {}
    pitching_stats = fetch_player_stats(session, player_id, season, "pitching") if player_id else {}

    primary_position = basic_info.get("primaryPosition") or position
    is_pitcher = str(primary_position).upper() == "P"
    recent_group = "pitching" if is_pitcher else "hitting"
    recent_window = 5 if is_pitcher else 10
    recent_logs = (
        fetch_player_game_log(session, player_id, season, recent_group) if player_id else []
    )
    recent_summary = summarize_recent_games(recent_logs, recent_window, recent_group)
    recent_indicators = (
        build_pitcher_recent_indicators(
            recent_summary.get("summary", {}), recent_summary.get("games_count", 0)
        )
        if is_pitcher
        else build_hitter_recent_indicators(
            recent_summary.get("summary", {}), recent_summary.get("games_count", 0)
        )
    )

    handedness_splits = (
        fetch_pitcher_handedness_splits(session, int(player_id), season)
        if player_id and is_pitcher
        else {}
    )

    return {
        "input_name": player_name,
        "position": position,
        "team": team_abbr,
        "matched": True,
        "basic_info": basic_info,
        "stats": {
            "season": {
                "hitting": hitting_stats,
                "pitching": pitching_stats,
            },
            "recent": {
                "role": "pitcher" if is_pitcher else "hitter_or_catcher",
                "scope": f"last_{recent_window}_games",
                "group": recent_group,
                "indicators": recent_indicators,
                "raw_summary": recent_summary,
            },
            "pitcher_vs_handedness": handedness_splits,
        },
    }


def resolve_roster_dir(date_dir: Path) -> Path:
    roaster_dir = date_dir / "Roaster"
    roster_dir = date_dir / "Roster"

    if roaster_dir.exists():
        return roaster_dir
    if roster_dir.exists():
        return roster_dir

    raise FileNotFoundError(
        f"Cannot find roster directory. Checked: {roaster_dir} and {roster_dir}"
    )


def enrich_file(
    session: requests.Session,
    roster_file: Path,
    season: int,
    date_iso: str,
    team_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    # Load one roster matchup file and enrich every team/player entry.
    payload = json.loads(roster_file.read_text(encoding="utf-8"))

    teams_output: dict[str, Any] = {}
    for team_abbr, team_data in payload.items():
        team_id = team_map.get(team_abbr, {}).get("id")
        team_metrics = {}
        if team_id:
            try:
                team_metrics = fetch_team_metrics(session, int(team_id), season, date_iso)
            except Exception as exc:
                team_metrics = {"error": str(exc)}

        starting_pitcher_name = team_data.get("starting_pitcher", "")
        if starting_pitcher_name:
            try:
                starting_pitcher_profile = build_player_record(
                    session=session,
                    player_name=starting_pitcher_name,
                    position="P",
                    team_abbr=team_abbr,
                    season=season,
                    team_map=team_map,
                )
            except Exception as exc:
                starting_pitcher_profile = {
                    "input_name": starting_pitcher_name,
                    "position": "P",
                    "team": team_abbr,
                    "matched": False,
                    "error": str(exc),
                }
        else:
            starting_pitcher_profile = {}

        players = team_data.get("roster", [])
        enriched_players = []

        for player in players:
            player_name = player.get("name", "")
            position = player.get("position", "")
            try:
                # Enrich roster player with season stats, recent indicators and splits.
                enriched = build_player_record(
                    session=session,
                    player_name=player_name,
                    position=position,
                    team_abbr=team_abbr,
                    season=season,
                    team_map=team_map,
                )
            except Exception as exc:
                enriched = {
                    "input_name": player_name,
                    "position": position,
                    "team": team_abbr,
                    "matched": False,
                    "error": str(exc),
                }
            enriched_players.append(enriched)

        teams_output[team_abbr] = {
            "home_away": team_data.get("home_away"),
            "starting_pitcher": team_data.get("starting_pitcher"),
            "starting_pitcher_profile": starting_pitcher_profile,
            "team_metrics": team_metrics,
            "players": enriched_players,
        }

    return {
        "source_file": roster_file.name,
        "season": season,
        "teams": teams_output,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read YYYYMMDD/Roaster(or Roster) game rosters and enrich players with MLB basic info and advanced stats."
    )
    parser.add_argument(
        "--date",
        default="",
        help="Target date directory in YYYYMMDD. Default: latest date folder in current directory.",
    )
    parser.add_argument(
        "--file",
        default="",
        help="Specific roster filename. Default: first json file in roster folder.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all roster files. Default is single-file mode for faster testing.",
    )
    args = parser.parse_args()

    # Resolve paths from file location so execution is stable from any cwd.
    project_root = Path(__file__).resolve().parents[2]
    data_root = project_root / "data"

    if args.date:
        date_dir = data_root / args.date
    else:
        date_dirs = sorted(
            [p for p in data_root.iterdir() if p.is_dir() and re.fullmatch(r"\d{8}", p.name)]
        )
        if not date_dirs:
            raise FileNotFoundError("No YYYYMMDD directories found in data directory.")
        date_dir = date_dirs[-1]

    season = int(date_dir.name[:4])
    roster_dir = resolve_roster_dir(date_dir)

    if args.file:
        roster_files = [roster_dir / args.file]
    elif args.all:
        roster_files = sorted(roster_dir.glob("*.json"))
    else:
        first_file = sorted(roster_dir.glob("*.json"))[:1]
        roster_files = first_file

    if not roster_files:
        raise FileNotFoundError(f"No roster json files found in {roster_dir}")

    # Write enriched output beside source roster files.
    output_dir = date_dir / "PlayerData"
    output_dir.mkdir(parents=True, exist_ok=True)

    session = build_session()
    team_map = load_team_map(session)
    date_iso = datetime.strptime(date_dir.name, "%Y%m%d").strftime("%Y-%m-%d")

    for roster_file in roster_files:
        if not roster_file.exists():
            print(f"Skip missing file: {roster_file}")
            continue

        print(f"Enriching: {roster_file.name}")
        enriched_payload = enrich_file(session, roster_file, season, date_iso, team_map)

        output_file = output_dir / roster_file.name
        output_file.write_text(
            json.dumps(enriched_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Saved: {output_file}")

    print(f"Done. Output directory: {output_dir}")


if __name__ == "__main__":
    main()
