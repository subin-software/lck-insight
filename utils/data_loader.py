"""data/ 폴더의 CSV를 읽고 분석하기 좋은 형태로 다듬는 함수 모음.

모든 로딩은 st.cache_data 로 캐시해서 앱이 켜진 동안 한 번만 읽는다.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KST_OFFSET = pd.Timedelta(hours=9)


@st.cache_data
def load_csv(name: str) -> pd.DataFrame:
    """data/<name>.csv 를 읽는다. 파일이 없으면 빈 DataFrame을 돌려준다."""
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    # 패치 번호는 문자열로 읽는다 (숫자로 읽으면 '26.10'이 26.1이 되어 '26.1'과 섞인다)
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False, dtype={"patch": str})


def has_data() -> bool:
    return (DATA_DIR / "games.csv").exists()


def _to_kst(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce") + KST_OFFSET


def load_update_log() -> pd.DataFrame:
    return load_csv("update_log")


@st.cache_data
def load_tournaments() -> pd.DataFrame:
    df = load_csv("tournaments").copy()
    if df.empty:
        return df
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["date_start"] = pd.to_datetime(df["date_start"], errors="coerce")
    df["split"] = df["split"].fillna("")
    df["stage"] = df["page"].map(_stage_of)
    return df


def _stage_of(page: str) -> str:
    """대회 페이지 이름으로 정규 시즌 / 플레이오프 등을 구분한다."""
    p = page.lower()
    if "playoff" in p or "finals" in p:
        return "playoffs"
    if "play-in" in p:
        return "play-in"
    if "road to msi" in p:
        return "road-to-msi"
    return "regular"


@st.cache_data
def load_games() -> pd.DataFrame:
    df = load_csv("games").copy()
    if df.empty:
        return df
    df["datetime_kst"] = _to_kst(df["datetime_utc"])
    for col in ["gamelength", "team1_kills", "team2_kills", "team1_gold", "team2_gold",
                "team1_dragons", "team2_dragons", "team1_barons", "team2_barons",
                "team1_towers", "team2_towers", "game_in_match"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["team1_picks", "team2_picks", "team1_bans", "team2_bans"]:
        df[col] = df[col].fillna("")
    tours = load_tournaments()[["page", "scope", "league_short", "year", "split", "stage", "name"]]
    return df.merge(tours.rename(columns={"name": "tournament"}), on="page", how="left")


@st.cache_data
def load_players(include_foreign: bool = False) -> pd.DataFrame:
    frames = [load_csv("players")]
    if include_foreign:
        frames.append(load_csv("players_foreign"))
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if df.empty:
        return df
    df["datetime_kst"] = _to_kst(df["datetime_utc"])
    for col in ["kills", "deaths", "assists", "cs", "gold", "damage", "vision",
                "team_kills", "team_gold"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["win"] = df["win"].eq("Yes")
    tours = load_tournaments()[["page", "scope", "league_short", "year", "split", "stage", "name"]]
    return df.merge(tours.rename(columns={"name": "tournament"}), on="page", how="left")


@st.cache_data
def load_schedule() -> pd.DataFrame:
    df = load_csv("schedule").copy()
    if df.empty:
        return df
    df["datetime_kst"] = _to_kst(df["datetime_utc"])
    for col in ["team1_score", "team2_score", "best_of"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["winner"] = pd.to_numeric(df["winner"], errors="coerce")
    df["tab"] = df["tab"].fillna("")
    tours = load_tournaments()[["page", "scope", "league_short", "year", "split", "stage", "name"]]
    return df.merge(tours.rename(columns={"name": "tournament"}), on="page", how="left")


@st.cache_data
def load_rosters() -> pd.DataFrame:
    df = load_csv("rosters").copy()
    if df.empty:
        return df
    tours = load_tournaments()[["page", "scope", "year", "split", "stage"]]
    return df.merge(tours, on="page", how="left")


@st.cache_data
def load_teams() -> pd.DataFrame:
    return load_csv("teams")


@st.cache_data
def load_team_renames() -> pd.DataFrame:
    df = load_csv("team_renames").copy()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


@st.cache_data
def load_champions() -> pd.DataFrame:
    return load_csv("champions")


@st.cache_data
def load_player_images() -> pd.DataFrame:
    """선수 사진 목록에 대회 연도·시작일을 붙인다 (시즌에 맞는 사진을 고르기 위해)."""
    df = load_csv("player_images").copy()
    if df.empty:
        return df
    tours = load_tournaments()[["page", "year", "date_start"]]
    df = df.merge(tours, on="page", how="left")
    # 대회 정보가 없는 사진은 파일 이름 속 연도(예: 'T1 Faker 2024 Split 2.png')로 보충
    file_year = pd.to_numeric(df["file"].str.extract(r"(20\d\d)")[0], errors="coerce")
    df["year"] = df["year"].astype("Float64").fillna(file_year)
    df["sort_date"] = pd.to_datetime(df["sort_date"], errors="coerce").fillna(df["date_start"])
    return df
