"""대진표 그리기: 대회 단계 나누기, 승자조/패자조 판단, 스위스·조별·토너먼트 화면을 HTML로 만든다.

Leaguepedia 일정에는 'Round 1', 'Day 3', 'Quarterfinals' 같은 라운드 이름만 있고 단계(스위스·조별 등),
조 이름, 승자조/패자조 구분은 없다. 그래서 다음 규칙으로 판단한다.
- 단계: 해마다 다른 라운드 이름 규칙(stage_of)으로 Play-in / Group / Swiss / Bracket / Knock-out 등으로 나눔
- 조: 조별 리그에서는 같은 조끼리만 경기하므로, '서로 경기한 팀끼리 이어지는 묶음'을 하나의 조로 봄
- 승자조/패자조: 같은 단계 안에서 '그 경기 전에 이미 시리즈를 진 적이 있는지'
"""
from __future__ import annotations

import re

import pandas as pd

GOLD = "#C89B3C"
LINE = "rgba(128,128,128,0.22)"          # 앱 다른 화면과 같은 옅은 회색 테두리
WIN_TINT = "rgba(200,155,60,0.12)"       # 이긴 팀: 앱 공통 금색을 옅게

GROUP_TAB = re.compile(r"^(Day \d+|Groups Day \d+|Groups Tiebreakers|Tiebreakers|Group Stage|Rumble Day \d+)$")
STAGE_ORDER = ["Road to MSI", "Play-in", "Group Stage", "Rumble Stage", "Swiss Stage", "Bracket Stage",
               "Knock-out Stage", "Play-off"]
ROUND_KO = {"Quarterfinals": "8강", "Semifinals": "4강", "Finals": "결승", "Third-Place Match": "3·4위전",
            "Elimination Round": "탈락전", "Qualification Round": "진출전", "Last Chance Qualifier": "최종 예선",
            "Knockout Stage": "녹아웃", "Qualifiers": "진출전", "Play-In": "단판 승부", "Tiebreakers": "순위 결정전"}


def round_name(tab: str) -> str:
    """라운드 이름 한국어로 (예: 'Bracket Round 2' → '2라운드', 'Play-In Day 3' → '3일차')."""
    tab = str(tab)
    if tab in ROUND_KO:
        return ROUND_KO[tab]
    m = re.match(r"^(?:Bracket |Playoffs |Play-In )?Round (\d+)$", tab)
    if m:
        return f"{m.group(1)}라운드"
    m = re.match(r"^(?:Play-In |Groups |Rumble )?Day (\d+)$", tab)
    if m:
        return f"{m.group(1)}일차"
    return tab


# ================================================================== 단계 나누기 (국제 대회)
def stage_of(page: str, tab: str, league: str, year: int, has_bracket_rounds: bool) -> str:
    tab = str(tab)
    if "Play-In" in page or tab.startswith("Play-In") or tab == "Last Chance Qualifier":
        return "Play-in"
    if tab.startswith("Bracket Round") or (has_bracket_rounds and tab == "Finals"):
        return "Bracket Stage"
    if tab.startswith("Rumble"):
        return "Rumble Stage"
    if league == "Worlds" and year >= 2023 and page.endswith("Main Event") and tab.startswith("Round"):
        return "Swiss Stage"
    if GROUP_TAB.match(tab):
        return "Group Stage"
    return "Knock-out Stage"


def split_stages(series: pd.DataFrame, league: str, year: int) -> dict[str, pd.DataFrame]:
    """국제 대회 시리즈를 단계별로 나눈다 (그 해 실제 포맷에 있는 단계만)."""
    if series.empty:
        return {}
    bracket_rounds = series["tab"].astype(str).str.startswith("Bracket Round").any()
    stage = series.apply(lambda r: stage_of(r["page"], r["tab"], league, year, bracket_rounds), axis=1)
    return {name: series[stage == name] for name in STAGE_ORDER if (stage == name).any()}


