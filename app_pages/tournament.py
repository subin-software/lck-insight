"""🏆 대회 정보: 대회를 고르면 최종 순위, 우승팀, 결승과 MVP, 대회 기록 상위 선수, 메타, 단계별 결과를 보여준다."""
import pandas as pd
import streamlit as st

from utils import champions as champ
from utils.data_loader import has_data, load_players
from utils.meta import champion_table
from utils.teams import display_name, team_games, team_info
from utils.tournaments import INTL_ORDER, event_schedule, events, official_results

GOLD, SILVER, BRONZE = "#C89B3C", "#9CA3AF", "#B45309"
TAB_KO = {"Finals": "결승", "Semifinals": "준결승", "Quarterfinals": "8강"}

st.title("🏆 대회 정보")
st.caption("대회를 고르면 최종 순위와 우승팀, 결승전과 MVP, 대회 기록 상위 선수, 많이 쓰인 챔피언, "
           "단계별 경기 결과를 한 화면에서 볼 수 있습니다.")

if not has_data():
    st.warning("아직 수집된 데이터가 없습니다.")
    st.stop()

ev = events()
info = team_info()


def logo(team: str, size: int = 28) -> str:
    url = info.at[team, "logo"] if team in info.index else None
    return f"<img src='{url}' style='width:{size}px;height:{size}px;object-fit:contain'>" if url else ""


def tab_ko(tab: str) -> str:
    if tab in TAB_KO:
        return TAB_KO[tab]
    return str(tab).replace("Round ", "") + "라운드" if str(tab).startswith("Round ") else tab


# ------------------------------------------------------------------ 선택
c1, c2, c3 = st.columns([2, 1, 2])
leagues = ["LCK"] + INTL_ORDER
league = c1.pills("대회 종류", leagues, default="LCK", selection_mode="single") or "LCK"
sub = ev[ev["league"] == league]
year = c2.selectbox("연도", sorted(sub["year"].unique(), reverse=True), format_func=lambda y: f"{y}년")
sub = sub[sub["year"] == year]
key = c3.selectbox("대회", list(sub["event_key"]), format_func=lambda k: sub.set_index("event_key").at[k, "name"],
                   disabled=len(sub) == 1)
event = sub.set_index("event_key").loc[key]
pages = tuple(event["pages"])

sched = event_schedule(pages)
played = sched[sched["winner"].notna()]
tg = team_games()
eg = tg[tg["page"].isin(pages)]
results = official_results(pages)

if played.empty:
    st.info("이 대회는 아직 치러진 경기가 없습니다.")
    st.stop()

# ------------------------------------------------------------------ 개요
final = played.iloc[-1]
champion = final["team1"] if final["winner"] == 1 else final["team2"]
runner_up = final["team2"] if final["winner"] == 1 else final["team1"]
prize_total = results["prize"].sum() if not results.empty else 0
teams_n = eg["team"].nunique()

st.markdown(
    f"<div style='border:1px solid rgba(128,128,128,0.2);border-top:4px solid {GOLD};border-radius:12px;"
    f"padding:16px 20px;margin:8px 0 12px'>"
    f"<div style='font-size:1.5rem;font-weight:800'>{event['name']}</div>"
    f"<div style='opacity:0.7;font-size:0.9rem;margin-top:2px'>"
    f"{event['start']:%Y.%m.%d} ~ {played['datetime_kst'].max():%Y.%m.%d} · 참가 {teams_n}팀 · "
    f"{len(played)}매치 {eg['game_id'].nunique()}세트"
    + (f" · 총상금 ${prize_total:,.0f}" if prize_total else "") + "</div>"
    f"<div style='display:flex;align-items:center;gap:10px;margin-top:12px'>{logo(champion, 48)}"
    f"<div><div style='font-size:0.8rem;opacity:0.7'>🏆 우승</div>"
    f"<div style='font-size:1.3rem;font-weight:800'>{champion}</div></div></div></div>",
    unsafe_allow_html=True)

tab_rank, tab_final, tab_stats, tab_matches = st.tabs(["🥇 최종 순위", "🎯 결승 · MVP", "📊 대회 기록", "📋 경기 결과"])

