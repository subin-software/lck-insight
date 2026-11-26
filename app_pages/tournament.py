"""🏆 대회 정보: 대회를 고르면 최종 순위, 우승팀, 결승과 MVP, 대회 기록 상위 선수, 메타, 단계별 결과를 보여준다."""
import pandas as pd
import streamlit as st

from utils import champions as champ
from utils.bracket import render_stage, split_stages
from utils.data_loader import has_data, load_players, load_tournaments
from utils.meta import champion_table
from utils.teams import display_name, season_aliases, team_games, team_info
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
tours_stage = load_tournaments()[["page", "stage"]]


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
this_year = pd.Timestamp.now(tz="Asia/Seoul").year
year_options = sorted(sub["year"].unique(), reverse=True)
# 기본값: 올해(없으면 올해 이전 가장 최근 연도). Leaguepedia에 미리 만들어진 다음 연도 대회는 '(예정)'으로 표시
past = [y for y in year_options if y <= this_year]
year = c2.selectbox("연도", year_options, index=year_options.index(past[0]) if past else 0,
                    format_func=lambda y: f"{y}년" + (" (예정)" if y > this_year else ""),
                    key=f"tour_year_{league}")
sub = sub[sub["year"] == year]
key = c3.selectbox("대회", list(sub["event_key"]), format_func=lambda k: sub.set_index("event_key").at[k, "name"],
                   disabled=len(sub) == 1)
event = sub.set_index("event_key").loc[key]
pages = tuple(event["pages"])

sched = event_schedule(pages).copy()
tg = team_games()
eg = tg[tg["page"].isin(pages)].copy()
is_lck = event["scope"] == "LCK"
if is_lck:                                   # 시즌 중 이름이 바뀐 팀은 하나로 (예: DRX → Kiwoom DRX)
    alias = season_aliases(eg)
    for col in ("team1", "team2"):
        sched[col] = sched[col].map(lambda t: alias.get(t, t))
    for col in ("team", "opponent"):
        eg[col] = eg[col].map(lambda t: alias.get(t, t))
played = sched[sched["winner"].notna()]
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

if is_lck:
    tab_rank, tab_bracket, tab_final, tab_stats, tab_matches = st.tabs(
        ["🥇 최종 순위", "🔥 포스트시즌", "🎯 결승 · MVP", "📊 대회 기록", "📋 경기 결과"])
else:
    tab_rank, tab_bracket, tab_final, tab_stats, tab_matches = st.tabs(
        ["🥇 최종 순위", "🗺️ 스테이지", "🎯 결승 · MVP", "📊 대회 기록", "📋 경기 결과"])

# LCK 정규 시즌 순위 (매치 승수 → 세트 득실)
reg = played[played["page"].isin([p for p in pages if p in set(tours_stage.loc[tours_stage["stage"] == "regular", "page"])])]
standing = pd.DataFrame()
if is_lck and not reg.empty:
    rows = []
    for _, r in reg.iterrows():
        for side, opp in ((1, 2), (2, 1)):
            rows.append({"team": r[f"team{side}"], "win": r["winner"] == side,
                         "sw": r[f"team{side}_score"], "sl": r[f"team{opp}_score"]})
    rr = pd.DataFrame(rows)
    standing = rr.groupby("team").agg(매치승=("win", "sum"), 매치=("win", "size"), 세트승=("sw", "sum"), 세트패=("sl", "sum"))
    standing["매치패"] = standing["매치"] - standing["매치승"]
    standing["세트득실"] = standing["세트승"] - standing["세트패"]

    def head_to_head(group: list[str]) -> dict[str, int]:
        """동률 팀끼리 맞대결에서 이긴 매치 수."""
        g = reg[reg["team1"].isin(group) & reg["team2"].isin(group)]
        wins = pd.concat([g.loc[g["winner"] == 1, "team1"], g.loc[g["winner"] == 2, "team2"]]).value_counts()
        return {t: int(wins.get(t, 0)) for t in group}

    # 순위 결정: 매치 승수 → 세트 득실 → (동률이면) 동률 팀 간 맞대결 승수 → 세트 승수
    standing["_h2h"] = 0
    for _, grp in standing.groupby(["매치승", "세트득실"]):
        if len(grp) > 1:
            for t, w in head_to_head(list(grp.index)).items():
                standing.at[t, "_h2h"] = w
    standing = standing.sort_values(["매치승", "세트득실", "_h2h", "세트승"], ascending=False).drop(columns="_h2h")
    standing.insert(0, "순위", range(1, len(standing) + 1))

