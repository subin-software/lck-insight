"""국제전 분석: 팀 → 리그(지역) 매핑, 리그 간 상대 전적, 대회별 결과."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.teams import team_games, team_info, team_series

# Leaguepedia 지역 표기 → 앱에서 쓰는 리그 이름
REGION_LEAGUE = {
    "Korea": "LCK", "China": "LPL", "EMEA": "LEC", "Europe": "LEC",
    "North America": "LCS", "Asia Pacific": "아시아·태평양", "LMS": "아시아·태평양", "SEA": "아시아·태평양",
    "Vietnam": "VCS", "Brazil": "남미", "Latin America": "남미", "LAN": "남미",
}
# 팀 정보에 지역이 비어 있는 팀 (직접 보완)
MANUAL_REGION = {
    "DAMWON Gaming": "Korea", "MAD Lions": "EMEA", "CLG Prime": "North America",
    "Flamengo Esports": "Brazil", "GIGABYTE Marines": "Vietnam", "SuperMassive Esports": "Turkey",
}
MAJOR = ["LCK", "LPL", "LEC", "LCS"]
LEAGUE_COLOR = {"LCK": "#C89B3C", "LPL": "#EF4444", "LEC": "#3B82F6", "LCS": "#10B981",
                "아시아·태평양": "#8B5CF6", "VCS": "#F59E0B", "남미": "#14B8A6", "기타": "#9CA3AF"}


@st.cache_data
def team_league() -> dict[str, str]:
    """국제전에 나온 팀 이름 → 리그."""
    info = team_info()
    out = {}
    for t in set(team_games()["team"]):
        region = MANUAL_REGION.get(t) or (info.at[t, "region"] if t in info.index else None)
        out[t] = REGION_LEAGUE.get(region, "기타")
    return out


@st.cache_data
def intl_games() -> pd.DataFrame:
    """국제전 세트 (팀 시점 2행) + 양 팀 리그."""
    tg = team_games()
    tg = tg[tg["scope"] == "INTL"].copy()
    lg = team_league()
    tg["league"] = tg["team"].map(lg)
    tg["opp_league"] = tg["opponent"].map(lg)
    return tg


@st.cache_data
def intl_series() -> pd.DataFrame:
    s = team_series()
    s = s[s["scope"] == "INTL"].copy()
    lg = team_league()
    s["league"] = s["team"].map(lg)
    s["opp_league"] = s["opponent"].map(lg)
    return s


@st.cache_data
def tournament_results() -> pd.DataFrame:
    """대회(연도 × 대회)별 우승·준우승 팀과 LCK 최고 성적."""
    s = intl_series().sort_values("datetime_kst")
    rows = []
    for (year, tour), g in s.groupby(["year", "league_short"]):
        final = g[g["match_id"] == g.iloc[-1]["match_id"]]
        winner = final[final["win"]].iloc[0]
        lck = g[g["league"] == "LCK"]
        if lck.empty:
            lck_best = "출전 안 함"
        elif "LCK" in (winner["league"], winner["opp_league"]):
            lck_best = "우승" if winner["league"] == "LCK" else "준우승"
        else:
            last = lck.sort_values("datetime_kst").iloc[-1]
            lck_best = f"{last['tab']}"
        rows.append({"연도": int(year), "대회": tour, "우승": winner["team"], "우승 리그": winner["league"],
                     "준우승": winner["opponent"], "준우승 리그": winner["opp_league"],
                     "결승 스코어": f"{int(winner['score'])}:{int(winner['opp_score'])}",
                     "LCK 최고 성적": lck_best, "_start": g["datetime_kst"].min()})
    return pd.DataFrame(rows)


def league_matrix(games: pd.DataFrame, leagues: list[str]) -> pd.DataFrame:
    """행 리그가 열 리그를 상대로 거둔 세트 승률 (같은 리그끼리는 제외)."""
    g = games[games["league"].isin(leagues) & games["opp_league"].isin(leagues)
              & (games["league"] != games["opp_league"])]
    return g.pivot_table(index="league", columns="opp_league", values="win", aggfunc="mean") \
        .reindex(index=leagues, columns=leagues)


def league_counts(games: pd.DataFrame, leagues: list[str]) -> pd.DataFrame:
    g = games[games["league"].isin(leagues) & games["opp_league"].isin(leagues)
              & (games["league"] != games["opp_league"])]
    return g.pivot_table(index="league", columns="opp_league", values="win", aggfunc="size") \
        .reindex(index=leagues, columns=leagues)
