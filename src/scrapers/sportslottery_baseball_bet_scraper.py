import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from playwright.sync_api import Page, sync_playwright


SPORT_URL = "https://www.sportslottery.com.tw/sportsbook/sport/%E6%A3%92%E7%90%83/34731.1"
MLB_URL_KEYWORD = "美國職棒"


TEAM_ABBR_MAP = {
	"arizona diamondbacks": "AZ",
	"atlanta braves": "ATL",
	"athletics": "ATH",
	"athletics mlb": "ATH",
	"baltimore orioles": "BAL",
	"boston red sox": "BOS",
	"chicago cubs": "CHC",
	"chicago white sox": "CWS",
	"cincinnati reds": "CIN",
	"cleveland guardians": "CLE",
	"colorado rockies": "COL",
	"detroit tigers": "DET",
	"houston astros": "HOU",
	"kansas city royals": "KC",
	"los angeles angels": "LAA",
	"los angeles dodgers": "LAD",
	"miami marlins": "MIA",
	"milwaukee brewers": "MIL",
	"minnesota twins": "MIN",
	"new york mets": "NYM",
	"new york yankees": "NYY",
	"philadelphia phillies": "PHI",
	"pittsburgh pirates": "PIT",
	"san diego padres": "SD",
	"san francisco giants": "SF",
	"seattle mariners": "SEA",
	"st louis cardinals": "STL",
	"tampa bay rays": "TB",
	"texas rangers": "TEX",
	"toronto blue jays": "TOR",
	"washington nationals": "WSH",
	"亞利桑那響尾蛇": "AZ",
	"亞特蘭大勇士": "ATL",
	"運動家": "ATH",
	"奧克蘭運動家": "ATH",
	"巴爾的摩金鶯": "BAL",
	"波士頓紅襪": "BOS",
	"芝加哥小熊": "CHC",
	"芝加哥白襪": "CWS",
	"辛辛那提紅人": "CIN",
	"克里夫蘭守護者": "CLE",
	"科羅拉多洛磯": "COL",
	"底特律老虎": "DET",
	"休士頓太空人": "HOU",
	"堪薩斯市皇家": "KC",
	"洛杉磯天使": "LAA",
	"洛杉磯道奇": "LAD",
	"邁阿密馬林魚": "MIA",
	"密爾瓦基釀酒人": "MIL",
	"明尼蘇達雙城": "MIN",
	"紐約大都會": "NYM",
	"紐約洋基": "NYY",
	"費城費城人": "PHI",
	"匹茲堡海盜": "PIT",
	"聖地牙哥教士": "SD",
	"舊金山巨人": "SF",
	"西雅圖水手": "SEA",
	"聖路易紅雀": "STL",
	"坦帕灣光芒": "TB",
	"德州遊騎兵": "TEX",
	"多倫多藍鳥": "TOR",
	"華盛頓國民": "WSH",
}


TEAM_ABBR_CONTAINS = {
	"亞利桑": "AZ",
	"亞歷桑": "AZ",
	"堪薩斯": "KC",
	"運動家": "ATH",
	"辛辛那": "CIN",
	"科羅拉": "COL",
}


def normalize_team_key(team_name: str) -> str:
	name = (team_name or "").strip()
	name = re.sub(r"\([^)]*\)", "", name)
	name = name.replace("隊", "")
	name = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", name)
	name = re.sub(r"\s+", " ", name).strip()
	return name.lower()


def to_team_abbr(team_name: str) -> str:
	key = normalize_team_key(team_name)
	mapped = TEAM_ABBR_MAP.get(key)
	if mapped:
		return mapped

	for fragment, abbr in TEAM_ABBR_CONTAINS.items():
		if fragment.lower() in key:
			return abbr

	parts = [p for p in key.split(" ") if p]
	if parts:
		if len(parts) >= 2:
			return "".join(part[0] for part in parts[:3]).upper()
		return parts[0][:3].upper()

	return "UNK"


def scroll_for_full_listing(page: Page) -> None:
	stable_count = 0
	last_height = -1

	for _ in range(20):
		page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 1.2))")
		page.wait_for_timeout(400)

		current_height = page.evaluate("document.body.scrollHeight")
		if current_height == last_height:
			stable_count += 1
		else:
			stable_count = 0

		last_height = current_height
		if stable_count >= 3:
			break

	page.evaluate("window.scrollTo(0, 0)")
	page.wait_for_timeout(300)