# ------------------------------------------------------------------ 최종 순위
with tab_rank:
    if is_lck and not standing.empty:
        medal = {1: ("🥇", GOLD), 2: ("🥈", SILVER), 3: ("🥉", BRONZE)}
        top4 = standing.head(4)
        cols = st.columns(len(top4))
        for col, (team, r) in zip(cols, top4.iterrows()):
            icon, color = medal.get(int(r["순위"]), ("🏅", BRONZE))
            col.markdown(
                f"<div style='text-align:center;border:1px solid rgba(128,128,128,0.2);border-top:3px solid {color};"
                f"border-radius:10px;padding:12px 6px'>{logo(team, 52)}"
                f"<div style='font-size:0.85rem;margin-top:6px'>{icon} 정규 시즌 {int(r['순위'])}위</div>"
                f"<div style='font-weight:800'>{team}</div>"
                f"<div style='font-size:0.8rem;opacity:0.7'>{int(r['매치승'])}승 {int(r['매치패'])}패 · 득실 {int(r['세트득실']):+d}</div>"
                f"</div>", unsafe_allow_html=True)
        table = standing.reset_index().rename(columns={"team": "팀"})
        table.insert(1, "로고", table["팀"].map(lambda t: info.at[t, "logo"] if t in info.index else None))
        table["세트 승률"] = table["세트승"] / (table["세트승"] + table["세트패"])
        st.markdown("**정규 시즌 순위**")
        st.dataframe(table[["순위", "로고", "팀", "매치승", "매치패", "세트승", "세트패", "세트득실", "세트 승률"]],
                     hide_index=True, width="stretch", column_config={
                         "로고": st.column_config.ImageColumn(width="small"),
                         "세트득실": st.column_config.NumberColumn(format="%+d"),
                         "세트 승률": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)})
        st.caption("정규 시즌(모든 라운드) 매치 승수 → 세트 득실 순입니다. Road to MSI·플레이인·플레이오프 결과는 "
                   "🔥 포스트시즌 탭에서 볼 수 있습니다.")
    else:
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

# ------------------------------------------------------------------ 단계별 대진표 (LCK 포스트시즌 / 국제 대회 스테이지)
def short_name(t: str) -> str:
    return info.at[t, "short"] if t in info.index and isinstance(info.at[t, "short"], str) else display_name(t)


def logo_url(t: str):
    return info.at[t, "logo"] if t in info.index else None


with tab_bracket:
    if is_lck:
        # LCK: 정규 시즌 뒤 단계를 페이지(Road to MSI / 플레이인 / 플레이오프) 단위로 나눈다
        stage_names = {"road-to-msi": "Road to MSI", "play-in": "Play-in", "playoffs": "Play-off"}
        stage_of = dict(zip(tours_stage["page"], tours_stage["stage"]))
        stages = {}
        for p in pages:
            if stage_of.get(p) in stage_names:
                stages[stage_names[stage_of[p]]] = sched[sched["page"] == p]
        rank = {t: int(r["순위"]) for t, r in standing.iterrows()} if not standing.empty else {}
        seed = lambda t: f"정규 {rank[t]}위" if t in rank else ""  # noqa: E731
        empty_msg = "이 대회에는 Road to MSI·Play-in·Play-off 단계가 따로 없습니다."
        note = "팀 이름 아래는 정규 시즌 순위입니다."
    else:
        # 국제 대회: 그 해 실제 포맷의 단계로 나눈다 (예: 2026 Worlds = Play-in / Swiss / Knock-out)
        stages = split_stages(sched, event["league"], int(event["year"]))
        seed = lambda t: info.at[t, "region"] if t in info.index and isinstance(info.at[t, "region"], str) else ""  # noqa: E731
        empty_msg = "이 대회의 단계별 경기 기록이 없습니다."
        note = "팀 이름 아래는 소속 지역(스위스 스테이지는 그 경기 전 전적)입니다."
    order = [n for n in stages if not stages[n].empty]
    if not order:
        st.info(empty_msg)
    else:
        pick = st.pills("단계", order, default=order[-1], selection_mode="single",
                        key=f"bracket_stage_{key}") or order[-1]
        html = render_stage(stages[pick], pick, short_name, logo_url, seed, f"{event['name']} {pick}")
        st.markdown(html, unsafe_allow_html=True)
        st.caption(f"금색으로 표시된 쪽이 이긴 팀입니다. {note} 승자조·패자조는 '그 경기 전에 이미 진 적이 "
                   "있는지'로, 조별 리그의 조는 '서로 경기한 팀끼리'로 구분했습니다.")

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
