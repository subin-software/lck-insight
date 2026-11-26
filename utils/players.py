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
    p["gpm"] = p["gold"] / p["gamelength"]
    p["vspm"] = p["vision"] / p["gamelength"]
    p["dmg_per_gold"] = p["damage"] / p["gold"].replace(0, np.nan)       # 골드 1당 딜량 (딜 효율)
    p["assist_share"] = p["assists"] / p["team_kills"].replace(0, np.nan)  # 팀 킬 중 어시스트 관여
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
        "gpm": df["gpm"].mean() if "gpm" in df else np.nan,
        "vspm": df["vspm"].mean() if "vspm" in df else np.nan,
        "dmg_per_gold": df["dmg_per_gold"].mean() if "dmg_per_gold" in df else np.nan,
        "assist_share": df["assist_share"].mean() if "assist_share" in df else np.nan,
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


# ================================================================== 포지션별 지표
# 형식: (지표 키, 이름, 표시 형식, 높을수록 좋은지, 설명)
COMMON_METRICS = [
    ("win_rate", "승률", "{:.0%}", True, "이긴 경기 비율"),
    ("kda", "KDA", "{:.2f}", True, "(킬 + 어시스트) ÷ 데스"),
    ("kp", "킬 관여율", "{:.0%}", True, "팀 킬 중 내가 킬·어시스트로 관여한 비율"),
]
# Oracle's Elixir 데이터가 있어야 계산되는 지표 (data/oe_season.csv)
OE_METRICS = {
    "gd15": ("15분 골드 격차", "{:+.0f}", True, "15분 시점 맞라인 상대와의 골드 차이"),
    "csd15": ("15분 CS 격차", "{:+.1f}", True, "15분 시점 맞라인 상대와의 CS 차이"),
    "xpd15": ("15분 경험치 격차", "{:+.0f}", True, "15분 시점 맞라인 상대와의 경험치 차이"),
    "early_kp": ("15분 킬 관여율", "{:.0%}", True, "15분까지 팀 킬 중 관여 비율 (초반 갱킹·로밍·합류)"),
    "first_obj": ("첫 오브젝트 확보율", "{:.0%}", True, "팀이 첫 용·첫 전령을 가져간 비율"),
    "wpm": ("분당 와드 설치", "{:.2f}", True, "1분마다 설치한 와드 수"),
    "wcpm": ("분당 와드 제거", "{:.2f}", True, "1분마다 제거한 상대 와드 수"),
}
ROLE_METRICS = {
    "Top": {
        "desc": "사이드 운영과 한타 진입을 함께 맡아, 라인전 체급과 후반 한타 기여도를 함께 봅니다.",
        "metrics": [("gd15",), ("csd15",), ("xpd15",),
                    ("dpm", "분당 딜량 (DPM)", "{:.0f}", True, "1분마다 챔피언에게 준 피해량 (2020년~)"),
                    ("dmg_share", "팀 내 딜 비중", "{:.0%}", True, "팀 전체 딜량 중 내 비중 (2020년~)"),
                    ("kill_share", "팀 킬 비중", "{:.0%}", True, "팀 킬 중 내가 마무리한 비율 (솔로 킬 대신 참고)"),
                    ("deaths_pg", "경기당 데스", "{:.2f}", False, "적을수록 좋음")],
    },
    "Jungle": {
        "desc": "맵 전체를 움직여 주도권을 만드는 포지션이라, 초반 관여와 오브젝트, 동선 효율, 시야를 봅니다.",
        "metrics": [("early_kp",), ("first_obj",), ("xpd15",),
                    ("cs_min", "분당 CS", "{:.1f}", True, "정글 몬스터 포함 — 동선 효율"),
                    ("vspm", "분당 시야 점수", "{:.2f}", True, "시야 제어 (2019년~)"),
                    ("wcpm",),
                    ("assists_pg", "경기당 어시스트", "{:.1f}", True, "교전 연계")],
    },
    "Mid": {
        "desc": "사이드·정글 교전에 개입하기 쉬운 위치라, 라인 주도권과 합류, 성장, 딜을 함께 봅니다.",
        "metrics": [("gd15",), ("csd15",), ("early_kp",),
                    ("dpm", "분당 딜량 (DPM)", "{:.0f}", True, "1분마다 챔피언에게 준 피해량 (2020년~)"),
                    ("dmg_share", "팀 내 딜 비중", "{:.0%}", True, "팀 전체 딜량 중 내 비중 (2020년~)"),
                    ("cs_min", "분당 CS", "{:.1f}", True, "라인 관리"),
                    ("gold_share", "팀 골드 비중", "{:.0%}", True, "팀 자원 중 내 몫")],
    },
    "Bot": {
        "desc": "꾸준한 성장과 한타 지속 딜링이 핵심이라, 성장 속도와 딜, 딜 효율, 데스 관리를 봅니다.",
        "metrics": [("cs_min", "분당 CS (CS/M)", "{:.1f}", True, "성장 속도"),
                    ("dpm", "분당 딜량 (DPM)", "{:.0f}", True, "1분마다 챔피언에게 준 피해량 (2020년~)"),
                    ("dmg_per_gold", "골드 대비 딜 효율", "{:.2f}", True, "골드 1당 챔피언에게 준 피해량 (2020년~)"),
                    ("dmg_share", "팀 내 딜 비중", "{:.0%}", True, "팀 전체 딜량 중 내 비중 (2020년~)"),
                    ("deaths_pg", "경기당 데스", "{:.2f}", False, "데스 관리 — 적을수록 좋음"),
                    ("csd15",)],
    },
    "Support": {
        "desc": "어시스트 관여와 시야, 유틸·딜 기여를 봅니다. 다만 이기는 팀은 와드가 오래 살아남고 지는 팀은 "
                "급하게 와드를 박아 시야 점수가 높게 잡히기도 해서, 수치만으로는 한계가 있습니다.",
        "metrics": [("assist_share", "어시스트 관여율", "{:.0%}", True, "팀 킬 중 어시스트로 관여한 비율"),
                    ("vspm", "분당 시야 점수", "{:.2f}", True, "시야 제어 (2019년~)"),
                    ("wpm",), ("wcpm",),
                    ("dmg_share", "팀 내 딜 비중", "{:.0%}", True, "딜 기여 (2020년~)"),
                    ("deaths_pg", "경기당 데스", "{:.2f}", False, "적을수록 좋음")],
    },
}
UNAVAILABLE = {
    "Top": "솔로 킬/데스",
    "Mid": "로밍 횟수",
    "Support": "CC(군중 제어) 시간",
}


