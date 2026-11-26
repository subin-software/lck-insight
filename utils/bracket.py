"""대진표 그리기: 시리즈 결과로 승자조/패자조를 판단하고 HTML 대진표를 만든다.

Leaguepedia 일정에는 'Round 1', 'Finals' 같은 라운드 이름만 있고 승자조·패자조 구분이 없다.
그래서 같은 단계 안에서 '그 경기 전에 이미 시리즈를 진 적이 있는지'로 판단한다.
- 두 팀 모두 패배 기록 없음 → 승자조 (Upper Bracket)
- 두 팀 모두 1패 이상 → 패자조 (Lower Bracket)
- 단계의 마지막 경기 → 결승
패자조 경기가 하나도 없으면(단판 토너먼트·건틀릿 형식) 라운드별로 한 줄로 그린다.
"""
from __future__ import annotations

import pandas as pd



def classify(series: pd.DataFrame) -> pd.DataFrame:
    """시리즈마다 bracket(upper/lower/final/round)과 열 번호(col), 이름(label)을 붙인다."""
    s = series.sort_values("datetime_kst").reset_index(drop=True).copy()
    losses: dict[str, int] = {}
    kinds = []
    for i, r in s.iterrows():
        la, lb = losses.get(r["team1"], 0), losses.get(r["team2"], 0)
        if i == len(s) - 1 and str(r["tab"]).lower().startswith("final"):
            kinds.append("final")
        elif la == 0 and lb == 0:
            kinds.append("upper")
        elif la > 0 and lb > 0:
            kinds.append("lower")
        else:
            kinds.append("mixed")
        if pd.notna(r["winner"]):
            loser = r["team2"] if r["winner"] == 1 else r["team1"]
            losses[loser] = losses.get(loser, 0) + 1
    s["kind"] = kinds
    double = (s["kind"] == "lower").any() and not (s["kind"] == "mixed").any()
    if not double:                                   # 건틀릿·단판 토너먼트: 라운드 이름 순서대로 한 줄
        tabs = list(dict.fromkeys(s["tab"]))
        s["bracket"] = "round"
        s["col"] = s["tab"].map({t: i for i, t in enumerate(tabs)})
    else:
        s["bracket"] = s["kind"]
        s["col"] = 0
        for b in ("upper", "lower"):
            tabs = list(dict.fromkeys(s.loc[s["bracket"] == b, "tab"]))   # 그 조 안에서 라운드 순서
            s.loc[s["bracket"] == b, "col"] = s.loc[s["bracket"] == b, "tab"].map({t: i for i, t in enumerate(tabs)})
    # 이름 붙이기
    labels = []
    for _, r in s.iterrows():
        date = f"{r['datetime_kst']:%m/%d}".lstrip("0").replace("/0", "/")
        if r["bracket"] == "final":
            labels.append(f"Grand Finals ({date})")
        elif r["bracket"] == "round":
            same = s[(s["bracket"] == "round") & (s["col"] == r["col"])]
            n = list(same.index).index(r.name) + 1
            name = "결승" if str(r["tab"]).lower().startswith("final") else str(r["tab"]).replace("Round ", "R")
            labels.append(f"{name}{f' M{n}' if len(same) > 1 else ''} ({date})")
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


GOLD = "#C89B3C"
LINE = "rgba(128,128,128,0.22)"          # 앱 다른 화면과 같은 옅은 회색 테두리
WIN_TINT = "rgba(200,155,60,0.12)"       # 이긴 팀: 앱 공통 금색을 옅게


