"""팀·선수 분석 리포트 만들기: 데이터 정리 → Excel(openpyxl) / PDF(reportlab) 파일 생성.

PDF의 한글은 reportlab 내장 CID 폰트(HYGothic-Medium)를 써서 폰트 파일 없이도 서버에서 깨지지 않는다.
그래프는 matplotlib로 그려 PNG로 넣는데, 서버에 한글 폰트가 없으므로 그래프 안 글자는 영문·숫자만 쓴다.
"""
from __future__ import annotations

import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")                     # 화면 없는 서버에서 그림만 만들기
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # noqa: E402
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from utils import champions as champ  # noqa: E402
from utils.data_loader import load_players, load_tournaments  # noqa: E402
from utils.players import player_games, style_clusters, summarize  # noqa: E402
from utils.teams import (ROLE_KO, ROLE_ORDER, display_name, lineage_of, season_aliases,  # noqa: E402
                         team_games, team_series)

GOLD = "#C89B3C"
FONT = "HYGothic-Medium"
pdfmetrics.registerFont(UnicodeCIDFont(FONT))
TAB_KO = {"Finals": "결승", "Semifinals": "준결승", "Quarterfinals": "8강"}


def _tab_ko(tab: str) -> str:
    if tab in TAB_KO:
        return TAB_KO[tab]
    return str(tab).replace("Round ", "") + "라운드" if str(tab).startswith("Round ") else tab


# ================================================================== 데이터 정리
def team_report(year: int, split: str, team: str) -> dict:
    """팀 시즌 리포트에 들어갈 요약·표·그래프 데이터."""
    tours = load_tournaments()
    lck = tours[(tours["scope"] == "LCK") & (tours["year"] == year)]
    if split != "시즌 전체":
        lck = lck[lck["split"].replace("", "기타") == split]
    pages = list(lck.sort_values("date_start")["page"])

    games = team_games()
    games = games[games["page"].isin(pages)].copy()
    series = team_series()
    series = series[series["page"].isin(pages)].copy()
    alias = season_aliases(games)
    for df in (games, series):
        df["team"] = df["team"].map(lambda t: alias.get(t, t))
        df["opponent"] = df["opponent"].map(lambda t: alias.get(t, t))
    used = [raw for raw, shown in alias.items() if shown == team]

    tg, ts = games[games["team"] == team], series[series["team"] == team]

    # 정규 시즌 순위 (매치 승수 → 세트 득실)
    reg = series[series["stage"] == "regular"]
    table = reg.groupby("team").agg(매치승=("win", "sum"), 매치=("win", "size"),
                                    세트승=("score", "sum"), 세트패=("opp_score", "sum"))
    table["매치패"] = table["매치"] - table["매치승"]
    table["세트득실"] = table["세트승"] - table["세트패"]
    table = table.sort_values(["매치승", "세트득실"], ascending=False)
    table.insert(0, "순위", range(1, len(table) + 1))
    standings = table[["순위", "매치승", "매치패", "세트득실"]].reset_index().rename(columns={"team": "팀"})

    # 스플릿별 플레이오프 결과
    playoffs = []
    po = series[series["stage"] == "playoffs"]
    for page in [p for p in pages if p in set(po["page"])]:
        pp = po[po["page"] == page]
        mine = pp[pp["team"] == team]
        sp = pp["split"].iloc[0] or "플레이오프"
        if mine.empty:
            playoffs.append(f"{sp} 진출 못함")
        elif mine.iloc[-1]["match_id"] == pp.iloc[-1]["match_id"]:
            playoffs.append(f"{sp} {'우승' if mine.iloc[-1]['win'] else '준우승'}")
        else:
            playoffs.append(f"{sp} {_tab_ko(mine.iloc[-1]['tab'])} 탈락")

    side = tg.groupby("side")["win"].mean()
    rank = int(table.at[team, "순위"]) if team in table.index else None
    summary = {
        "팀": team + (f" (기간 중 이름: {' → '.join(used)})" if len(used) > 1 else ""),
        "기간": f"{year}년 {split}",
        "매치 전적": f"{int(ts['win'].sum())}승 {int((~ts['win']).sum())}패",
        "세트 전적": f"{int(tg['win'].sum())}승 {int((~tg['win']).sum())}패 (승률 {tg['win'].mean():.0%})",
        "정규 시즌 순위": f"{rank}위 / {len(table)}팀" if rank else "-",
        "플레이오프": " · ".join(playoffs) if playoffs else "-",
        "블루 / 레드 승률": f"{side.get('Blue', float('nan')):.0%} / {side.get('Red', float('nan')):.0%}",
        "평균 경기 시간": f"{tg['gamelength'].mean():.1f}분",
    }

    # 로스터 (출전 기록 기준)
    p = load_players()
    played = p[p["page"].isin(pages) & p["team"].isin(used or [team])]
    roster = []
    for (player, role), df in played.groupby(["player", "role"]):
        kda = (df["kills"].sum() + df["assists"].sum()) / max(df["deaths"].sum(), 1)
        roster.append({"포지션": ROLE_KO.get(role, role), "선수": display_name(player), "경기": len(df),
                       "승률": round(df["win"].mean(), 3), "KDA": round(kda, 2),
                       "_order": ROLE_ORDER.get(role, 9)})
    roster = pd.DataFrame(roster).sort_values(["_order", "경기"], ascending=[True, False]).drop(columns="_order") \
        if roster else pd.DataFrame()

    matches = ts.sort_values("datetime_kst").assign(
        날짜=lambda d: d["datetime_kst"].dt.strftime("%Y-%m-%d"),
        스코어=lambda d: d["score"].astype(int).astype(str) + ":" + d["opp_score"].astype(int).astype(str),
        결과=lambda d: d["win"].map({True: "승", False: "패"}),
        단계=lambda d: d["tab"].map(_tab_ko))[["날짜", "opponent", "스코어", "결과", "단계"]] \
        .rename(columns={"opponent": "상대"})

    ex = champ.explode_champions(tg, "picks")
    champs = ex.groupby("champion").agg(픽=("game_id", "size"), 승률=("win", "mean")).reset_index() \
        .sort_values("픽", ascending=False).head(15)
    champs.insert(1, "이름", champs["champion"].map(champ.name_ko))
    champs["승률"] = champs["승률"].round(3)

    names = lineage_of(team)
    intl = team_series()
    intl = intl[(intl["scope"] == "INTL") & (intl["year"] == year) & intl["team"].isin(names)]
    intl_rows = intl.groupby("league_short").agg(매치승=("win", "sum"), 매치=("win", "size")).reset_index() \
        .rename(columns={"league_short": "대회"})
    if not intl_rows.empty:
        intl_rows["매치패"] = intl_rows["매치"] - intl_rows["매치승"]
        intl_rows = intl_rows[["대회", "매치승", "매치패"]]

    flow = tg.reset_index(drop=True)
    return {
        "kind": "team", "title": f"{team} {year} {split} 팀 리포트", "summary": summary,
        "sections": [("정규 시즌 순위", standings), ("로스터 (출전 기록)", roster), ("매치 결과", matches),
                     ("많이 고른 챔피언", champs.drop(columns="champion")), ("같은 해 국제전", intl_rows)],
        "chart_flow": flow["win"].expanding().mean(),
        "chart_champs": champs.set_index("champion")["픽"].head(10),
    }


