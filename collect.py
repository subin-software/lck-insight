"""Leaguepedia 데이터 수집 스크립트.

- 로컬에서 직접 실행하거나, GitHub Actions가 매일 한 번 실행한다.
- 앱(Streamlit)은 이 스크립트가 만든 data/*.csv 만 읽는다.
  (Leaguepedia는 요청 제한이 엄격해서 앱이 직접 API를 부르지 않는다.)

실행: python collect.py
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

API_URL = "https://lol.fandom.com/api.php"
HEADERS = {"User-Agent": "LCK-Insight student project (Streamlit app)"}
DATA_DIR = Path(__file__).resolve().parent / "data"
KST = timezone(timedelta(hours=9))

# 수집 범위
LCK_LEAGUE = "LoL Champions Korea"
INTERNATIONAL_LEAGUES = [
    "World Championship",
    "Mid-Season Invitational",
    "First Stand",
    "Esports World Cup",
]

REQUEST_INTERVAL = 3  # 요청 사이 대기 시간(초)
PAGE_SIZE = 500       # cargoquery 1회 최대 행 수


def cargo_query(tables: str, fields: str, where: str = "", join_on: str = "",
                order_by: str = "", max_retries: int = 5) -> list[dict]:
    """Leaguepedia Cargo API를 페이지 단위로 끝까지 조회한다.

    요청 제한(ratelimited)에 걸리면 대기 시간을 늘려 가며 다시 시도한다.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        params = {
            "action": "cargoquery", "format": "json",
            "tables": tables, "fields": fields, "where": where,
            "join_on": join_on, "order_by": order_by,
            "limit": PAGE_SIZE, "offset": offset,
        }
        for attempt in range(max_retries):
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("error", {}).get("code") == "ratelimited":
                time.sleep(30 * (attempt + 1))
                continue
            if "error" in data:
                raise RuntimeError(data["error"])
            break
        else:
            raise RuntimeError("요청 제한이 계속되어 수집을 중단합니다.")

        batch = [item["title"] for item in data.get("cargoquery", [])]
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE
        time.sleep(REQUEST_INTERVAL)


def append_update_log(new_games: int, note: str) -> None:
    """data/update_log.csv 에 이번 실행 결과를 한 줄 추가한다."""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "update_log.csv"
    row = pd.DataFrame([{
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "new_games": new_games,
        "note": note,
    }])
    if path.exists():
        row = pd.concat([pd.read_csv(path), row], ignore_index=True)
    row.to_csv(path, index=False, encoding="utf-8-sig")


def main() -> None:
    # TODO: 경기(ScoreboardGames), 선수 기록(ScoreboardPlayers), 일정(MatchSchedule),
    #       로스터(TournamentPlayers), 팀 정보(Teams) 증분 수집 구현
    append_update_log(new_games=0, note="수집 기능 준비 중")


if __name__ == "__main__":
    main()
