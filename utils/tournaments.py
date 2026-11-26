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
        if split.startswith("LCK"):          # 2025년~ 'LCK' / 'LCK Cup' (이름이 겹치지 않게)
            name = f"{year} {split}"
        else:
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


# ================================================================== 정규 시즌 순위 · 팀의 연간 대회 성적
def standings_from_series(series: pd.DataFrame) -> pd.DataFrame:
    """일정(시리즈) 표 → 순위표. 매치 승수 → 세트 득실 → 동률 팀 간 맞대결 승수 → 세트 승수 순."""
    played = series[series["winner"].isin([1, 2])]
    if played.empty:
        return pd.DataFrame()
    rows = []
    for _, r in played.iterrows():
        for side, opp in ((1, 2), (2, 1)):
            rows.append({"team": r[f"team{side}"], "win": r["winner"] == side,
                         "sw": r[f"team{side}_score"], "sl": r[f"team{opp}_score"]})
    rr = pd.DataFrame(rows)
    t = rr.groupby("team").agg(매치승=("win", "sum"), 매치=("win", "size"), 세트승=("sw", "sum"), 세트패=("sl", "sum"))
    t["매치패"] = t["매치"] - t["매치승"]
    t["세트득실"] = t["세트승"] - t["세트패"]
    t["_h2h"] = 0
    for _, grp in t.groupby(["매치승", "세트득실"]):
        if len(grp) > 1:
            names = list(grp.index)
            g = played[played["team1"].isin(names) & played["team2"].isin(names)]
            wins = pd.concat([g.loc[g["winner"] == 1, "team1"], g.loc[g["winner"] == 2, "team2"]]).value_counts()
            for n in names:
                t.at[n, "_h2h"] = int(wins.get(n, 0))
    t = t.sort_values(["매치승", "세트득실", "_h2h", "세트승"], ascending=False).drop(columns="_h2h")
    t.insert(0, "순위", range(1, len(t) + 1))
    return t


def _merge_names(series: pd.DataFrame) -> pd.DataFrame:
    """같은 계보의 팀 이름(예: DRX/Kiwoom DRX)을 하나로 바꾼 일정 표."""
    from utils.teams import lineage_groups
    groups = lineage_groups()
    s = series.copy()
    for col in ("team1", "team2"):
        s[col] = s[col].map(lambda t: groups.get(t, [t])[0])
    return s


def team_year_summary(team: str, year: int) -> tuple[list[tuple[str, int, int]], list[tuple[str, str]]]:
    """(정규 시즌 순위 목록 [(시즌, 순위, 팀 수)], 대회별 성적 [(대회, 결과)]) — 그 해 전체, 시간 순."""
    from utils.bracket import round_name, split_stages
    from utils.teams import lineage_groups
    key = lineage_groups().get(team, [team])[0]
    stage_of = dict(zip(load_tournaments()["page"], load_tournaments()["stage"]))
    ranks, results = [], []
    for ev in events()[events()["year"] == year].sort_values("start").itertuples():
        s = _merge_names(event_schedule(ev.pages))
        s = s[s["winner"].isin([1, 2])]
        mine = s[(s["team1"] == key) | (s["team2"] == key)]
        if mine.empty:
            continue
        lck = ev.scope == "LCK"
        label = (ev.split if str(ev.split).startswith("LCK") else f"LCK {ev.split}") if lck else ev.league
        # 정규 시즌 순위 (LCK, Cup 제외)
        if lck and ev.split != "LCK Cup":
            reg = s[s["page"].map(stage_of) == "regular"]
            table = standings_from_series(reg)
            if key in table.index:
                ranks.append((label, int(table.at[key, "순위"]), len(table)))
        # 대회 최종 성적
        final = s.iloc[-1]
        if key in (final["team1"], final["team2"]):
            won = (final["team1"] == key) == (final["winner"] == 1)
            results.append((label, "우승" if won else "준우승"))
            continue
        last = mine.iloc[-1]
        if lck:
            stage = stage_of.get(last["page"], "regular")
            po = mine[mine["page"].map(stage_of) == "playoffs"]
            if not po.empty:
                results.append((label, f"Play-off {round_name(po.iloc[-1]['tab'])} 탈락"))
            elif stage == "play-in" or (mine["page"].map(stage_of) == "play-in").any():
                results.append((label, "Play-in 탈락"))
            elif ev.split == "LCK Cup" and stage == "regular" and str(last["tab"]) in (
                    "Quarterfinals", "Semifinals", "Third-Place Match"):
                results.append((label, round_name(last["tab"])))
            else:
                results.append((label, "플레이오프 진출 실패"))
        else:
            stages = split_stages(s, ev.league, year)
            stage = next((n for n, part in stages.items() if last["match_id"] in set(part["match_id"])), "")
            if stage == "Knock-out Stage" and str(last["tab"]) == "Third-Place Match":
                won = (last["team1"] == key) == (last["winner"] == 1)
                results.append((label, "3위" if won else "4위"))
            elif stage == "Knock-out Stage":
                results.append((label, round_name(last["tab"])))
            else:
                results.append((label, f"{stage} 탈락" if stage else "탈락"))
    return ranks, results