def metric_defs(role: str) -> list[tuple]:
    """포지션의 지표 목록 [(키, 이름, 형식, 높을수록 좋은지, 설명, 출처)] — 공통 지표 포함."""
    out = [(*m, "base") for m in COMMON_METRICS]
    for m in ROLE_METRICS[role]["metrics"]:
        if len(m) == 1:
            out.append((m[0], *OE_METRICS[m[0]], "oe"))
        else:
            out.append((*m, "base"))
    return out


@st.cache_data
def oe_season() -> pd.DataFrame:
    """Oracle's Elixir 선수-시즌 지표 (없으면 빈 표)."""
    from utils.data_loader import load_csv
    return load_csv("oe_season")


@st.cache_data
def position_table() -> pd.DataFrame:
    """LCK 선수-시즌 지표 + (있으면) Oracle's Elixir 15분 지표."""
    t = season_table().copy()
    oe = oe_season()
    if not oe.empty:
        t = t.merge(oe, on=["player", "year", "role"], how="left")
    for key in OE_METRICS:
        if key not in t:
            t[key] = np.nan
    return t


def position_percentiles(player: str, year: int, role: str) -> pd.DataFrame:
    """그 시즌 같은 포지션 LCK 선수들 사이에서의 백분위 (높을수록 좋게 맞춤)."""
    t = position_table()
    pool = t[(t["role"] == role) & (t["year"] == year)]
    me = pool[pool["player"] == player]
    rows = []
    for key, label, fmt, higher, desc, source in metric_defs(role):
        v = me[key].iloc[0] if not me.empty else np.nan
        col = pool[key].dropna()
        if pd.isna(v) or col.empty:
            pct, avg = np.nan, (col.mean() if not col.empty else np.nan)
        else:
            pct = ((col < v).mean() if higher else (col > v).mean()) * 100
            avg = col.mean()
        rows.append({"key": key, "지표": label, "값": v, "포지션 평균": avg, "백분위": pct, "형식": fmt,
                     "설명": desc, "출처": source, "공통": key in {m[0] for m in COMMON_METRICS}})
    return pd.DataFrame(rows)
