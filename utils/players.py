"""선수 지표 계산과 플레이 유형 군집 분석(KMeans)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from utils.data_loader import load_games, load_players

MIN_GAMES = 10   # 군집·비교 대상이 되려면 한 시즌 최소 경기 수
N_CLUSTERS = 4

# 2016년부터 모든 시즌에 있는 지표만 군집에 사용한다 (딜량은 2020년, 시야는 2019년부터 기록됨)
STYLE_FEATURES = {
    "kp": "킬 관여율",
    "kill_share": "팀 킬 비중",
    "gold_share": "팀 골드 비중",
    "cs_min": "분당 CS",
    "deaths_pg": "경기당 데스",
    "assists_pg": "경기당 어시스트",
}
# 레이더 비교용 (딜량 비중은 둘 다 기록이 있을 때만 표시)
RADAR_FEATURES = {
    "kda": "KDA", "kp": "킬 관여율", "gold_share": "골드 비중", "cs_min": "분당 CS",
    "survival": "생존력", "win_rate": "승률", "dmg_share": "딜량 비중",
}
ARCHETYPES = {
    # 이름: (설명, {지표: 방향}) → 군집 중심 z-점수의 (방향 × 값) 평균이 그 유형과 닮은 정도
    "캐리형": ("킬과 골드를 많이 가져가는 팀의 주 공격수", {"kill_share": 1, "gold_share": 1}),
    "팀플레이형": ("킬 관여와 어시스트가 많아 팀 싸움 연계에 강함", {"kp": 1, "assists_pg": 1}),
    "안정형": ("데스가 적고 무리하지 않는 운영", {"deaths_pg": -1}),
    "공격형": ("킬 비중이 높지만 데스도 많은 과감한 스타일", {"kill_share": 1, "deaths_pg": 1}),
    "조력형": ("킬과 골드를 팀원에게 양보하고 받쳐 주는 비중이 큰 시즌", {"kill_share": -1, "gold_share": -1}),
}


def name_clusters(centers: pd.DataFrame) -> dict[int, str]:
    """군집 4개와 유형 5개 사이의 '닮은 정도' 합이 최대가 되도록 1:1로 이름을 붙인다 (헝가리안 알고리즘)."""
    score = np.array([[np.mean([w * centers.loc[c, f] for f, w in rule.items()])
                       for _, rule in ARCHETYPES.values()] for c in centers.index])
    rows, cols = linear_sum_assignment(-score)
    names = list(ARCHETYPES)
    return {int(r): names[c] for r, c in zip(rows, cols)}


@st.cache_data
def player_games(include_foreign: bool = True) -> pd.DataFrame:
    """선수 경기 기록 + 경기 시간 + 파생 지표(킬 관여율, 비중, 분당 지표)."""
    p = load_players(include_foreign=include_foreign).copy()
    g = load_games()[["game_id", "gamelength"]]
    p = p.merge(g, on="game_id", how="left")          # 해외 리그 기록은 경기 시간이 없다
    p["scope"] = p["scope"].fillna("FOREIGN")
    team_dmg = p.groupby(["game_id", "team"])["damage"].transform(lambda s: s.sum(min_count=5))
    p["kp"] = (p["kills"] + p["assists"]) / p["team_kills"].replace(0, np.nan)
    p["kill_share"] = p["kills"] / p["team_kills"].replace(0, np.nan)
    p["gold_share"] = p["gold"] / p["team_gold"].replace(0, np.nan)
    p["dmg_share"] = p["damage"] / team_dmg.replace(0, np.nan)
    p["cs_min"] = p["cs"] / p["gamelength"]
    p["dpm"] = p["damage"] / p["gamelength"]
    return p


def summarize(df: pd.DataFrame) -> dict:
    """여러 경기 기록 → 요약 지표 (KDA는 합계로 계산)."""
    k, d, a = df["kills"].sum(), df["deaths"].sum(), df["assists"].sum()
    n = len(df)
    return {
        "games": n, "wins": int(df["win"].sum()), "win_rate": df["win"].mean() if n else np.nan,
        "kda": (k + a) / max(d, 1), "kills_pg": k / n if n else np.nan,
        "deaths_pg": d / n if n else np.nan, "assists_pg": a / n if n else np.nan,
        "kp": df["kp"].mean(), "kill_share": df["kill_share"].mean(),
        "gold_share": df["gold_share"].mean(), "dmg_share": df["dmg_share"].mean(),
        "cs_min": df["cs_min"].mean(), "dpm": df["dpm"].mean(),
    }


@st.cache_data
def season_table() -> pd.DataFrame:
    """LCK 선수-시즌 단위 지표 (군집·비교의 기본 단위)."""
    p = player_games(include_foreign=False)
    p = p[p["scope"] == "LCK"]
    rows = []
    for (player, year, role), df in p.groupby(["player", "year", "role"]):
        if len(df) < MIN_GAMES:
            continue
        row = summarize(df)
        row.update(player=player, year=int(year), role=role, team=df["team"].mode().iat[0])
        rows.append(row)
    t = pd.DataFrame(rows)
    t["survival"] = -t["deaths_pg"]
    return t


@st.cache_data
def style_clusters() -> tuple[pd.DataFrame, pd.DataFrame]:
    """포지션별로 선수-시즌을 KMeans로 4개 유형으로 나누고, 군집 중심 특징으로 이름을 붙인다.

    반환: (선수-시즌 표 + 유형·PCA 좌표, 유형별 평균 z-점수 표)
    """
    seasons = season_table().dropna(subset=list(STYLE_FEATURES)).copy()
    out, profiles = [], []
    for role, df in seasons.groupby("role"):
        x = StandardScaler().fit_transform(df[list(STYLE_FEATURES)])
        km = KMeans(n_clusters=N_CLUSTERS, n_init=20, random_state=42).fit(x)
        centers = pd.DataFrame(km.cluster_centers_, columns=list(STYLE_FEATURES))
        names = name_clusters(centers)
        df = df.assign(style=[names[c] for c in km.labels_])
        xy = PCA(n_components=2, random_state=42).fit_transform(x)
        df["pc1"], df["pc2"] = xy[:, 0], xy[:, 1]
        df[[f"z_{f}" for f in STYLE_FEATURES]] = x
        out.append(df)
        prof = centers.assign(role=role, style=[names[c] for c in range(N_CLUSTERS)])
        profiles.append(prof)
    return pd.concat(out, ignore_index=True), pd.concat(profiles, ignore_index=True)


def similar_players(player: str, year: int, role: str, n: int = 5) -> pd.DataFrame:
    """같은 포지션 선수-시즌 중 플레이 지표가 가장 비슷한 n개 (표준화 거리 기준, 본인 제외)."""
    clusters, _ = style_clusters()
    pool = clusters[clusters["role"] == role]
    me = pool[(pool["player"] == player) & (pool["year"] == year)]
    if me.empty:
        return pd.DataFrame()
    zcols = [f"z_{f}" for f in STYLE_FEATURES]
    dist = np.linalg.norm(pool[zcols].values - me[zcols].values[0], axis=1)
    pool = pool.assign(distance=dist)
    pool = pool[pool["player"] != player].sort_values("distance")
    return pool.drop_duplicates("player").head(n)


def percentiles(values: dict, role: str) -> dict:
    """선수 지표를 같은 포지션 LCK 선수-시즌 분포에서의 백분위(0~100)로 바꾼다."""
    pool = season_table()
    pool = pool[pool["role"] == role]
    out = {}
    for key in RADAR_FEATURES:
        v, col = values.get(key), pool[key].dropna()
        out[key] = np.nan if v is None or pd.isna(v) or col.empty else (col < v).mean() * 100
    return out
