"""📅 경기 일정: 월간 캘린더로 지난 경기 스코어와 예정 경기를 보고, 경기를 눌러 세트별 결과를 확인한다."""
from datetime import timedelta

import pandas as pd
import streamlit as st

from utils import champions as champ
from utils.data_loader import has_data, load_games, load_players, load_schedule
from utils.teams import display_name, lineage_of, team_info, team_series

LEAGUE_COLOR = {"LCK": "#C89B3C", "Worlds": "#2563EB", "MSI": "#7C3AED",
                "First Stand": "#0891B2", "EWC": "#16A34A"}
TAB_KO = {"Finals": "결승", "Semifinals": "준결승", "Quarterfinals": "8강"}
GOLD = "#C89B3C"

st.title("📅 경기 일정")
st.caption("LCK와 국제 대회 경기를 캘린더로 보여줍니다. 지난 경기는 세트 스코어, 예정 경기는 시작 시간(한국 시간)이 "
           "표시되고, 경기를 누르면 아래에 세트별 결과가 나옵니다.")

if not has_data():
    st.warning("아직 수집된 데이터가 없습니다.")
    st.stop()

sched = load_schedule().dropna(subset=["datetime_kst"]).sort_values("datetime_kst")
info = team_info()


def short(team: str) -> str:
    if team in info.index and isinstance(info.at[team, "short"], str):
        return info.at[team, "short"]
    return display_name(team)        # 'LYON (2024 American Team)' → 'LYON'


def logo(team: str) -> str | None:
    return info.at[team, "logo"] if team in info.index else None


def tab_ko(tab: str) -> str:
    if tab in TAB_KO:
        return TAB_KO[tab]
    return tab.replace("Round ", "") + "라운드" if str(tab).startswith("Round ") else tab


# ------------------------------------------------------------------ 필터
with st.container(border=True):
    c1, c2 = st.columns([3, 2])
    leagues = c1.pills("대회", list(LEAGUE_COLOR), selection_mode="multi", default=list(LEAGUE_COLOR))
    all_teams = sorted(set(sched["team1"].dropna()) | set(sched["team2"].dropna()))
    team_filter = c2.selectbox("팀", all_teams, index=None, placeholder="전체 팀 (선택하면 그 팀 경기만)")

view = sched[sched["league_short"].isin(leagues or [])]
if team_filter:
    names = lineage_of(team_filter)          # 이름이 바뀐 시기의 경기도 함께
    view = view[view["team1"].isin(names) | view["team2"].isin(names)]

now = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None)
upcoming = view[view["winner"].isna() & (view["datetime_kst"] >= now - timedelta(hours=6))]
if view.empty:
    st.info("조건에 맞는 경기가 없습니다.")
    st.stop()
# 처음 열 달: 예정 경기가 있으면 가장 가까운 예정 경기, 없으면 가장 최근 경기
start_at = upcoming["datetime_kst"].min() if not upcoming.empty else view["datetime_kst"].max()
latest = view.loc[view["winner"].notna(), "datetime_kst"].max()
status = (f"표시 중 <b>{len(view):,}</b>경기 · 예정 <b>{len(upcoming)}</b>경기 · "
          f"가장 최근 경기 <b>{latest:%Y.%m.%d}</b>")
legend = "".join(f"<span style='display:inline-flex;align-items:center;gap:4px;margin-left:12px'>"
                 f"<span style='width:10px;height:10px;border-radius:3px;background:{c}'></span>{n}</span>"
                 for n, c in LEAGUE_COLOR.items() if n in (leagues or []))
st.markdown(f"<div style='display:flex;flex-wrap:wrap;justify-content:space-between;font-size:0.85rem;"
            f"opacity:0.85;margin:4px 0 8px'><span>{status}</span><span>{legend}</span></div>",
            unsafe_allow_html=True)
if upcoming.empty:
    st.caption("현재 등록된 예정 경기가 없습니다 (비시즌). 새 시즌 일정이 발표되면 매일 자동 업데이트로 추가됩니다.")


# ------------------------------------------------------------------ 캘린더
def event_title(r) -> str:
    a, b = short(r.team1), short(r.team2)
    if pd.notna(r.winner):
        return f"{a} {int(r.team1_score)}:{int(r.team2_score)} {b}"
    return f"{r.datetime_kst:%H:%M} {a} vs {b}"


def day_end(t: pd.Timestamp) -> pd.Timestamp:
    """경기 표시 끝 시간: 시작 1시간 뒤, 단 시작한 날을 넘기지 않는다 (밤 경기도 하루에만 표시)."""
    return min(t + timedelta(hours=1), t.normalize() + timedelta(hours=23, minutes=59))