def _card(r, short, logo, seed, final: bool = False) -> str:
    """경기 카드: 작은 경기 이름 + 두 팀 줄 (이긴 팀은 옅은 금색 배경·금색 점수, 진 팀은 흐리게)."""
    rows = ""
    for side in (1, 2):
        team, score = r[f"team{side}"], r[f"team{side}_score"]
        won = pd.notna(r["winner"]) and r["winner"] == side
        url = logo(team)
        img = f"<img src='{url}' style='width:26px;height:26px;object-fit:contain'>" if url else ""
        sd = seed(team)
        rows += (f"<div style='display:flex;align-items:center;gap:8px;padding:6px 10px;"
                 f"background:{WIN_TINT if won else 'transparent'};opacity:{1 if won else 0.6}'>"
                 f"{img}<div style='flex:1;line-height:1.15'><div style='font-weight:700'>{short(team)}</div>"
                 f"<div style='font-size:0.7rem;opacity:0.7'>{sd}</div></div>"
                 f"<div style='font-size:1.15rem;font-weight:{800 if won else 500};"
                 f"color:{GOLD if won else 'inherit'}'>{'' if pd.isna(score) else int(score)}</div></div>")
    border = f"1px solid {GOLD}" if final else f"1px solid {LINE}"
    return (f"<div style='border:{border};border-radius:10px;overflow:hidden;margin:6px 4px;min-width:150px'>"
            f"<div style='font-size:0.72rem;opacity:0.65;padding:5px 10px;border-bottom:1px solid {LINE}'>"
            f"{'🏆 ' if final else ''}{r['label']}</div>{rows}</div>")


def render(series: pd.DataFrame, short, logo, seed, title: str) -> str:
    """대진표 HTML. short/logo/seed: 팀 이름 → 약칭 / 로고 주소 / 아래 작은 글씨(시드·순위)."""
    s = classify(series)
    th = (f"font-weight:600;font-size:0.8rem;opacity:0.7;padding:6px 4px;text-align:center;"
          f"border-bottom:1px solid {LINE}")
    td = "vertical-align:middle;padding:2px;border:none"

    def column_cells(part: pd.DataFrame, ncol: int) -> str:
        cells = ""
        for c in range(ncol):
            cards = "".join(_card(r, short, logo, seed) for _, r in part[part["col"] == c].iterrows())
            cells += f"<td style='{td}'>{cards or '<div style=\"text-align:center;opacity:0.3\">→</div>'}</td>"
        return cells

    def section(label: str, ncol: int) -> str:
        return (f"<tr><td colspan='{ncol}' style='padding:10px 4px 2px'>"
                f"<span style='font-size:0.8rem;font-weight:700;border-left:3px solid {GOLD};padding-left:8px'>"
                f"{label}</span></td></tr>")

    head = f"<div style='font-weight:700;font-size:1.05rem;margin-bottom:6px'>{title}</div>"
    if (s["bracket"] == "round").all():
        ncol = int(s["col"].max()) + 1
        names = [("결승" if str(t).lower().startswith("final") else str(t).replace("Round ", "") + "라운드")
                 for t in dict.fromkeys(s["tab"])]
        header = "".join(f"<th style='{th}'>{n}</th>" for n in names)
        body = f"<tr>{column_cells(s, ncol)}</tr>"
    else:
        up, low, fin = s[s["bracket"] == "upper"], s[s["bracket"] == "lower"], s[s["bracket"] == "final"]
        ncol = int(max(up["col"].max() if not up.empty else 0, low["col"].max() if not low.empty else 0)) + 1
        header = "".join(f"<th style='{th}'>{i + 1}라운드</th>" for i in range(ncol)) + f"<th style='{th}'>결승</th>"
        final_cards = "".join(_card(r, short, logo, seed, final=True) for _, r in fin.iterrows())
        body = (section("승자조 (Upper Bracket)", ncol).replace("</tr>", f"<td rowspan='4' style='{td}'>{final_cards}</td></tr>", 1)
                + f"<tr>{column_cells(up, ncol)}</tr>"
                + section("패자조 (Lower Bracket)", ncol)
                + f"<tr>{column_cells(low, ncol)}</tr>")
    return (f"<div style='border:1px solid {LINE};border-radius:12px;padding:14px 16px;overflow-x:auto'>{head}"
            f"<table style='border-collapse:collapse;width:100%;table-layout:fixed;min-width:{165 * (ncol + 1)}px'>"
            f"<tr>{header}</tr>{body}</table></div>")