# ================================================================== 경기 분류 (토너먼트)
def classify(series: pd.DataFrame, force_round: bool = False) -> pd.DataFrame:
    """시리즈마다 bracket(upper/lower/final/round)과 열 번호(col), 이름(label), 경기 전 전적을 붙인다.

    force_round=True(스위스 스테이지)면 승자조·패자조를 나누지 않고 라운드 순서대로만 놓는다.
    """
    s = series.sort_values("datetime_kst").reset_index(drop=True).copy()
    losses: dict[str, int] = {}
    record: dict[str, list[int]] = {}
    kinds, rec1, rec2 = [], [], []
    for i, r in s.iterrows():
        la, lb = losses.get(r["team1"], 0), losses.get(r["team2"], 0)
        w1, l1 = record.get(r["team1"], [0, 0])
        w2, l2 = record.get(r["team2"], [0, 0])
        rec1.append(f"{w1}승 {l1}패")
        rec2.append(f"{w2}승 {l2}패")
        if i == len(s) - 1 and str(r["tab"]).lower().startswith("final"):
            kinds.append("final")
        elif str(r["tab"]) == "Third-Place Match":       # 3·4위전은 패자조가 아님
            kinds.append("third")
        elif la == 0 and lb == 0:
            kinds.append("upper")
        elif la > 0 and lb > 0:
            kinds.append("lower")
        else:
            kinds.append("mixed")
        if pd.notna(r["winner"]):
            winner, loser = (r["team1"], r["team2"]) if r["winner"] == 1 else (r["team2"], r["team1"])
            losses[loser] = losses.get(loser, 0) + 1
            record.setdefault(winner, [0, 0])[0] += 1
            record.setdefault(loser, [0, 0])[1] += 1
    s["kind"], s["rec1"], s["rec2"] = kinds, rec1, rec2
    double = (not force_round and (s["kind"] == "lower").any() and not (s["kind"] == "mixed").any()
              and not (s["kind"] == "third").any())
    if not double:                                   # 단판 토너먼트·건틀릿·스위스: 라운드 이름 순서대로
        tabs = list(dict.fromkeys(s["tab"]))
        s["bracket"] = "round"
        s["col"] = s["tab"].map({t: i for i, t in enumerate(tabs)})
    else:
        s["bracket"] = s["kind"]
        s["col"] = 0
        for b in ("upper", "lower"):
            tabs = list(dict.fromkeys(s.loc[s["bracket"] == b, "tab"]))   # 그 조 안에서 라운드 순서
            s.loc[s["bracket"] == b, "col"] = s.loc[s["bracket"] == b, "tab"].map({t: i for i, t in enumerate(tabs)})
    labels = []
    for _, r in s.iterrows():
        date = f"{r['datetime_kst'].month}/{r['datetime_kst'].day}"
        if r["bracket"] == "final":
            labels.append(f"Grand Finals ({date})")
        elif r["bracket"] == "round":
            same = s[(s["bracket"] == "round") & (s["col"] == r["col"])]
            n = list(same.index).index(r.name) + 1
            labels.append(f"{round_name(r['tab'])}{f' M{n}' if len(same) > 1 else ''} ({date})")
        else:
            same = s[(s["bracket"] == r["bracket"]) & (s["col"] == r["col"])]
            n = list(same.index).index(r.name) + 1
            prefix = "UB" if r["bracket"] == "upper" else "LB"
            last_col = s.loc[s["bracket"] == r["bracket"], "col"].max()
            if r["bracket"] == "lower" and r["col"] == last_col and len(same) == 1:
                labels.append(f"Lower Finals ({date})")
            else:
                labels.append(f"{prefix} R{int(r['col']) + 1}{f' M{n}' if len(same) > 1 else ''} ({date})")
    s["label"] = labels
    return s


# ================================================================== 공통 조각
TH = (f"font-weight:600;font-size:0.8rem;opacity:0.7;padding:6px 4px;text-align:center;"
      f"border-bottom:1px solid {LINE}")
TD = "vertical-align:middle;padding:2px;border:none"


