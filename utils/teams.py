"""팀 관련 계산: 팀 시점 경기 데이터, 팀 계보(이름 변경 이력), 로고 주소."""
from __future__ import annotations

import hashlib
from urllib.parse import quote

import pandas as pd
import streamlit as st

from utils.data_loader import (load_csv, load_games, load_player_images, load_schedule,
                               load_team_renames, load_teams)

ROLE_ORDER = {"Top": 0, "Jungle": 1, "Mid": 2, "Bot": 3, "Support": 4}
ROLE_KO = {"Top": "탑", "Jungle": "정글", "Mid": "미드", "Bot": "원딜", "Support": "서포터",
           "Coach": "코치", "Head Coach": "감독"}


def image_url(file_name: str | float) -> str | None:
    """Leaguepedia 파일 이름 → 이미지 실제 주소.

    MediaWiki는 파일을 'MD5(파일이름)' 앞 1·2글자 폴더에 저장하므로 API 호출 없이 주소를 만들 수 있다.
    (Special:FilePath 리다이렉트는 자동 요청을 차단(403)해서 쓰지 않는다.)
    """
    if not isinstance(file_name, str) or not file_name:
        return None
    name = file_name.replace(" ", "_")
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    return f"https://static.wikia.nocookie.net/lolesports_gamepedia_en/images/{h[0]}/{h[:2]}/{quote(name)}"


logo_url = image_url


@st.cache_data
def resolve_map() -> dict[str, str]:
    """경기 기록 속 팀 이름(옛 이름 포함) → Leaguepedia 현재 팀 페이지 이름."""
    teams = load_teams()
    if teams.empty:
        return {}
    known = set(teams["team"])
    lower = {t.lower(): t for t in known}
    out = {t: t for t in known}
    redirects = load_csv("team_redirects")
    for alias, page in redirects[["alias", "team"]].dropna().itertuples(index=False):
        if page in known:
            out.setdefault(alias, page)
    names = set(load_games()[["team1", "team2"]].stack()) | set(load_schedule()[["team1", "team2"]].stack())
    for n in names - set(out):
        if n.lower() in lower:            # 대소문자만 다른 경우 (예: Dplus KIA / Dplus Kia)
            out[n] = lower[n.lower()]
    return out


@st.cache_data
def team_info() -> pd.DataFrame:
    """팀 이름(옛 이름 포함) → 약칭, 지역, 로고, 해체 여부, 현재 이름."""
    df = load_teams().copy()
    if df.empty:
        return df
    df["logo"] = df["image"].map(logo_url)
    base = df.set_index("team")
    rows = []
    for alias, page in resolve_map().items():
        row = base.loc[page].to_dict()
        row.update(team=alias, current=page)
        rows.append(row)
    return pd.DataFrame(rows).set_index("team")


@st.cache_data
def team_games() -> pd.DataFrame:
    """경기 1건을 두 팀 시점의 2행으로 펼친다 (팀, 상대, 진영, 승패, 픽·밴 ...)."""
    g = load_games()
    if g.empty:
        return g
    common = ["game_id", "match_id", "page", "datetime_kst", "patch", "gamelength", "scope",
              "league_short", "year", "split", "stage", "tournament", "game_in_match"]
    sides = []
    for me, op, side in [("team1", "team2", "Blue"), ("team2", "team1", "Red")]:
        part = g[common].copy()
        part["team"] = g[me]
        part["opponent"] = g[op]
        part["side"] = side
        part["win"] = g["win_team"] == g[me]
        part["picks"] = g[f"{me}_picks"]
        part["bans"] = g[f"{me}_bans"]
        part["opp_picks"] = g[f"{op}_picks"]
        for stat in ["kills", "gold", "dragons", "barons", "towers"]:
            part[stat] = g[f"{me}_{stat}"]
            part[f"opp_{stat}"] = g[f"{op}_{stat}"]
        sides.append(part)
    return pd.concat(sides, ignore_index=True).sort_values("datetime_kst")