def collect_event_links(page: Page) -> list[str]:
	links_by_event_id: dict[str, str] = {}

	for _ in range(10):
		results = page.evaluate(
			"""
			() => {
			  return Array.from(document.querySelectorAll('a[href*="/event/"]'))
				.map(a => a.href)
				.filter(Boolean);
			}
			"""
		)
		for href in results:
			if "/sport/" in href and "/event/" in href:
				decoded = unquote(href)
				if MLB_URL_KEYWORD not in decoded:
					continue

				event_match = re.search(r"/event/(\d+\.\d+)", href)
				if not event_match:
					continue
				event_id = event_match.group(1)
				links_by_event_id[event_id] = href

		page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 0.9))")
		page.wait_for_timeout(350)

	return sorted(links_by_event_id.values())


def parse_matchup(label_text: str) -> tuple[str, str]:
	text = (label_text or "").strip()
	match = re.search(r"(.+?)\s*@\s*(.+)", text)
	if not match:
		return "", ""
	away = match.group(1).strip()
	home = match.group(2).strip()
	return away, home


def extract_event_data(page: Page, url: str) -> dict[str, Any]:
	page.goto(url, wait_until="domcontentloaded")
	page.wait_for_timeout(1200)

	try:
		page.get_by_role("button", name="All Markets").click(timeout=2500)
		page.wait_for_timeout(300)
	except Exception:
		pass

	def extract_visible_markets() -> dict[str, Any]:
		scroll_for_full_listing(page)
		return page.evaluate(
			r"""
			() => {
				const headingText = Array.from(document.querySelectorAll('h1, h2'))
					.map(el => (el.textContent || '').replace(/\s+/g, ' ').trim())
					.find(text => text.includes('@')) || '';

				const markets = [];
				const sections = Array.from(document.querySelectorAll('h3'))
					.map(h3 => {
						let node = h3;
						for (let i = 0; i < 8 && node; i += 1) {
							const count = node.querySelectorAll('[role="checkbox"]').length;
							if (count > 0 && count <= 30) {
								return node;
							}
							node = node.parentElement;
						}
						return null;
					})
					.filter(Boolean);

				let participants = [];
				const seen = new Set();

				for (const section of sections) {
					const marketNameEl = section.querySelector('h3');
					const marketName = (marketNameEl?.textContent || '').replace(/\s+/g, ' ').trim();
					if (!marketName) continue;

					const optionEls = Array.from(section.querySelectorAll('[role="checkbox"]'));
					if (!optionEls.length) continue;

					if (!participants.length) {
						const teamText = Array.from(section.querySelectorAll('p'))
							.map(p => (p.textContent || '').replace(/\s+/g, ' ').trim())
							.filter(t => t)
							.filter(t => !/^\d+(\.\d+)?$/.test(t))
							.filter(t => !/^(HOME|AWAY|主場|客場)$/i.test(t))
							.filter(t => !/[+-]\d+(\.\d+)?$/.test(t))
							.filter(t => !/^(Over|Under|大|小)\s*/i.test(t));

						const uniqueTeams = [];
						for (const name of teamText) {
							if (!uniqueTeams.includes(name)) {
								uniqueTeams.push(name);
							}
						}
						if (uniqueTeams.length >= 2) {
							participants = [uniqueTeams[0], uniqueTeams[1]];
						}
					}

					const options = [];
					for (const optionEl of optionEls) {
						const ariaLabel = (optionEl.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
						const m = ariaLabel.match(/-\s*(.*?)\s*-\s*odds\s*([0-9]+(?:\.[0-9]+)?)/i);

						let selection = '';
						let odds = null;

						if (m) {
							selection = (m[1] || '').trim();
							odds = Number(m[2]);
						} else {
							const p = optionEl.querySelector('p');
							selection = (p?.textContent || '').replace(/\s+/g, ' ').trim();

							const numberText = (optionEl.textContent || '').match(/([0-9]+(?:\.[0-9]+))/g);
							if (numberText && numberText.length) {
								odds = Number(numberText[numberText.length - 1]);
							}
						}

						if (!selection || !Number.isFinite(odds)) continue;

						const optionKey = `${marketName}__${selection}__${odds}`;
						if (seen.has(optionKey)) continue;
						seen.add(optionKey);

						options.push({ selection, odds });
					}

					if (options.length) {
						markets.push({
							market: marketName,
							options,
						});
					}
				}

				return { headingText, participants, markets };
			}
			"""
		)

	merged_markets: dict[str, dict[str, Any]] = {}
	heading_text = ""
	participants: list[str] = []

	tabs_to_visit = ["全場", "前 5 局", "前5局", "1-5局"]
	visited_tabs: set[str] = set()

	for tab_name in tabs_to_visit:
		if tab_name in visited_tabs:
			continue
		visited_tabs.add(tab_name)

		if tab_name != "全場":
			clicked = False
			for selector in [
				f"button:has-text('{tab_name}')",
				f"[role='tab']:has-text('{tab_name}')",
				f"text={tab_name}",
			]:
				try:
					page.locator(selector).first.click(timeout=1500)
					page.wait_for_timeout(700)
					clicked = True
					break
				except Exception:
					continue
			if not clicked:
				continue

		raw = extract_visible_markets()
		if not heading_text:
			heading_text = raw.get("headingText", "")
		if not participants and len(raw.get("participants", [])) >= 2:
			participants = raw.get("participants", [])

		for market in raw.get("markets", []):
			market_name = market.get("market", "")
			if not market_name:
				continue
			options = market.get("options", [])
			existing = merged_markets.get(market_name)
			if not existing:
				merged_markets[market_name] = {
					"market": market_name,
					"options": list(options),
				}
				continue

			existing_keys = {
				f"{item.get('selection', '')}__{item.get('odds', '')}"
				for item in existing["options"]
			}
			for item in options:
				item_key = f"{item.get('selection', '')}__{item.get('odds', '')}"
				if item_key not in existing_keys:
					existing["options"].append(item)
					existing_keys.add(item_key)

	away_team, home_team = parse_matchup(heading_text)
	if (not home_team or not away_team) and len(participants) >= 2:
		home_team = participants[0]
		away_team = participants[1]

	return {
		"source_url": url,
		"heading": heading_text,
		"home_team": home_team,
		"away_team": away_team,
		"markets": list(merged_markets.values()),
	}