def _card(r, short, logo, notes: tuple[str, str], final: bool = False) -> str:
    """경기 카드: 작은 경기 이름 + 두 팀 줄 (이긴 팀은 옅은 금색 배경·금색 점수, 진 팀은 흐리게)."""
    rows = ""
    for side, note in zip((1, 2), notes):
        team, score = r[f"team{side}"], r[f"team{side}_score"]
        won = pd.notna(r["winner"]) and r["winner"] == side
        url = logo(team)
        img = f"<img src='{url}' style='width:26px;height:26px;object-fit:contain'>" if url else ""
        rows += (f"<div style='display:flex;align-items:center;gap:8px;padding:6px 10px;"
                 f"background:{WIN_TINT if won else 'transparent'};opacity:{1 if won else 0.6}'>"
                 f"{img}<div style='flex:1;line-height:1.15'><div style='font-weight:700'>{short(team)}</div>"
                 f"<div style='font-size:0.7rem;opacity:0.7'>{note}</div></div>"
                 f"<div style='font-size:1.15rem;font-weight:{800 if won else 500};"
                 f"color:{GOLD if won else 'inherit'}'>{'' if pd.isna(score) else int(score)}</div></div>")
    border = f"1px solid {GOLD}" if final else f"1px solid {LINE}"
    return (f"<div style='border:{border};border-radius:10px;overflow:hidden;margin:6px 4px;min-width:150px'>"
            f"<div style='font-size:0.72rem;opacity:0.65;padding:5px 10px;border-bottom:1px solid {LINE}'>"
            f"{'🏆 ' if final else ''}{r['label']}</div>{rows}</div>")


def _box(title: str, inner: str, ncol: int) -> str:
    return (f"<div style='border:1px solid {LINE};border-radius:12px;padding:14px 16px;overflow-x:auto;"
            f"margin-bottom:12px'><div style='font-weight:700;font-size:1.05rem;margin-bottom:6px'>{title}</div>"
            f"<table style='border-collapse:collapse;width:100%;table-layout:fixed;min-width:{165 * ncol}px'>"
            f"{inner}</table></div>")


def _section(label: str, ncol: int) -> str:
    return (f"<tr><td colspan='{ncol}' style='padding:10px 4px 2px'>"
            f"<span style='font-size:0.8rem;font-weight:700;border-left:3px solid {GOLD};padding-left:8px'>"
            f"{label}</span></td></tr>")


# ================================================================== 토너먼트 (더블·단판·건틀릿·스위스)
def render(series: pd.DataFrame, short, logo, seed, title: str, use_record: bool = False) -> str:
    """토너먼트 대진표. seed: 팀 → 팀 이름 아래 작은 글씨. use_record=True면 대신 '경기 전 전적'을 쓴다."""
    s = classify(series, force_round=use_record)

    def notes(r):
        return (r["rec1"], r["rec2"]) if use_record else (seed(r["team1"]), seed(r["team2"]))

    def cells(part: pd.DataFrame, ncol: int) -> str:
        out = ""
        for c in range(ncol):
            cards = "".join(_card(r, short, logo, notes(r)) for _, r in part[part["col"] == c].iterrows())
            out += f"<td style='{TD}'>{cards or '<div style=\"text-align:center;opacity:0.3\">→</div>'}</td>"
        return out

    if (s["bracket"] == "round").all():
        ncol = int(s["col"].max()) + 1
        header = "".join(f"<th style='{TH}'>{round_name(t)}</th>" for t in dict.fromkeys(s["tab"]))
        return _box(title, f"<tr>{header}</tr><tr>{cells(s, ncol)}</tr>", ncol)

    up, low, fin = s[s["bracket"] == "upper"], s[s["bracket"] == "lower"], s[s["bracket"] == "final"]
    ncol = int(max(up["col"].max() if not up.empty else 0, low["col"].max() if not low.empty else 0)) + 1
    header = "".join(f"<th style='{TH}'>{i + 1}라운드</th>" for i in range(ncol)) + f"<th style='{TH}'>결승</th>"
    final_cards = "".join(_card(r, short, logo, notes(r), final=True) for _, r in fin.iterrows())
    body = (_section("승자조 (Upper Bracket)", ncol).replace(
                "</tr>", f"<td rowspan='4' style='{TD}'>{final_cards}</td></tr>", 1)
            + f"<tr>{cells(up, ncol)}</tr>"
            + _section("패자조 (Lower Bracket)", ncol)
            + f"<tr>{cells(low, ncol)}</tr>")
    return _box(title, f"<tr>{header}</tr>{body}", ncol + 1)