# ------------------------------------------------------------------ 최종 순위
with tab_rank:
    if results.empty:
        # 공식 순위가 없으면 결승 결과로 1·2위만 표시
        results = pd.DataFrame({"place": ["1", "2"], "place_number": [1, 2], "team": [champion, runner_up],
                                "prize": [None, None]})
        st.caption("공식 최종 순위 기록이 없어 결승 결과로 1·2위만 표시합니다.")
    podium = results[results["place_number"] <= 4].drop_duplicates("team").head(4)
    cols = st.columns(len(podium)) if len(podium) else []
    medal = {1: ("🥇", GOLD), 2: ("🥈", SILVER), 3: ("🥉", BRONZE)}
    for col, r in zip(cols, podium.itertuples()):
        icon, color = medal.get(int(r.place_number), ("🏅", BRONZE))
        prize = f"${r.prize:,.0f}" if pd.notna(r.prize) else ""
        col.markdown(
            f"<div style='text-align:center;border:1px solid rgba(128,128,128,0.2);border-top:3px solid {color};"
            f"border-radius:10px;padding:12px 6px'>{logo(r.team, 52)}"
            f"<div style='font-size:0.85rem;margin-top:6px'>{icon} {r.place}위</div>"
            f"<div style='font-weight:800'>{r.team}</div>"
            f"<div style='font-size:0.8rem;opacity:0.7'>{prize}</div></div>", unsafe_allow_html=True)

    rec = eg.groupby("team").agg(세트승=("win", "sum"), 세트=("win", "size"))
    ser = sched[sched["winner"].notna()]
    match_w = pd.concat([ser.loc[ser["winner"] == 1, "team1"], ser.loc[ser["winner"] == 2, "team2"]]).value_counts()
    match_n = pd.concat([ser["team1"], ser["team2"]]).value_counts()
    full = results.drop_duplicates("team").copy()
    full["로고"] = full["team"].map(lambda t: info.at[t, "logo"] if t in info.index else None)
    full["매치"] = full["team"].map(lambda t: f"{match_w.get(t, 0)}승 {match_n.get(t, 0) - match_w.get(t, 0)}패")
    full["세트 승률"] = full["team"].map(lambda t: rec.at[t, "세트승"] / rec.at[t, "세트"] if t in rec.index else None)
    full["지역"] = full["team"].map(lambda t: info.at[t, "region"] if t in info.index else "")
    st.markdown("**전체 순위**")
    st.dataframe(full[["place", "로고", "team", "지역", "매치", "세트 승률", "prize"]]
                 .rename(columns={"place": "순위", "team": "팀", "prize": "상금($)"}),
                 hide_index=True, width="stretch", column_config={
                     "로고": st.column_config.ImageColumn(width="small"),
                     "세트 승률": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                     "상금($)": st.column_config.NumberColumn(format="$%d")})
    st.caption("순위·상금은 Leaguepedia 공식 대회 결과 기준입니다 (공동 순위는 '5-8'처럼 표시).")

# ------------------------------------------------------------------ 결승 · MVP
with tab_final:
    s1, s2 = int(final["team1_score"]), int(final["team2_score"])
    w1 = final["winner"] == 1
    mvp = final.get("mvp")
    st.markdown(
        f"<div style='display:flex;align-items:center;justify-content:center;gap:24px;padding:16px;"
        f"border:1px solid rgba(128,128,128,0.2);border-radius:12px'>"
        f"<div style='text-align:center;opacity:{1 if w1 else 0.55}'>{logo(final['team1'], 56)}"
        f"<div style='font-weight:700'>{final['team1']}</div></div>"
        f"<div style='font-size:2.4rem;font-weight:800'><span style='color:{GOLD if w1 else SILVER}'>{s1}</span>"
        f"<span style='opacity:0.4'> : </span><span style='color:{GOLD if not w1 else SILVER}'>{s2}</span></div>"
        f"<div style='text-align:center;opacity:{1 if not w1 else 0.55}'>{logo(final['team2'], 56)}"
        f"<div style='font-weight:700'>{final['team2']}</div></div></div>"
        f"<div style='text-align:center;opacity:0.7;font-size:0.85rem;margin-top:6px'>"
        f"{final['datetime_kst']:%Y.%m.%d %H:%M} (한국 시간) · {tab_ko(final['tab'])}</div>",
        unsafe_allow_html=True)
    if isinstance(mvp, str) and mvp:
        st.success(f"🏅 결승 MVP: **{display_name(mvp)}**")
    mvps = sched["mvp"].dropna() if "mvp" in sched else pd.Series(dtype=str)
    if not mvps.empty:
        top = mvps.map(display_name).value_counts().head(10).rename_axis("선수").reset_index(name="MVP 횟수")
        st.markdown("**이 대회 MVP 횟수 순위** (매치마다 선정된 MVP 기준)")
        st.dataframe(top, hide_index=True, width="stretch")
    else:
        st.caption("이 대회의 경기 MVP 기록이 없습니다.")