events = [{
    "id": r.match_id,
    "title": event_title(r),
    "start": r.datetime_kst.strftime("%Y-%m-%dT%H:%M:%S"),
    "end": day_end(r.datetime_kst).strftime("%Y-%m-%dT%H:%M:%S"),
    "backgroundColor": LEAGUE_COLOR.get(r.league_short, "#6B7280") + "1F",   # 대회 색을 옅게
    "borderColor": LEAGUE_COLOR.get(r.league_short, "#6B7280"),
    "textColor": "#1F2937",
} for r in view.itertuples()]

options = {
    "initialView": "dayGridMonth",
    "initialDate": start_at.strftime("%Y-%m-%d"),
    "locale": "ko",
    "headerToolbar": {"left": "title", "center": "", "right": "today prev,next dayGridMonth,listMonth"},
    "buttonText": {"today": "오늘", "month": "달력", "list": "목록"},
    "dayMaxEvents": 3,
    "displayEventTime": False,
    "eventDisplay": "block",
    "nextDayThreshold": "23:59:59",   # 자정을 넘기는 경기도 시작한 날에만 표시
    "fixedWeekCount": False,
    "height": 620,
}
custom_css = f"""
    .fc {{ font-family: inherit; }}
    .fc .fc-toolbar-title {{ font-size: 1.15rem; font-weight: 700; color: #111827; }}
    .fc .fc-button {{ background: #fff; border: 1px solid #E5E7EB; color: #374151; font-size: 0.8rem;
                      padding: 4px 10px; box-shadow: none; text-transform: none; }}
    .fc .fc-button:hover {{ background: #F9FAFB; color: #111827; border-color: #D1D5DB; }}
    .fc .fc-button-primary:not(:disabled).fc-button-active,
    .fc .fc-button-primary:not(:disabled):active {{ background: {GOLD}; border-color: {GOLD}; color: #fff; }}
    .fc .fc-button:focus {{ box-shadow: none; }}
    .fc-theme-standard td, .fc-theme-standard th, .fc-theme-standard .fc-scrollgrid {{ border-color: #F1F1F1; }}
    .fc .fc-col-header-cell-cushion {{ font-size: 0.78rem; color: #6B7280; font-weight: 600; padding: 6px 0; }}
    .fc .fc-day-sun .fc-col-header-cell-cushion, .fc .fc-day-sun .fc-daygrid-day-number {{ color: #DC2626; }}
    .fc .fc-day-sat .fc-col-header-cell-cushion, .fc .fc-day-sat .fc-daygrid-day-number {{ color: #2563EB; }}
    .fc .fc-daygrid-day-number {{ font-size: 0.75rem; color: #6B7280; padding: 4px 6px; }}
    .fc .fc-day-today {{ background: rgba(200,155,60,0.08) !important; }}
    .fc .fc-day-other .fc-daygrid-day-number {{ opacity: 0.35; }}
    .fc .fc-daygrid-block-event {{ border-width: 0 0 0 3px; border-radius: 5px; margin: 1px 3px; }}
    .fc .fc-event-main {{ padding: 1px 5px; }}
    .fc .fc-event-title {{ font-size: 0.7rem; font-weight: 600; white-space: nowrap; overflow: hidden;
                           text-overflow: ellipsis; }}
    .fc .fc-daygrid-event {{ cursor: pointer; }}
    .fc .fc-daygrid-event:hover {{ filter: brightness(0.95); }}
    .fc .fc-daygrid-more-link {{ font-size: 0.7rem; color: #6B7280; }}
    .fc .fc-list-event:hover td {{ background: #F9FAFB; cursor: pointer; }}
"""

try:
    from streamlit_calendar import calendar
    state = calendar(events=events, options=options, custom_css=custom_css,
                     callbacks=["eventClick"], key=f"cal_{'-'.join(leagues or [])}_{team_filter}")
    if isinstance(state, dict) and state.get("callback") == "eventClick":
        st.session_state["schedule_match"] = state["eventClick"]["event"]["id"]
except Exception as exc:  # 캘린더 컴포넌트를 못 쓰는 환경이면 목록으로 대체
    st.warning(f"캘린더를 표시하지 못해 목록으로 보여줍니다. ({exc})")

