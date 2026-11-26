"""대회 단위 정보: 대회 묶기(플레이인+본선 / 정규+플레이오프), 공식 순위, 결승, MVP."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.data_loader import load_csv, load_schedule, load_tournaments

INTL_ORDER = ["Worlds", "MSI", "First Stand", "EWC"]


@st.cache_data
def events() -> pd.DataFrame:
    """앱에서 보여 줄 '대회' 목록.

    - 국제전: 같은 해 같은 대회의 플레이인·본선 페이지를 하나로 (예: 2026 Worlds)
    - LCK: 같은 해 같은 스플릿의 정규 시즌·플레이오프를 하나로 (예: 2026 LCK Spring)
    """
    t = load_tournaments()
    t = t[t["scope"].isin(["LCK", "INTL"])].dropna(subset=["year"]).copy()
    t["split"] = t["split"].fillna("")
    t["event_key"] = t.apply(lambda r: f"{int(r['year'])}|{r['league_short']}|"
                                       f"{r['split'] if r['scope'] == 'LCK' else ''}", axis=1)
    rows = []
    for key, g in t.groupby("event_key"):
        year, league, split = key.split("|")
        name = f"{year} {league}" + (f" {split}" if split else "")
        rows.append({"event_key": key, "name": name, "year": int(year), "league": league, "split": split,
                     "scope": g["scope"].iloc[0], "pages": list(g.sort_values("date_start")["page"]),
                     "start": g["date_start"].min(), "end": pd.to_datetime(g["date_end"], errors="coerce").max()})
    return pd.DataFrame(rows).sort_values("start", ascending=False)


@st.cache_data
def official_results(pages: tuple[str, ...]) -> pd.DataFrame:
    """Leaguepedia 공식 최종 순위·상금. 상위 페이지에 기록된 경우도 찾고, 순위가 가장 많이 기록된 페이지를 쓴다."""
    r = load_csv("tournament_results")
    if r.empty:
        return r
    candidates = set()
    for p in pages:
        parts = p.split("/")
        candidates.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    r = r[r["page"].isin(candidates)].copy()
    if r.empty:
        return r
    # 플레이오프 페이지와 정규 시즌 페이지가 둘 다 있으면 플레이오프(최종) 결과를 우선
    best = sorted(r["page"].unique(), key=lambda p: ("playoff" not in p.lower(), -len(r[r["page"] == p])))[0]
    r = r[r["page"] == best].copy()
    r["place_number"] = pd.to_numeric(r["place_number"], errors="coerce")
    r["prize"] = pd.to_numeric(r["prize"], errors="coerce")
    return r.sort_values(["place_number", "team"])


def event_schedule(pages) -> pd.DataFrame:
    s = load_schedule()
    return s[s["page"].isin(list(pages))].sort_values("datetime_kst")