@st.cache_data
def team_series() -> pd.DataFrame:
    """일정(시리즈) 1건을 두 팀 시점의 2행으로 펼친다. 끝난 경기만."""
    s = load_schedule()
    if s.empty:
        return s
    s = s[s["winner"].isin([1, 2])]
    common = ["match_id", "page", "datetime_kst", "best_of", "tab", "scope", "league_short",
              "year", "split", "stage", "tournament"]
    rows = []
    for me, op, num in [("team1", "team2", 1), ("team2", "team1", 2)]:
        part = s[common].copy()
        part["team"] = s[me]
        part["opponent"] = s[op]
        part["score"] = s[f"{me}_score"]
        part["opp_score"] = s[f"{op}_score"]
        part["win"] = s["winner"] == num
        rows.append(part)
    return pd.concat(rows, ignore_index=True).sort_values("datetime_kst")


@st.cache_data
def lineage_groups() -> dict[str, list[str]]:
    """팀 이름 → 같은 계보(이름 변경으로 이어진)에 속한 모든 이름 목록.

    TeamRenames 의 (옛 이름, 새 이름) 쌍을 간선으로 보고 연결된 이름끼리 묶는다.
    """
    renames = load_team_renames()
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs = list(renames[["original_name", "new_name"]].dropna().itertuples(index=False))
    pairs += list(resolve_map().items())     # 옛 이름 → 현재 팀 페이지 연결도 계보로 본다
    for a, b in pairs:
        parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for name in parent:
        groups.setdefault(find(name), []).append(name)
    return {name: sorted(members) for members in groups.values() for name in members}


def player_photo(player: str, pages=(), year: int | None = None, team: str | None = None) -> str | None:
    """선수 사진 고르기: ① 그 대회 사진 → ② 같은 해·같은 팀 → ③ 같은 해 → ④ 가장 가까운 해."""
    imgs = load_player_images()
    if imgs.empty:
        return None
    mine = imgs[imgs["player"] == player]
    if mine.empty:
        return None
    for cond in [mine["page"].isin(list(pages)),
                 (mine["year"] == year) & (mine["team"] == team),
                 mine["year"] == year]:
        hit = mine[cond]
        if not hit.empty:
            return hit.sort_values("sort_date").iloc[-1]["url"]
    if year is not None and mine["year"].notna().any():
        return mine.loc[(mine["year"] - year).abs().idxmin(), "url"]
    return mine.iloc[-1]["url"]


def lineage_of(team: str) -> list[str]:
    return lineage_groups().get(team, [team])


def season_aliases(games: pd.DataFrame) -> dict[str, str]:
    """기간 중 이름이 바뀐 팀(예: DRX → Kiwoom DRX)을 하나로 합친다.

    같은 계보에 속한 이름들은 그 기간에 '가장 마지막으로 쓴 이름' 하나로 표시한다.
    games: team, datetime_kst 열이 있는 팀 시점 경기 데이터
    """
    groups = lineage_groups()
    last_used = games.groupby("team")["datetime_kst"].max()
    by_root: dict[str, list[str]] = {}
    for name in last_used.index:
        by_root.setdefault(groups.get(name, [name])[0], []).append(name)
    return {n: max(members, key=lambda m: last_used[m]) for members in by_root.values() for n in members}


def current_status(team: str) -> tuple[str, bool]:
    """(계보에서 가장 최근에 경기한 이름, 해체 여부). 이름이 바뀌어 이어진 팀은 해체로 보지 않는다."""
    g = team_games()
    names = lineage_of(team)
    last = g[g["team"].isin(names)].sort_values("datetime_kst")
    latest = last["team"].iloc[-1] if not last.empty else team
    info = team_info()
    disbanded = (latest in info.index and str(info.at[latest, "is_disbanded"]) in ("1", "1.0", "True")
                 and info.at[latest, "current"] == latest)
    return latest, disbanded


def display_name(player: str) -> str:
    """동명이인 구분용 괄호를 뗀 표시 이름 (예: 'Duke (Lee Ho-seong)' → 'Duke')."""
    return player.split(" (")[0] if isinstance(player, str) else player


def rename_history(team: str) -> pd.DataFrame:
    names = set(lineage_of(team))
    r = load_team_renames()
    r = r[r["original_name"].isin(names) | r["new_name"].isin(names)]
    return r.sort_values("date")