def player_report(player: str) -> dict:
    """선수 커리어 리포트 데이터."""
    pg = player_games(include_foreign=True)
    mine = pg[pg["player"] == player].sort_values("datetime_kst")
    total = summarize(mine)
    role = mine["role"].mode().iat[0]
    years = mine["year"].dropna().astype(int)
    summary = {
        "선수": display_name(player),
        "포지션": ROLE_KO.get(role, role),
        "최근 소속": mine.iloc[-1]["team"],
        "활동 기간": f"{years.min()}~{years.max()}년",
        "통산 경기": f"{total['games']}경기 ({total['wins']}승)",
        "통산 승률 / KDA": f"{total['win_rate']:.0%} / {total['kda']:.2f}",
        "킬 관여율": f"{total['kp']:.0%}",
        "국제전 경기": f"{int((mine['scope'] == 'INTL').sum())}경기",
    }
    scope_ko = {"LCK": "LCK", "INTL": "국제전", "FOREIGN": "해외 리그"}
    career = []
    for (y, scope, league, team), df in mine.groupby(["year", "scope", "league_short", "team"]):
        s = summarize(df)
        career.append({"연도": int(y), "구분": scope_ko.get(scope, scope), "리그·대회": league, "팀": team,
                       "경기": s["games"], "승률": round(s["win_rate"], 3), "KDA": round(s["kda"], 2),
                       "킬 관여율": round(s["kp"], 3) if pd.notna(s["kp"]) else None})
    career = pd.DataFrame(career).sort_values(["연도", "구분"])

    pool = mine.groupby("champion").apply(lambda d: pd.Series(summarize(d)), include_groups=False) \
        .sort_values("games", ascending=False).head(15).reset_index()
    champs = pd.DataFrame({"이름": pool["champion"].map(champ.name_ko), "경기": pool["games"].astype(int),
                           "승률": pool["win_rate"].round(3), "KDA": pool["kda"].round(2)})

    clusters, _ = style_clusters()
    own = clusters[clusters["player"] == player].sort_values("year")
    styles = pd.DataFrame({"시즌": own["year"], "팀": own["team"], "플레이 유형": own["style"],
                           "KDA": own["kda"].round(2), "킬 관여율": own["kp"].round(3)})

    trend = mine.groupby("year").apply(lambda d: pd.Series({"kda": summarize(d)["kda"], "win": d["win"].mean()}),
                                       include_groups=False)
    return {
        "kind": "player", "title": f"{display_name(player)} 선수 리포트", "summary": summary,
        "sections": [("시즌별 기록", career), ("많이 쓴 챔피언", champs), ("시즌별 플레이 유형 (LCK, KMeans)", styles)],
        "chart_trend": trend,
        "chart_champs": pool.set_index("champion")["games"].head(10),
    }