with st.expander("📋 목록에서 경기 고르기 · 📥 내 캘린더에 추가"):
    recent = view.sort_values("datetime_kst", ascending=False).head(300)
    labels = {r.match_id: f"{r.datetime_kst:%Y-%m-%d} · {r.league_short} · {event_title(r)}"
              for r in recent.itertuples()}
    pick = st.selectbox("경기", list(labels), index=None, placeholder="경기를 선택하세요 (최근 300경기)",
                        format_func=labels.get)
    if pick:
        st.session_state["schedule_match"] = pick

    def to_ics(df: pd.DataFrame) -> str:
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//LCK Insight//KO"]
        for r in df.itertuples():
            start = (r.datetime_kst - timedelta(hours=9)).strftime("%Y%m%dT%H%M%SZ")   # KST → UTC
            end = (r.datetime_kst + timedelta(hours=-9 + 2)).strftime("%Y%m%dT%H%M%SZ")
            lines += ["BEGIN:VEVENT", f"UID:{abs(hash(r.match_id))}@lck-insight",
                      f"DTSTART:{start}", f"DTEND:{end}",
                      f"SUMMARY:[{r.league_short}] {r.team1} vs {r.team2}",
                      f"DESCRIPTION:{r.tournament} {r.tab}", "END:VEVENT"]
        return "\r\n".join(lines + ["END:VCALENDAR"])

    if upcoming.empty:
        st.caption("📥 예정 경기가 등록되면 선택한 대회·팀의 일정을 .ics 파일로 내려받아 "
                   "구글·애플 캘린더에 추가할 수 있습니다.")
    else:
        st.download_button(f"📥 예정 경기 {len(upcoming)}개를 캘린더 파일(.ics)로 받기", to_ics(upcoming),
                           file_name="lck_schedule.ics", mime="text/calendar")

# ------------------------------------------------------------------ 경기 상세
match_id = st.session_state.get("schedule_match")
if match_id is None or match_id not in set(sched["match_id"]):
    st.info("👆 캘린더나 목록에서 경기를 누르면 세트별 결과가 여기에 나타납니다.")
    st.stop()

match = sched[sched["match_id"] == match_id].iloc[0]
played = pd.notna(match["winner"])
color = LEAGUE_COLOR.get(match["league_short"], "#6B7280")


def team_block(team: str, won: bool | None, align: str) -> str:
    img = f"<img src='{logo(team)}' style='width:56px;height:56px;object-fit:contain'>" if logo(team) else ""
    weight, opacity = ("800", "1") if won in (True, None) else ("500", "0.55")
    return (f"<div style='flex:1;display:flex;flex-direction:column;align-items:{align};gap:6px;opacity:{opacity}'>"
            f"{img}<span style='font-size:1.05rem;font-weight:{weight}'>{display_name(team)}</span></div>")


if played:
    s1, s2 = int(match["team1_score"]), int(match["team2_score"])
    w1 = match["winner"] == 1
    score_html = (f"<span style='color:{GOLD if w1 else '#9CA3AF'}'>{s1}</span>"
                  f"<span style='opacity:0.4;margin:0 10px'>:</span>"
                  f"<span style='color:{GOLD if not w1 else '#9CA3AF'}'>{s2}</span>")
else:
    w1 = None
    score_html = f"<span style='opacity:0.6;font-size:1.4rem'>{match['datetime_kst']:%H:%M}</span>"
bo = int(match["best_of"]) if pd.notna(match["best_of"]) else None
weekday = "월화수목금토일"[match["datetime_kst"].weekday()]
chips = [f"{match['datetime_kst']:%Y.%m.%d} ({weekday}) {match['datetime_kst']:%H:%M}",
         match["tournament"], tab_ko(match["tab"])]
if bo:
    chips.append(f"{bo}판 {bo // 2 + 1}선승")
if isinstance(match.get("mvp"), str) and match["mvp"]:
    chips.append(f"🏅 MVP {display_name(match['mvp'])}")
chip_html = "".join(f"<span style='font-size:0.75rem;padding:2px 8px;border-radius:999px;"
                    f"background:rgba(128,128,128,0.12);margin:0 3px'>{c}</span>" for c in chips)
st.markdown(
    f"<div style='border:1px solid rgba(128,128,128,0.2);border-top:4px solid {color};border-radius:12px;"
    f"padding:18px 20px;margin:12px 0'>"
    f"<div style='display:flex;align-items:center;justify-content:space-between'>"
    f"{team_block(match['team1'], None if w1 is None else w1, 'center')}"
    f"<div style='font-size:2.4rem;font-weight:800;min-width:140px;text-align:center'>{score_html}</div>"
    f"{team_block(match['team2'], None if w1 is None else not w1, 'center')}</div>"
    f"<div style='text-align:center;margin-top:12px'>{chip_html}</div></div>",
    unsafe_allow_html=True)

games = load_games()
sets = games[games["match_id"] == match_id].sort_values("game_in_match")


def icons(picks: str, size: int = 30, faded: bool = False) -> str:
    out = []
    for name in [c.strip() for c in str(picks).split(",") if c.strip() and c.strip() != "None"]:
        url, alt = champ.icon(name), champ.name_ko(name)
        style = f"width:{size}px;height:{size}px;border-radius:6px;margin-right:3px;" + \
            ("filter:grayscale(80%);opacity:0.6" if faded else "")
        out.append(f"<img src='{url}' title='{alt}' style='{style}'>" if url else f"<span title='{alt}'>{alt}</span>")
    return "".join(out)


