"""팀 관련 계산: 팀 시점 경기 데이터, 팀 계보(이름 변경 이력), 로고 주소."""
from __future__ import annotations

import hashlib
from pathlib import Path
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
    out = pd.DataFrame(rows).set_index("team")
    # Leaguepedia 팀 정보의 로고 파일이 없거나(404) 비어 있는 팀: 실제로 있는 다른 파일 이름으로 보완
    for name, file in LOGO_OVERRIDES.items():
        if name in out.index:
            out.at[name, "logo"] = logo_url(file)
        else:
            out.loc[name, ["logo", "current"]] = [logo_url(file), name]
    # Leaguepedia에 아예 없는 로고: 직접 받은 이미지 파일(assets/logos)
    for name, rel in LOCAL_LOGOS.items():
        if name not in out.index:
            out.loc[name, "current"] = name
        out.at[name, "logo"] = asset_uri(rel)
    # 팀 정보에 약칭이 없는 팀 (직접 받은 값)
    for name, short in SHORT_OVERRIDES.items():
        if name not in out.index:
            out.loc[name, "current"] = name
        out.at[name, "short"] = short
    return out


ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOCAL_LOGOS = {
    "Unicorns of Love.CIS": "logos/unicorns_of_love_cis.png",
    "GIGABYTE Marines": "logos/gigabyte_marines.png",
}
LOCAL_PHOTOS = {"Cry": "players/cry.png", "Hipo": "players/hipo.png"}
SHORT_OVERRIDES = {
    "DAMWON Gaming": "DWG", "Flamengo Esports": "FLA", "GIGABYTE Marines": "GAM",
    "MAD Lions": "MAD", "SANDBOX Gaming": "SB", "SuperMassive Esports": "SUP",
}


@st.cache_data
def asset_uri(rel: str) -> str | None:
    """assets 폴더의 이미지를 data URI로 (서버·브라우저 어디서나 별도 주소 없이 표시됨)."""
    import base64
    path = ASSETS / rel
    if not path.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


# 팀 정보에 적힌 로고 파일이 없을 때 쓰는 실제 파일 이름 (직접 확인함)
LOGO_OVERRIDES = {
    "Vikings Esports": "Vikings Esportslogo square.png",
    "Vikings Esports (2023 Vietnamese Team)": "Vikings Esports (2023 Vietnamese Team)logo square.png",
    "MAD Lions": "MAD Lionslogo profile.png",
    "DAMWON Gaming": "DAMWON Gaminglogo square.png",
    "DWG KIA": "DWG KIAlogo square.png",
    "LGD Gaming": "LGD Gaminglogo square.png",
    "SANDBOX Gaming": "SANDBOX Gaminglogo square.png",
    "Liiv SANDBOX": "Liiv SANDBOXlogo square.png",
    "Suning": "Suninglogo square.png",
    "Flamengo Esports": "Flamengo Esportslogo square.png",
    "SuperMassive Esports": "SuperMassive Esportslogo profile.png",
    "MVP": "MVPlogo square.png",
    "Virtus.pro": "Virtus.prologo square.png",
    "Young Generation": "Young Generationlogo std.png",
}


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
    for key, h in curated_history().items():  # 직접 정리한 팀 변천사(data/team_history.json)도 연결
        pairs += [(alias, key) for alias in h.get("aliases", [])]
    for a, b in pairs:
        parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for name in parent:
        groups.setdefault(find(name), []).append(name)
    return {name: sorted(members) for members in groups.values() for name in members}


def player_photo(player: str, pages=(), year: int | None = None, team: str | None = None) -> str | None:
    """선수 사진 고르기: ① 그 대회 사진 → ② 같은 해·같은 팀 → ③ 같은 해 → ④ 가장 가까운 해."""
    imgs = load_player_images()
    mine = imgs[imgs["player"] == player] if not imgs.empty else imgs
    if mine.empty:                                     # Leaguepedia에 사진이 없으면 직접 받은 사진
        return asset_uri(LOCAL_PHOTOS[player]) if player in LOCAL_PHOTOS else None
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