# ================================================================== 그래프 (PNG)
def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def charts(data: dict) -> list[tuple[str, io.BytesIO]]:
    """리포트 종류에 맞는 그래프 2개. 그래프 안 글자는 영문·숫자만 쓴다."""
    out = []
    if data["kind"] == "team":
        s = data["chart_flow"]
        fig, ax = plt.subplots(figsize=(7, 2.6))
        ax.plot(range(1, len(s) + 1), s.values * 100, color=GOLD, lw=2)
        ax.axhline(50, color="gray", ls=":", lw=1)
        ax.set_ylim(0, 100)
        ax.set_xlabel("Set #")
        ax.set_ylabel("Cumulative win %")
        ax.grid(alpha=0.2)
        out.append(("시즌 흐름 (세트 누적 승률)", _png(fig)))
    else:
        t = data["chart_trend"]
        fig, ax1 = plt.subplots(figsize=(7, 2.6))
        ax1.plot(t.index, t["kda"], color=GOLD, marker="o", lw=2, label="KDA")
        ax1.set_ylabel("KDA")
        ax2 = ax1.twinx()
        ax2.plot(t.index, t["win"] * 100, color="#3B82F6", marker="s", lw=1.5, label="Win %")
        ax2.set_ylim(0, 100)
        ax2.set_ylabel("Win %")
        ax1.set_xticks(list(t.index))
        ax1.grid(alpha=0.2)
        fig.legend(loc="lower center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False, fontsize=8)
        out.append(("연도별 KDA · 승률", _png(fig)))
    c = data["chart_champs"]
    if not c.empty:
        fig, ax = plt.subplots(figsize=(7, 2.8))
        ax.barh(list(c.index)[::-1], list(c.values)[::-1], color=GOLD)
        ax.set_xlabel("Games picked")
        ax.grid(axis="x", alpha=0.2)
        out.append(("많이 쓴 챔피언 Top 10", _png(fig)))
    return out


# ================================================================== Excel
def to_excel(data: dict) -> bytes:
    """요약 + 섹션마다 시트 1개. 머리글 강조, 열 너비 자동 조정."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(list(data["summary"].items()), columns=["항목", "내용"]).to_excel(
            writer, sheet_name="요약", index=False)
        for name, df in data["sections"]:
            if isinstance(df, pd.DataFrame) and not df.empty:
                df.to_excel(writer, sheet_name=name[:31].replace("/", "·"), index=False)
        for ws in writer.book.worksheets:
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor=GOLD.lstrip("#"))
                cell.alignment = Alignment(horizontal="center")
            for i, col in enumerate(ws.columns, 1):
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[get_column_letter(i)].width = min(max(10, width * 1.6), 60)
                for c in col[1:]:
                    if isinstance(c.value, float) and ws.cell(1, i).value in ("승률", "킬 관여율"):
                        c.number_format = "0.0%"
            ws.freeze_panes = "A2"
    return buf.getvalue()


# ================================================================== PDF
def _fmt(v, col: str) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    if col in ("승률", "킬 관여율") and isinstance(v, float):
        return f"{v:.0%}"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def to_pdf(data: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title=data["title"])
    h1 = ParagraphStyle("h1", fontName=FONT, fontSize=18, leading=24, textColor=colors.HexColor("#111827"))
    h2 = ParagraphStyle("h2", fontName=FONT, fontSize=12, leading=18, spaceBefore=10, spaceAfter=4,
                        textColor=colors.HexColor(GOLD))
    small = ParagraphStyle("small", fontName=FONT, fontSize=8, leading=11, textColor=colors.gray)
    cell = ParagraphStyle("cell", fontName=FONT, fontSize=8, leading=10)

    def table(df: pd.DataFrame, max_rows: int = 40):
        df = df.head(max_rows)
        rows = [[Paragraph(str(c), cell) for c in df.columns]]
        rows += [[Paragraph(_fmt(v, c), cell) for v, c in zip(r, df.columns)] for r in df.itertuples(index=False)]
        t = Table(rows, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GOLD)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAF7")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    story = [Paragraph(data["title"], h1),
             Paragraph(f"LCK Insight · 생성 {datetime.now():%Y-%m-%d %H:%M}", small), Spacer(1, 6)]
    story += [Paragraph("요약", h2), table(pd.DataFrame(list(data["summary"].items()), columns=["항목", "내용"]))]
    for title, png in charts(data):
        story += [Paragraph(title, h2), Image(png, width=170 * mm, height=62 * mm)]
    for name, df in data["sections"]:
        if isinstance(df, pd.DataFrame) and not df.empty:
            story += [Paragraph(name, h2), table(df)]
    story += [Spacer(1, 10), Paragraph("데이터 출처: Leaguepedia (CC BY-SA 3.0), Riot Games Data Dragon. "
                                       "Riot Games와 관련 없는 개인 학습용 프로젝트입니다.", small)]
    doc.build(story)
    return buf.getvalue()
