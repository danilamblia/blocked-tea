#!/usr/bin/env python3
"""
Собирает матчи из нескольких турниров unitedleagues.gg в один CSV.

Использование:
    python multi_tours.py 8430 8431 8432
    python multi_tours.py --ids 8430 8431 --output all.csv
    python multi_tours.py --file tour_ids.txt
    python multi_tours.py 8430 --all-states        # включая незавершённые
"""

import argparse
import csv
import re
import sys
import time
import requests
from datetime import datetime


# ========== КОНФИГ ==========

BASE = "https://api.unitedleagues.gg/"
SPORT = "efootball"
SITE = "https://efootball.unitedleagues.gg"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": SITE,
    "Referer": SITE + "/",
    "Content-Type": "application/json",
}

DEFAULT_DELAY = 0.4   # пауза между турнирами (сек)


# ========== УТИЛИТЫ ==========

_PERIODS_RE = re.compile(r"\(?\s*(\d+)\s*[-:]\s*(\d+)\s*\)?")
_STREAM_RE = re.compile(r"stream\s*(\d+)", re.IGNORECASE)


def split_periods(periods):
    """
    '(2-1)' -> (2, 1)
    Возвращает (None, None), если формат не распознан.
    """
    if not periods:
        return None, None
    m = _PERIODS_RE.search(periods)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def to_iso(date_str):
    """'03.10.2026' -> '2026-10-03'. При ошибке возвращает как есть."""
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception:
        return date_str or ""


def stream_number(tour_val):
    """Номер стрима из названия турнира (1, 2, ...). None если нет."""
    title = (tour_val.get("title_en") or "") + " " + (tour_val.get("title_ru") or "")
    m = _STREAM_RE.search(title)
    return int(m.group(1)) if m else None


# ========== API ==========

def make_session():
    """Сессия с прогретыми cookies."""
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get(SITE + "/", timeout=10)
    except Exception:
        pass
    return s


def fetch_tour(session, tour_id, timeout=20):
    """
    Возвращает (tour_val, tour_data) или (None, None).
    tour_val — мета турнира, tour_data — блоки (games, games_group, ...).
    """
    try:
        r1 = session.post(f"{BASE}api/{SPORT}/load/tour/{tour_id}", timeout=timeout)
        if r1.status_code != 200:
            print(f"[!] {tour_id}: HTTP {r1.status_code} на load/tour")
            return None, None

        tour_val = r1.json()
        if not tour_val or "id_sl" not in tour_val:
            print(f"[!] {tour_id}: пустой ответ или нет id_sl")
            return None, None

        r2 = session.post(f"{BASE}api/{SPORT}/load/tour/data/{tour_val['id_sl']}",
                          timeout=timeout)
        if r2.status_code != 200:
            print(f"[!] {tour_id}: HTTP {r2.status_code} на load/tour/data")
            return tour_val, None

        return tour_val, r2.json()

    except requests.RequestException as e:
        print(f"[!] {tour_id}: сеть — {e}")
        return None, None
    except ValueError as e:
        print(f"[!] {tour_id}: JSON — {e}")
        return None, None


# ========== СБОР ==========

def extract_matches(tour_id, tour_val, tour_data, only_finished=True):
    """Возвращает список dict'ов — матчи одного турнира."""
    blocks = tour_data.get("tour_blocks", {})
    games = blocks.get("games", [])

    rows = []
    for g in games:
        if only_finished and g.get("state") != "finished":
            continue

        ht1, ht2 = split_periods(g.get("periods"))

        rows.append({
            "tour_id": tour_id,
            "tour_title": tour_val.get("title_en") or "",
            "tour_date": tour_val.get("date") or "",
            "stream": stream_number(tour_val) or "",
            "date": to_iso(g.get("game_date")),
            "time": g.get("game_time") or "",
            "player1": g.get("player_1_title_en") or "",
            "team1": g.get("team_1_title_en") or "",
            "player2": g.get("player_2_title_en") or "",
            "team2": g.get("team_2_title_en") or "",
            "goals_team1_ht": ht1 if ht1 is not None else "",
            "goals_team2_ht": ht2 if ht2 is not None else "",
            "goals_team1_ft": g.get("score_team1") or "",
            "goals_team2_ft": g.get("score_team2") or "",
            "state": g.get("state") or "",
        })
    return rows


