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

st.title("📅 경기 일정")
st.caption("LCK와 국제 대회(Worlds, MSI, First Stand, EWC) 경기를 캘린더로 보여줍니다. "
           "지난 경기는 세트 스코어가, 예정 경기는 시작 시간(한국 시간)이 표시됩니다. "
           "경기를 누르면 아래에 세트별 결과가 나옵니다.")

if not has_data():
    st.warning("아직 수집된 데이터가 없습니다.")
    st.stop()

sched = load_schedule().dropna(subset=["datetime_kst"]).sort_values("datetime_kst")
info = team_info()


def short(team: str) -> str:
    if team in info.index and isinstance(info.at[team, "short"], str):
        return info.at[team, "short"]
    return team


def logo(team: str) -> str | None:
    return info.at[team, "logo"] if team in info.index else None


def tab_ko(tab: str) -> str:
    if tab in TAB_KO:
        return TAB_KO[tab]
    return tab.replace("Round ", "") + "라운드" if str(tab).startswith("Round ") else tab


# ------------------------------------------------------------------ 필터
c1, c2 = st.columns([3, 2])
leagues = c1.multiselect("대회", list(LEAGUE_COLOR), default=list(LEAGUE_COLOR))
all_teams = sorted(set(sched["team1"].dropna()) | set(sched["team2"].dropna()))
team_filter = c2.selectbox("팀 (선택하면 그 팀 경기만)", all_teams, index=None, placeholder="전체 팀")

view = sched[sched["league_short"].isin(leagues)]
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

m = st.columns(3)
m[0].metric("표시 중인 경기", f"{len(view):,}", border=True)
m[1].metric("예정 경기", f"{len(upcoming)}", border=True)
m[2].metric("가장 최근 경기", view.loc[view["winner"].notna(), "datetime_kst"].max().strftime("%Y-%m-%d"),
            border=True)
if upcoming.empty:
    st.caption("현재 등록된 예정 경기가 없습니다 (비시즌). 새 시즌 일정이 발표되면 매일 자동 업데이트로 추가됩니다.")


# ------------------------------------------------------------------ 캘린더
def event_title(r) -> str:
    a, b = short(r.team1), short(r.team2)
    if pd.notna(r.winner):
        return f"{a} {int(r.team1_score)}:{int(r.team2_score)} {b}"
    return f"{r.datetime_kst:%H:%M} {a} vs {b}"


events = [{
    "id": r.match_id,
    "title": event_title(r),
    "start": r.datetime_kst.strftime("%Y-%m-%dT%H:%M:%S"),
    "end": (r.datetime_kst + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
    "backgroundColor": LEAGUE_COLOR.get(r.league_short, "#6B7280"),
    "borderColor": LEAGUE_COLOR.get(r.league_short, "#6B7280"),
} for r in view.itertuples()]

options = {
    "initialView": "dayGridMonth",
    "initialDate": start_at.strftime("%Y-%m-%d"),
    "locale": "ko",
    "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,listMonth"},
    "buttonText": {"today": "오늘", "month": "달력", "list": "목록"},
    "dayMaxEvents": 4,
    "displayEventTime": False,
    "eventDisplay": "block",          # 시간 있는 경기도 점(•)이 아닌 색 블록으로 표시
    "height": 650,
}
custom_css = (".fc-event-title { font-size: 0.72rem; font-weight: 600; white-space: normal; }"
              " .fc-daygrid-event { cursor: pointer; }")

st.markdown(" ".join(f"<span style='background:{c};color:white;padding:2px 8px;border-radius:6px;"
                     f"font-size:0.8rem'>{name}</span>" for name, c in LEAGUE_COLOR.items()),
            unsafe_allow_html=True)

selected = None
try:
    from streamlit_calendar import calendar
    state = calendar(events=events, options=options, custom_css=custom_css,
                     callbacks=["eventClick"], key=f"cal_{'-'.join(leagues)}_{team_filter}")
    if isinstance(state, dict) and state.get("callback") == "eventClick":
        selected = state["eventClick"]["event"]["id"]
        st.session_state["schedule_match"] = selected
except Exception as exc:  # 캘린더 컴포넌트를 못 쓰는 환경이면 목록으로 대체
    st.warning(f"캘린더를 표시하지 못해 목록으로 보여줍니다. ({exc})")

