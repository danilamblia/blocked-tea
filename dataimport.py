#!/usr/bin/env python3
"""Базовый сборщик матчей одного турнира."""
import sys, csv, re, requests
from datetime import datetime

BASE = "https://api.unitedleagues.gg/"
SPORT = "efootball"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://efootball.unitedleagues.gg",
    "Referer": "https://efootball.unitedleagues.gg/",
    "Content-Type": "application/json",
}

def fetch(tour_id):
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(f"https://efootball.unitedleagues.gg/tour/{tour_id}")
    tv = s.post(f"{BASE}api/{SPORT}/load/tour/{tour_id}").json()
    td = s.post(f"{BASE}api/{SPORT}/load/tour/data/{tv['id_sl']}").json()
    return tv, td

def parse_ht(periods):
    m = re.search(r"\((\d+)\s*-\s*(\d+)\)", periods or "")
    return (m.group(1), m.group(2)) if m else ("", "")

def to_iso(d):
    try:
        return datetime.strptime(d, "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception:
        return d or ""

def main():
    tour_id = sys.argv[1] if len(sys.argv) > 1 else "8301"
    tv, td = fetch(tour_id)
    games = td["tour_blocks"]["games"]

    header = ["date","time","player1","team1","player2","team2",
              "goals_team1_ht","goals_team2_ht","goals_team1_ft","goals_team2_ft"]
    rows = []
    for g in games:
        if g.get("state") != "finished":
            continue
        ht1, ht2 = parse_ht(g.get("periods"))
        rows.append([to_iso(g.get("game_date")), g.get("game_time"),
                     g.get("player_1_title_en"), g.get("team_1_title_en"),
                     g.get("player_2_title_en"), g.get("team_2_title_en"),
                     ht1, ht2, g.get("score_team1"), g.get("score_team2")])

    with open(f"matches_{tour_id}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"OK: {len(rows)} матчей → matches_{tour_id}.csv")

if __name__ == "__main__":
    main()