if played and not sets.empty:
    players = load_players()
    for g in sets.itertuples():
        win1 = g.win_team == g.team1
        rows = ""
        for team, picks, bans, kills, won, side_color in [
                (g.team1, g.team1_picks, g.team1_bans, g.team1_kills, win1, "#3B82F6"),
                (g.team2, g.team2_picks, g.team2_bans, g.team2_kills, not win1, "#EF4444")]:
            badge = (f"<span style='font-size:0.7rem;font-weight:700;color:#fff;background:{GOLD};"
                     f"padding:1px 7px;border-radius:999px;margin-left:6px'>WIN</span>" if won else "")
            rows += (f"<div style='display:flex;align-items:center;gap:12px;padding:8px 10px;border-radius:8px;"
                     f"background:{'rgba(200,155,60,0.08)' if won else 'transparent'}'>"
                     f"<div style='width:150px;display:flex;align-items:center;gap:6px'>"
                     f"<span style='width:8px;height:8px;border-radius:50%;background:{side_color}'></span>"
                     f"<b>{short(team)}</b>{badge}</div>"
                     f"<div style='width:52px;font-size:0.85rem;opacity:0.8'>"
                     f"{int(kills) if pd.notna(kills) else '-'}킬</div>"
                     f"<div style='flex:1'>{icons(picks)}</div>"
                     f"<div style='opacity:0.9'>{icons(bans, 20, faded=True)}</div></div>")
        st.markdown(
            f"<div style='border:1px solid rgba(128,128,128,0.2);border-radius:10px;padding:10px 12px 8px;"
            f"margin-top:10px'><div style='display:flex;justify-content:space-between;font-size:0.85rem;"
            f"margin:0 4px 6px'><b>{int(g.game_in_match)}세트</b><span style='opacity:0.6'>"
            f"{g.gamelength:.0f}분 · 패치 {g.patch} · 🔵 블루 / 🔴 레드 · 오른쪽 흐린 아이콘은 밴</span></div>"
            f"{rows}</div>", unsafe_allow_html=True)
        with st.expander(f"{int(g.game_in_match)}세트 선수 기록"):
            ps = players[players["game_id"] == g.game_id].copy()
            ps["아이콘"] = ps["champion"].map(champ.icon)
            ps["선수"] = ps["player"].map(display_name)
            ps["챔피언"] = ps["champion"].map(champ.name_ko)
            ps["K/D/A"] = ps[["kills", "deaths", "assists"]].astype("Int64").astype(str).agg("/".join, axis=1)
            st.dataframe(ps[["team", "role", "선수", "아이콘", "챔피언", "K/D/A", "cs", "gold", "damage"]]
                         .rename(columns={"team": "팀", "role": "포지션", "cs": "CS", "gold": "골드",
                                          "damage": "딜량"}),
                         hide_index=True, width="stretch",
                         column_config={"아이콘": st.column_config.ImageColumn(width="small")})
elif played:
    st.info("이 경기의 세트별 기록은 수집되지 않았습니다.")
else:
    # 예정 경기 미리보기: 상대 전적, 최근 흐름, 예상 승률
    ser = team_series()
    a_names, b_names = lineage_of(match["team1"]), lineage_of(match["team2"])
    h2h = ser[ser["team"].isin(a_names) & ser["opponent"].isin(b_names)]
    from utils.model import predict, series_prob
    p, _ = predict(match["team1"], match["team2"], a_blue=True)
    p = (p + 1 - predict(match["team2"], match["team1"], a_blue=True)[0]) / 2   # 진영 미정 → 양쪽 평균
    c = st.columns(4)
    c[0].metric(f"{short(match['team1'])} 예상 승률", f"{(series_prob(p, bo) if bo and bo > 1 else p):.0%}",
                f"세트 {p:.0%}" if bo and bo > 1 else None, delta_color="off", delta_arrow="off", border=True)
    c[1].metric("상대 전적", f"{int(h2h['win'].sum())}승 {int((~h2h['win']).sum())}패", border=True)
    for col, names, team in [(c[2], a_names, match["team1"]), (c[3], b_names, match["team2"])]:
        recent10 = ser[ser["team"].isin(names)].tail(10)
        col.metric(f"{short(team)} 최근 10매치", f"{int(recent10['win'].sum())}승 {int((~recent10['win']).sum())}패",
                   border=True)
    st.caption("예상 승률은 승부 예측 페이지의 모델로 계산했습니다 (진영 미정이라 양쪽 진영의 평균).")
