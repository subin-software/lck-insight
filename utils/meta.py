"""챔피언 메타 집계: 픽률·밴률·승률, 패치별 추이, 팀별 선호 챔피언."""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from utils.champions import explode_champions
from utils.data_loader import load_players
from utils.teams import team_games


def patch_key(patch: str) -> tuple:
    """'26.10' → (26, 10). 정렬용."""
    nums = re.findall(r"\d+", str(patch))
    return tuple(int(n) for n in nums) if nums else (0,)


@st.cache_data
def champion_roles() -> pd.Series:
    """챔피언 → 프로 경기에서 가장 많이 쓰인 포지션 (게임 ID 기준)."""
    p = load_players()
    return p.groupby("champion")["role"].agg(lambda s: s.mode().iat[0])


def filtered_games(scopes: list[str], year: int, patches: list[str] | None) -> pd.DataFrame:
    """팀 시점(경기당 2행) 경기 데이터를 조건으로 거른다."""
    tg = team_games()
    tg = tg[tg["scope"].isin(scopes) & (tg["year"] == year)]
    if patches:
        tg = tg[tg["patch"].isin(patches)]
    return tg


def champion_table(tg: pd.DataFrame) -> pd.DataFrame:
    """챔피언별 픽·밴 수, 픽률·밴률·밴픽률(등장률), 승률."""
    n_games = tg["game_id"].nunique()
    if n_games == 0:
        return pd.DataFrame()
    picks = explode_champions(tg, "picks").groupby("champion").agg(픽=("game_id", "size"), 승=("win", "sum"))
    bans = explode_champions(tg, "bans").groupby("champion").size().rename("밴")
    t = picks.join(bans, how="outer").fillna(0)
    t["픽률"] = t["픽"] / n_games
    t["밴률"] = t["밴"] / n_games
    t["등장률"] = (t["픽"] + t["밴"]) / n_games
    t["승률"] = t["승"] / t["픽"].where(t["픽"] > 0)
    t["포지션"] = t.index.map(champion_roles())
    return t.sort_values("등장률", ascending=False)


def patch_trend(tg: pd.DataFrame, champions: list[str]) -> pd.DataFrame:
    """패치별 선택 챔피언의 등장률·승률."""
    rows = []
    for patch, g in tg.groupby("patch"):
        t = champion_table(g)
        n = g["game_id"].nunique()
        for c in champions:
            r = t.loc[c] if c in t.index else None
            rows.append({"패치": patch, "champion": c, "경기 수": n,
                         "등장률": r["등장률"] if r is not None else 0.0,
                         "승률": r["승률"] if r is not None else None})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    order = sorted(out["패치"].unique(), key=patch_key)
    out["패치"] = pd.Categorical(out["패치"], categories=order, ordered=True)
    return out.sort_values("패치")


def team_champion_matrix(tg: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """팀 × 챔피언 픽 횟수 (가장 많이 쓰인 챔피언 top 개)."""
    ex = explode_champions(tg, "picks")
    top_champs = ex["champion"].value_counts().head(top).index
    m = ex[ex["champion"].isin(top_champs)].pivot_table(index="team", columns="champion", values="game_id",
                                                         aggfunc="size", fill_value=0)
    return m[top_champs]
