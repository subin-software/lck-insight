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

HEADER_BG = "linear-gradient(90deg,#1E1B4B,#4C1D95 55%,#1E1B4B)"
WIN_BG = "#DCFCE7"
GOLD_BG = "#FDE68A"


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


def _card(r, short, logo, seed, final: bool = False) -> str:
    rows = ""
    for side in (1, 2):
        team, score = r[f"team{side}"], r[f"team{side}_score"]
        won = pd.notna(r["winner"]) and r["winner"] == side
        bg = (GOLD_BG if final else WIN_BG) if won else "#FFFFFF"
        url = logo(team)
        img = f"<img src='{url}' style='width:46px;height:46px;object-fit:contain'>" if url else ""
        sd = seed(team)
        rows += (f"<div style='display:grid;grid-template-columns:56px 1fr 38px;border-top:1px solid #E5E7EB'>"
                 f"<div style='padding:6px 4px;text-align:center;background:#fff'>"
                 f"<div style='font-weight:800;color:#2563EB;font-size:0.95rem'>{short(team)}</div>"
                 f"<div style='font-size:0.68rem;color:#6B7280'>{sd}</div></div>"
                 f"<div style='display:flex;align-items:center;justify-content:center;background:{bg}'>{img}</div>"
                 f"<div style='display:flex;align-items:center;justify-content:center;font-size:1.35rem;"
                 f"font-weight:{800 if won else 500};color:#111827;background:#fff'>"
                 f"{'' if pd.isna(score) else int(score)}</div></div>")
    return (f"<div style='border:2px solid #1E1B4B;border-radius:6px;overflow:hidden;margin:6px 4px;"
            f"background:#fff;min-width:165px'>"
            f"<div style='background:{HEADER_BG};color:#fff;text-align:center;font-size:0.8rem;font-weight:700;"
            f"padding:5px 4px'>{r['label']}</div>{rows}</div>")


def render(series: pd.DataFrame, short, logo, seed, title: str) -> str:
    """대진표 HTML. short/logo/seed: 팀 이름 → 약칭 / 로고 주소 / 아래 작은 글씨(시드·순위)."""
    s = classify(series)
    th = ("background:#1E1B4B;color:#fff;font-weight:700;font-size:0.85rem;padding:8px;text-align:center;"
          "border:1px solid #312E81")
    td = "vertical-align:middle;padding:2px;border:1px solid #E5E7EB;background:#FAFAFA"

    def column_cells(part: pd.DataFrame, ncol: int, final_cell: str = "") -> str:
        cells = ""
        for c in range(ncol):
            cards = "".join(_card(r, short, logo, seed) for _, r in part[part["col"] == c].iterrows())
            cells += f"<td style='{td}'>{cards or '<div style=\"text-align:center;opacity:0.4\">→</div>'}</td>"
        return cells + final_cell

    head = (f"<div style='background:{HEADER_BG};color:#fff;padding:14px 18px;border-radius:8px 8px 0 0'>"
            f"<div style='font-size:1.3rem;font-weight:800'>{title}</div></div>")
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
        sec = "text-align:center;font-weight:700;padding:6px;font-size:0.9rem"
        body = (f"<tr><td colspan='{ncol}' style='{sec};background:#C7D2FE'>승자조 대진표 (Upper Bracket)</td>"
                f"<td rowspan='4' style='{td};background:#fff'>{final_cards}</td></tr>"
                f"<tr>{column_cells(up, ncol)}</tr>"
                f"<tr><td colspan='{ncol}' style='{sec};background:#FECACA'>패자조 대진표 (Lower Bracket)</td></tr>"
                f"<tr>{column_cells(low, ncol)}</tr>")
    return (f"<div style='overflow-x:auto;border:2px solid #1E1B4B;border-radius:10px'>{head}"
            f"<table style='border-collapse:collapse;width:100%;table-layout:fixed;min-width:{185 * (ncol + 1)}px'>"
            f"<tr>{header}</tr>{body}</table></div>")