with st.expander("📋 목록에서 경기 고르기 / 📥 내 캘린더에 추가"):
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
st.divider()
h = st.columns([1, 3, 2, 3, 1])
for col, team in [(h[0], match["team1"]), (h[4], match["team2"])]:
    if logo(team):
        col.image(logo(team), width=60)
h[1].markdown(f"<h3 style='text-align:right'>{match['team1']}</h3>", unsafe_allow_html=True)
h[3].markdown(f"<h3>{match['team2']}</h3>", unsafe_allow_html=True)
score = f"{int(match['team1_score'])} : {int(match['team2_score'])}" if pd.notna(match["winner"]) else "vs"
h[2].markdown(f"<h2 style='text-align:center'>{score}</h2>", unsafe_allow_html=True)
st.caption(f"{match['datetime_kst']:%Y-%m-%d %H:%M} (한국 시간) · {match['tournament']} · "
           f"{tab_ko(match['tab'])} · {int(match['best_of']) if pd.notna(match['best_of']) else '-'}판"
           f"{int(match['best_of']) // 2 + 1 if pd.notna(match['best_of']) else ''}선승")

games = load_games()
sets = games[games["match_id"] == match_id].sort_values("game_in_match")


def icons(picks: str, size: int = 30) -> str:
    out = []
    for name in [c.strip() for c in str(picks).split(",") if c.strip() and c.strip() != "None"]:
        url = champ.icon(name)
        alt = champ.name_ko(name)
        out.append(f"<img src='{url}' width='{size}' title='{alt}' style='border-radius:4px;margin:1px'>"
                   if url else f"<span title='{alt}'>{alt}</span>")
    return "".join(out)


if pd.notna(match["winner"]) and not sets.empty:
    players = load_players()
    for g in sets.itertuples():
        win1 = g.win_team == g.team1
        with st.container(border=True):
            st.markdown(f"**{int(g.game_in_match)}세트** · {g.gamelength:.0f}분 · 패치 {g.patch} · "
                        f"승리: **{g.win_team}**")
            left, right = st.columns(2)
            for col, team, picks, bans, kills, won, side in [
                    (left, g.team1, g.team1_picks, g.team1_bans, g.team1_kills, win1, "🔵 블루"),
                    (right, g.team2, g.team2_picks, g.team2_bans, g.team2_kills, not win1, "🔴 레드")]:
                col.markdown(f"{side} · **{team}** {'🏆' if won else ''} · {int(kills) if pd.notna(kills) else '-'}킬",
                             unsafe_allow_html=True)
                col.markdown(f"픽 {icons(picks)}", unsafe_allow_html=True)
                col.markdown(f"<span style='opacity:0.6'>밴 {icons(bans, 22)}</span>", unsafe_allow_html=True)
            with st.expander("선수 기록"):
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
elif pd.notna(match["winner"]):
    st.info("이 경기의 세트별 기록은 수집되지 않았습니다.")
else:
    # 예정 경기 미리보기: 상대 전적과 최근 흐름
    st.markdown("**경기 미리보기**")
    ser = team_series()
    a_names, b_names = lineage_of(match["team1"]), lineage_of(match["team2"])
    h2h = ser[ser["team"].isin(a_names) & ser["opponent"].isin(b_names)]
    c = st.columns(3)
    c[0].metric(f"{short(match['team1'])} 상대 전적", f"{int(h2h['win'].sum())}승 {int((~h2h['win']).sum())}패",
                border=True)
    for col, names, team in [(c[1], a_names, match["team1"]), (c[2], b_names, match["team2"])]:
        recent10 = ser[ser["team"].isin(names)].tail(10)
        col.metric(f"{short(team)} 최근 10매치", f"{int(recent10['win'].sum())}승 {int((~recent10['win']).sum())}패",
                   border=True)
    from utils.model import predict, series_prob
    p, _ = predict(match["team1"], match["team2"], a_blue=True)
    p = (p + 1 - predict(match["team2"], match["team1"], a_blue=True)[0]) / 2   # 진영 미정 → 양쪽 평균
    bo = int(match["best_of"]) if pd.notna(match["best_of"]) else 1
    st.metric(f"예상 승률 ({short(match['team1'])} 기준, 승부 예측 모델)",
              f"{(series_prob(p, bo) if bo > 1 else p):.0%}",
              f"세트 승률 {p:.0%} · {bo}판 기준" if bo > 1 else None, delta_color="off", delta_arrow="off",
              border=True)