# ================================================================== 조별 리그
def find_groups(series: pd.DataFrame) -> list[list[str]]:
    """서로 경기한 팀끼리 이어 조를 만든다 (조별 리그는 같은 조끼리만 경기하므로)."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    order = []
    for a, b in series.sort_values("datetime_kst")[["team1", "team2"]].itertuples(index=False):
        for t in (a, b):
            if t not in order:
                order.append(t)
        parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for t in order:
        groups.setdefault(find(t), []).append(t)
    return list(groups.values())


def render_groups(series: pd.DataFrame, short, logo, title: str) -> str:
    """조마다 순위표(매치 승패·세트 득실) + 경기 결과 목록."""
    played = series[series["winner"].notna()]
    groups = find_groups(series)
    cards = []
    for gi, teams in enumerate(groups):
        g = played[played["team1"].isin(teams)]
        rows = []
        for t in teams:
            m1, m2 = g[g["team1"] == t], g[g["team2"] == t]
            w = int((m1["winner"] == 1).sum() + (m2["winner"] == 2).sum())
            n = len(m1) + len(m2)
            sd = int(m1["team1_score"].sum() - m1["team2_score"].sum()
                     + m2["team2_score"].sum() - m2["team1_score"].sum())
            rows.append((t, w, n - w, sd))
        rows.sort(key=lambda x: (-x[1], -x[3]))
        table = "".join(
            f"<div style='display:flex;align-items:center;gap:8px;padding:5px 8px;"
            f"background:{WIN_TINT if i < 2 else 'transparent'};border-radius:6px'>"
            f"<span style='width:16px;opacity:0.6;font-size:0.8rem'>{i + 1}</span>"
            + (f"<img src='{logo(t)}' style='width:22px;height:22px;object-fit:contain'>" if logo(t) else "")
            + f"<span style='flex:1;font-weight:700'>{short(t)}</span>"
              f"<span style='font-size:0.85rem'>{w}승 {l}패</span>"
              f"<span style='font-size:0.75rem;opacity:0.6;width:34px;text-align:right'>{sd:+d}</span></div>"
            for i, (t, w, l, sd) in enumerate(rows))
        matches = "".join(
            f"<div style='display:flex;justify-content:space-between;font-size:0.8rem;padding:3px 8px;"
            f"border-top:1px solid {LINE}'><span style='opacity:0.6'>{r.datetime_kst.month}/{r.datetime_kst.day}</span>"
            f"<span><b style='color:{GOLD if r.winner == 1 else 'inherit'}'>{short(r.team1)}</b> "
            f"{int(r.team1_score)}:{int(r.team2_score)} "
            f"<b style='color:{GOLD if r.winner == 2 else 'inherit'}'>{short(r.team2)}</b></span></div>"
            for r in g.sort_values("datetime_kst").itertuples())
        name = f"{chr(ord('A') + gi)}조" if len(groups) > 1 else "순위"
        cards.append(f"<div style='border:1px solid {LINE};border-radius:10px;padding:10px'>"
                     f"<div style='font-weight:700;margin-bottom:6px;border-left:3px solid {GOLD};padding-left:8px'>"
                     f"{name}</div>{table}<div style='margin-top:8px'>{matches}</div></div>")
    return (f"<div style='border:1px solid {LINE};border-radius:12px;padding:14px 16px;margin-bottom:12px'>"
            f"<div style='font-weight:700;font-size:1.05rem;margin-bottom:8px'>{title}</div>"
            f"<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px'>"
            f"{''.join(cards)}</div></div>")


# ================================================================== 단계 하나 그리기
def render_stage(series: pd.DataFrame, stage: str, short, logo, seed, title: str) -> str:
    """단계 안에 조별 경기(일차·타이브레이커)와 토너먼트 경기가 섞여 있으면 둘 다 그린다."""
    is_group = series["tab"].astype(str).str.match(GROUP_TAB)
    html = ""
    if is_group.any():
        html += render_groups(series[is_group], short, logo, f"{title} — 조별 순위")
    rest = series[~is_group]
    if not rest.empty:
        swiss = stage == "Swiss Stage"
        suffix = " — 라운드별 결과" if swiss else (" — 토너먼트" if is_group.any() else "")
        html += render(rest, short, logo, seed, title + suffix, use_record=swiss)
    return html