def collect(session, tour_ids, only_finished=True, delay=DEFAULT_DELAY):
    """Собирает матчи из списка турниров."""
    all_rows = []
    stats = {"ok": 0, "fail": 0, "no_games": 0, "empty": 0}

    for i, tid in enumerate(tour_ids, 1):
        print(f"\n[{i}/{len(tour_ids)}] Турнир {tid} ...")
        tour_val, tour_data = fetch_tour(session, tid)

        if tour_val is None:
            stats["fail"] += 1
            continue
        if tour_data is None:
            stats["no_games"] += 1
            continue

        matches = extract_matches(tid, tour_val, tour_data,
                                  only_finished=only_finished)

        title = tour_val.get("title_en", "?")
        total = len(tour_data.get("tour_blocks", {}).get("games", []))
        print(f"    {title} | {tour_val.get('date')} "
              f"| матчей: {len(matches)} завершённых из {total}")

        if not matches:
            stats["empty"] += 1

        all_rows.extend(matches)
        stats["ok"] += 1

        if i < len(tour_ids):
            time.sleep(delay)

    return all_rows, stats


# ========== ЭКСПОРТ ==========

CSV_HEADER = [
    "tour_id", "tour_title", "tour_date", "stream",
    "date", "time",
    "player1", "team1", "player2", "team2",
    "goals_team1_ht", "goals_team2_ht",
    "goals_team1_ft", "goals_team2_ft",
    "state",
]


def save_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(rows)
    print(f"\n[OK] {len(rows)} матчей → {path}")


def save_xlsx(rows, path):
    """Опционально: сохранить в Excel, если установлен pandas."""
    try:
        import pandas as pd
    except ImportError:
        print("[!] pandas не установлен — пропускаю XLSX")
        return
    pd.DataFrame(rows, columns=CSV_HEADER).to_excel(path, index=False)
    print(f"[OK] {len(rows)} матчей → {path}")


# ========== АРГУМЕНТЫ ==========

def parse_args():
    p = argparse.ArgumentParser(
        description="Собирает матчи из нескольких турниров unitedleagues.gg в один CSV."
    )
    p.add_argument("tour_ids", nargs="*",
                   help="ID турниров (можно несколько)")
    p.add_argument("--ids", nargs="+",
                   help="Альтернативный способ задать ID")
    p.add_argument("--file",
                   help="Файл со списком ID (по одному в строке)")
    p.add_argument("-o", "--output", default="all_matches.csv",
                   help="Имя выходного CSV (по умолчанию all_matches.csv)")
    p.add_argument("--xlsx", action="store_true",
                   help="Дополнительно сохранить в XLSX (нужен pandas)")
    p.add_argument("--all-states", action="store_true",
                   help="Включать незавершённые матчи (по умолчанию только finished)")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                   help=f"Пауза между турнирами, сек (по умолчанию {DEFAULT_DELAY})")
    return p.parse_args()


def read_ids_from_file(path):
    ids = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                ids.append(line)
    return ids


# ========== MAIN ==========

def main():
    args = parse_args()

    # Собираем список ID из разных источников
    tour_ids = []
    tour_ids.extend(args.tour_ids)
    if args.ids:
        tour_ids.extend(args.ids)
    if args.file:
        tour_ids.extend(read_ids_from_file(args.file))

    # Убираем дубликаты, сохраняя порядок
    seen = set()
    tour_ids = [t for t in tour_ids if not (t in seen or seen.add(t))]

    if not tour_ids:
        print("[!] Не передано ни одного tour_id.")
        print("    Пример: python multi_tours.py 8430 8431 8432")
        sys.exit(1)

    print(f"[*] Турниров к сбору: {len(tour_ids)}")
    print(f"[*] Только завершённые: {not args.all_states}")
    print(f"[*] Пауза между запросами: {args.delay} сек")

    session = make_session()
    rows, stats = collect(
        session,
        tour_ids,
        only_finished=not args.all_states,
        delay=args.delay,
    )

    if not rows:
        print("\n[!] Не собрано ни одного матча.")
        sys.exit(1)

    save_csv(rows, args.output)
    if args.xlsx:
        save_xlsx(rows, args.output.rsplit(".", 1)[0] + ".xlsx")

    # Итоговая статистика
    print("\n=== Статистика ===")
    print(f"  турниров OK:        {stats['ok']}")
    print(f"  турниров пусто:     {stats['empty']}")
    print(f"  ошибок сети/JSON:   {stats['fail']}")
    print(f"  без данных (500?):  {stats['no_games']}")
    print(f"  матчей всего:       {len(rows)}")


if __name__ == "__main__":
    main()