# ------------------------------------------------------------------ 대회 기록
with tab_stats:
    p = load_players()
    p = p[p["page"].isin(pages)]
    min_games = max(3, int(p.groupby("player").size().median() // 2)) if not p.empty else 3
    agg = p.groupby("player").agg(팀=("team", "last"), 포지션=("role", lambda s: s.mode().iat[0]),
                                  경기=("game_id", "nunique"), 킬=("kills", "sum"), 데스=("deaths", "sum"),
                                  어시=("assists", "sum"), 승=("win", "sum"))
    agg = agg[agg["경기"] >= min_games]
    agg["KDA"] = (agg["킬"] + agg["어시"]) / agg["데스"].clip(lower=1)
    agg.index = agg.index.map(display_name)
    a, b = st.columns(2)
    a.markdown(f"**KDA 상위 선수** ({min_games}경기 이상)")
    a.dataframe(agg.sort_values("KDA", ascending=False).head(10)[["팀", "포지션", "경기", "KDA"]]
                .rename_axis("선수"), width="stretch",
                column_config={"KDA": st.column_config.NumberColumn(format="%.2f")})
    b.markdown("**최다 킬 선수**")
    b.dataframe(agg.sort_values("킬", ascending=False).head(10)[["팀", "포지션", "경기", "킬"]].rename_axis("선수"),
                width="stretch")

    ct = champion_table(eg)
    if not ct.empty:
        ct = ct.head(10).assign(아이콘=lambda d: d.index.map(champ.icon), 이름=lambda d: d.index.map(champ.name_ko))
        st.markdown("**가장 많이 등장한 챔피언** (픽 + 밴)")
        st.dataframe(ct[["아이콘", "이름", "픽", "밴", "등장률", "승률"]], hide_index=True, width="stretch",
                     column_config={"아이콘": st.column_config.ImageColumn(width="small"),
                                    "픽": st.column_config.NumberColumn(format="%d"),
                                    "밴": st.column_config.NumberColumn(format="%d"),
                                    "등장률": st.column_config.ProgressColumn(format="percent", min_value=0,
                                                                           max_value=1),
                                    "승률": st.column_config.NumberColumn(format="percent")})

# ------------------------------------------------------------------ 경기 결과
with tab_matches:
    stages = list(dict.fromkeys(played["tab"].fillna("")))[::-1]
    stage = st.selectbox("단계", ["전체"] + stages, format_func=lambda t: t if t == "전체" else tab_ko(t))
    view = played if stage == "전체" else played[played["tab"] == stage]
    rows = view.sort_values("datetime_kst", ascending=False).assign(
        날짜=lambda d: d["datetime_kst"].dt.strftime("%m.%d %H:%M"),
        단계=lambda d: d["tab"].map(tab_ko),
        스코어=lambda d: d["team1_score"].astype(int).astype(str) + " : " + d["team2_score"].astype(int).astype(str),
        승리=lambda d: d.apply(lambda r: r["team1"] if r["winner"] == 1 else r["team2"], axis=1),
        MVP=lambda d: d["mvp"].map(lambda m: display_name(m) if isinstance(m, str) else "") if "mvp" in d else "")
    st.dataframe(rows[["날짜", "단계", "team1", "스코어", "team2", "승리", "MVP"]]
                 .rename(columns={"team1": "팀 1", "team2": "팀 2"}), hide_index=True, width="stretch", height=420)