def team_logo(team: str) -> str | None:
    """팀 이름(옛 이름 포함) → 로고 주소."""
    info = team_info()
    return info.at[team, "logo"] if isinstance(team, str) and team in info.index else None


def team_label(team: str) -> str:
    """화면 표시용 팀 이름: Leaguepedia 구분용 괄호를 뗀다 (예: 'Griffin (Korean Team)' → 'Griffin')."""
    return team.split(" (")[0] if isinstance(team, str) else team


# ================================================================== 직접 정리한 팀 변천사
@st.cache_data
def curated_history() -> dict:
    """data/team_history.json — Leaguepedia 기록이 부족한 팀 이름 변천사를 직접 정리한 자료."""
    import json
    from utils.data_loader import DATA_DIR
    path = DATA_DIR / "team_history.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def history_for(team: str) -> dict | None:
    """팀(옛 이름 포함)에 해당하는 직접 정리한 변천사."""
    names = set(lineage_of(team)) | {team}
    for key, h in curated_history().items():
        if key in names or names & set(h.get("aliases", [])):
            return h
    return None


def history_html(h: dict) -> str:
    """변천사 HTML: 이름 상자를 화살표로 잇고, 갈래가 여러 개면 두 줄이 하나로 모이게 그린다."""
    gold, line = "#C89B3C", "rgba(128,128,128,0.35)"

    def chip(name, start, end, current=False):
        period = f"{start}&#126;{end}" if end else f"{start}&#126;"   # '~'는 마크다운 취소선이 되므로 엔티티로
        return (f"<div style='display:inline-flex;flex-direction:column;align-items:center;padding:7px 12px;"
                f"border-radius:10px;border:1px solid {gold if current else line};white-space:nowrap;"
                f"background:{'rgba(200,155,60,0.12)' if current else 'transparent'}'>"
                f"<span style='font-weight:700'>{name}</span>"
                f"<span style='font-size:0.75rem;opacity:0.7'>{period}</span></div>")

    arrow = "<span style='font-size:1.2rem;opacity:0.5;margin:0 4px'>→</span>"

    def chain(items, last_current=False):
        return arrow.join(chip(*it, current=last_current and i == len(items) - 1) for i, it in enumerate(items))

    main = chain(h["main"], last_current=True)
    if not h.get("branches"):
        return f"<div style='display:flex;flex-wrap:wrap;align-items:center;gap:4px'>{main}</div>"
    rows = "".join(f"<div style='display:flex;align-items:center;gap:4px;margin:4px 0'>{chain(b)}</div>"
                   for b in h["branches"])
    n = len(h["branches"])
    # 갈래 수만큼 선이 왼쪽에서 출발해 오른쪽 가운데로 모이는 연결선
    lines = "".join(f"<line x1='0' y1='{(i + 0.5) * 100 / n}' x2='100' y2='50' stroke='{line}' stroke-width='3'/>"
                    for i in range(n))
    connector = (f"<svg viewBox='0 0 100 100' preserveAspectRatio='none' style='width:44px;height:{60 * n}px'>"
                 f"{lines}</svg>")
    return (f"<div style='display:flex;align-items:center;gap:6px;overflow-x:auto;padding-bottom:4px'>"
            f"<div>{rows}</div>{connector}{arrow}"
            f"<div style='display:flex;align-items:center;gap:4px'>{main}</div></div>")


TEAM_COLUMNS = ("팀", "상대", "우승", "준우승", "팀 1", "팀 2", "승리")


def with_logos(df: pd.DataFrame, columns=TEAM_COLUMNS) -> tuple[pd.DataFrame, dict]:
    """표의 팀 이름 열 앞에 로고 열을 넣고 이름을 정리한다. (표, st.dataframe용 column_config)를 돌려준다."""
    out = df.copy()
    config = {}
    for col in [c for c in columns if c in out.columns]:
        logo_col = "로고" if col in ("팀", "상대") and "로고" not in out.columns else f"{col} 로고"
        out.insert(list(out.columns).index(col), logo_col, out[col].map(team_logo))
        out[col] = out[col].map(team_label)
        config[logo_col] = st.column_config.ImageColumn(" ", width="small")
    return out, config