def main() -> None:
	# Resolve paths from file location so execution is stable from any cwd.
	project_root = Path(__file__).resolve().parents[2]
	data_root = project_root / "data"

	now = datetime.now()
	date_stamp = now.strftime("%Y%m%d")
	# Persist scraped betting markets under data/YYYYMMDD/Bet.
	output_dir = data_root / date_stamp / "Bet"
	output_dir.mkdir(parents=True, exist_ok=True)

	with sync_playwright() as p:
		browser = p.chromium.launch(headless=True)
		page = browser.new_page()

		page.goto(SPORT_URL, wait_until="domcontentloaded")
		page.wait_for_timeout(1500)
		scroll_for_full_listing(page)

		event_links = collect_event_links(page)
		if not event_links:
			browser.close()
			raise RuntimeError("No baseball event links found on sports lottery page.")

		saved = 0
		for event_url in event_links:
			try:
				# Parse one event page and merge full-game and first-5 markets.
				event_data = extract_event_data(page, event_url)
			except Exception as exc:
				print(f"Skip {event_url}: {exc}")
				continue

			home_team = event_data.get("home_team", "")
			away_team = event_data.get("away_team", "")
			markets = event_data.get("markets", [])

			if not home_team or not away_team:
				print(f"Skip {event_url}: missing matchup teams.")
				continue

			home_abbr = to_team_abbr(home_team)
			away_abbr = to_team_abbr(away_team)

			output_payload = {
				"scraped_at": now.isoformat(timespec="seconds"),
				"source": "Taiwan Sports Lottery",
				"source_url": event_url,
				"sport": "Baseball",
				"date": date_stamp,
				"home_team": {
					"name": home_team,
					"abbr": home_abbr,
				},
				"away_team": {
					"name": away_team,
					"abbr": away_abbr,
				},
				"markets": markets,
				"odds_available": bool(markets),
			}

			output_name = f"{home_abbr}_{away_abbr}_{date_stamp}.json"
			output_path = output_dir / output_name
			output_path.write_text(
				json.dumps(output_payload, ensure_ascii=False, indent=2),
				encoding="utf-8",
			)
			saved += 1
			print(f"Saved: {output_path}")

		browser.close()

	print(f"Done. Saved {saved} file(s) to {output_dir}")


if __name__ == "__main__":
	main()
