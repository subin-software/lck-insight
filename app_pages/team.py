"""🛡️ 팀 분석: 시즌·팀을 골라 당시 로스터, 성적, 챔피언, 국제전, 팀 역사를 본다."""
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import champions as champ
from utils.data_loader import has_data, load_players, load_rosters, load_tournaments
from utils.teams import (ROLE_KO, ROLE_ORDER, current_status, display_name, lineage_of,
                         player_photo, rename_history, team_games, team_info, team_series)

TAB_KO = {"Finals": "결승", "Semifinals": "준결승", "Quarterfinals": "8강",
          "Final": "결승", "Semifinal": "준결승"}


def tab_ko(tab: str) -> str:
    if tab in TAB_KO:
        return TAB_KO[tab]
    if isinstance(tab, str) and tab.startswith("Round "):
        return tab.replace("Round ", "") + "라운드"
    return tab

st.title("🛡️ 팀 분석")
st.caption("시즌과 팀을 고르면 그 시즌의 로스터와 성적, 같은 해 국제전 기록, 팀의 역사를 보여줍니다. "
           "과거에 활동한 팀도 선택할 수 있습니다.")

if not has_data():
    st.warning("아직 수집된 데이터가 없습니다. 데이터 수집이 끝나면 이 페이지가 활성화됩니다.")
    st.stop()

tours = load_tournaments()
games = team_games()
series = team_series()
lck_games = games[games["scope"] == "LCK"]

# ------------------------------------------------------------------ 선택
c1, c2, c3 = st.columns([1, 1, 2])
years = sorted(lck_games["year"].dropna().unique(), reverse=True)
year = c1.selectbox("연도", years, format_func=lambda y: f"{y}년")

year_tours = tours[(tours["scope"] == "LCK") & (tours["year"] == year)
                   & tours["page"].isin(lck_games["page"])].sort_values("date_start")
splits = list(dict.fromkeys(year_tours["split"].replace("", "기타")))
split = c2.selectbox("스플릿", ["시즌 전체"] + splits)
pages = year_tours["page"] if split == "시즌 전체" else \
    year_tours.loc[year_tours["split"].replace("", "기타") == split, "page"]

sel_games = lck_games[lck_games["page"].isin(pages)]
sel_series = series[series["page"].isin(pages)]


def standings(ser: pd.DataFrame) -> pd.DataFrame:
    """정규 시즌 시리즈 결과로 순위표를 만든다 (매치 승수 → 세트 득실 순)."""
    reg = ser[ser["stage"] == "regular"]
    if reg.empty:
        return pd.DataFrame()
    t = reg.groupby("team").agg(매치승=("win", "sum"), 경기수=("win", "size"),
                                세트승=("score", "sum"), 세트패=("opp_score", "sum"))
    t["매치패"] = t["경기수"] - t["매치승"]
    t["세트득실"] = t["세트승"] - t["세트패"]
    t = t.sort_values(["매치승", "세트득실"], ascending=False)
    t.insert(0, "순위", range(1, len(t) + 1))
    return t[["순위", "매치승", "매치패", "세트승", "세트패", "세트득실"]]


table = standings(sel_series)
team_list = list(table.index) + sorted(set(sel_games["team"]) - set(table.index))
team = c3.selectbox("팀", team_list, help="정규 시즌 순위 순서로 정렬되어 있습니다.")

tg = sel_games[sel_games["team"] == team]
ts = sel_series[sel_series["team"] == team]
info = team_info()
names = lineage_of(team)

# ------------------------------------------------------------------ 헤더
h1, h2 = st.columns([1, 8])
if team in info.index and isinstance(info.at[team, "logo"], str):
    h1.image(info.at[team, "logo"], width=72)
sub = f"{year}년 {split}"
latest, disbanded = current_status(team)
if latest != team:
    sub += f" · 현재 팀 이름: **{latest}**"
elif disbanded:
    sub += " · 해체된 팀"
h2.markdown(f"## {team}\n{sub}")

tab_overview, tab_roster, tab_matches, tab_champs, tab_intl, tab_history = st.tabs(
    ["📋 개요", "👥 로스터", "📈 경기 기록", "🏆 챔피언", "🌏 국제전", "🕰️ 팀 역사"])

# ------------------------------------------------------------------ 개요
with tab_overview:
    def playoff_results() -> list[tuple[str, str]]:
        """스플릿별 (스플릿, 플레이오프 결과)."""
        po = sel_series[sel_series["stage"] == "playoffs"]
        out = []
        for page in [p for p in pages if p in set(po["page"])]:
            pp = po[po["page"] == page]
            mine = pp[pp["team"] == team]
            sp = pp["split"].iloc[0] or "플레이오프"
            if mine.empty:
                out.append((sp, "진출 못함"))
                continue
            last = mine.iloc[-1]
            if last["match_id"] == pp.iloc[-1]["match_id"]:
                out.append((sp, "🏆 우승" if last["win"] else "🥈 준우승"))
            else:
                out.append((sp, f"{tab_ko(last['tab'])} 탈락"))
        return out

    sets_w, sets_n = int(tg["win"].sum()), len(tg)
    note = dict(delta_color="off", delta_arrow="off", border=True)   # 보조 설명은 화살표 없이 회색으로
    m = st.columns(3)
    m[0].metric("매치 전적 (승-패)", f"{int(ts['win'].sum())}-{int((~ts['win']).sum())}", border=True)
    m[1].metric("세트 승률", f"{sets_w / sets_n:.0%}" if sets_n else "-",
                f"{sets_w}승 {sets_n - sets_w}패", **note)
    if not table.empty and team in table.index:
        m[2].metric("정규 시즌 순위", f"{table.at[team, '순위']}위", f"{len(table)}팀 중", **note)
    else:
        m[2].metric("정규 시즌 순위", "-", border=True)
    po_results = playoff_results()
    m = st.columns(2)
    m[0].metric("플레이오프", po_results[-1][1] if po_results else "-",
                f"{po_results[-1][0]} 스플릿" if len(po_results) > 1 else None, **note)
    m[1].metric("평균 경기 시간", f"{tg['gamelength'].mean():.1f}분" if sets_n else "-", border=True)
    if len(po_results) > 1:
        st.caption("스플릿별 플레이오프: " + " · ".join(f"{s} {r}" for s, r in po_results))

    left, right = st.columns(2)
    with left:
        st.markdown("**진영별 승률**")
        side = tg.groupby("side")["win"].agg(["mean", "size"]).reindex(["Blue", "Red"])
        fig = px.bar(x=["블루", "레드"], y=side["mean"].fillna(0),
                     text=[f"{v:.0%} ({int(n) if pd.notna(n) else 0}경기)" for v, n in
                           zip(side["mean"].fillna(0), side["size"])],
                     color=["블루", "레드"], color_discrete_map={"블루": "#3B82F6", "레드": "#EF4444"})
        fig.update_layout(showlegend=False, yaxis_tickformat=".0%", yaxis_range=[0, 1],
                          xaxis_title=None, yaxis_title="승률", height=300, margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch")
    with right:
        st.markdown("**리그 평균 대비 경기당 지표**")
        stats = {"킬": "kills", "드래곤": "dragons", "바론": "barons", "포탑": "towers"}
        comp = pd.DataFrame({
            "지표": list(stats),
            team: [tg[c].mean() for c in stats.values()],
            "리그 평균": [sel_games[c].mean() for c in stats.values()],
        }).melt("지표", var_name="구분", value_name="값")
        fig = px.bar(comp, x="지표", y="값", color="구분", barmode="group",
                     color_discrete_sequence=["#C89B3C", "#9CA3AF"])
        fig.update_layout(height=300, margin=dict(t=10, b=10), xaxis_title=None, yaxis_title=None,
                          legend_title=None)
        st.plotly_chart(fig, width="stretch")

    if not table.empty:
        st.markdown("**정규 시즌 순위표**")
        st.dataframe(table.style.apply(
            lambda r: ["background-color: rgba(200,155,60,0.25)" if r.name == team else "" for _ in r],
            axis=1), width="stretch")
        st.caption("정규 시즌 시리즈 결과 기준 (매치 승수 → 세트 득실 순). 실제 리그 순위 규정과 다를 수 있습니다.")

# ------------------------------------------------------------------ 로스터
with tab_roster:
    rosters = load_rosters()
    roster = rosters[rosters["page"].isin(pages) & (rosters["team"] == team)]
    players = load_players()
    played = players[players["page"].isin(pages) & (players["team"] == team)]
    stat = played.groupby(["player", "role"]).agg(
        경기=("game_id", "nunique"), 승=("win", "sum"), 킬=("kills", "sum"),
        데스=("deaths", "sum"), 어시=("assists", "sum")).reset_index()
    stat["KDA"] = (stat["킬"] + stat["어시"]) / stat["데스"].clip(lower=1)
    stat["승률"] = stat["승"] / stat["경기"]

    if stat.empty:
        st.info("이 시즌의 선수 기록이 없습니다.")
    else:
        starters = stat.sort_values("경기", ascending=False).drop_duplicates("role")
        starters = starters[starters["role"].isin(ROLE_ORDER)].sort_values(
            "role", key=lambda s: s.map(ROLE_ORDER))
        st.markdown("**주전 라인업** (포지션별 출전 경기가 가장 많은 선수)")
        cols = st.columns(5)
        for col, (_, p) in zip(cols, starters.iterrows()):
            with col.container(border=True):
                photo = player_photo(p["player"], pages, int(year), team)
                if photo:
                    st.image(photo, width="stretch")
                else:
                    st.markdown("<div style='font-size:64px;text-align:center'>👤</div>",
                                unsafe_allow_html=True)
                st.markdown(f"**{display_name(p['player'])}**  \n"
                            f"<small>{ROLE_KO.get(p['role'], p['role'])}</small>",
                            unsafe_allow_html=True)
                st.caption(f"{p['경기']}경기 · KDA {p['KDA']:.2f} · 승률 {p['승률']:.0%}")

        subs = stat[~stat.index.isin(starters.index)]
        if not subs.empty:
            st.markdown("**교체 출전 선수**")
            st.dataframe(subs.assign(포지션=subs["role"].map(lambda r: ROLE_KO.get(r, r)),
                                     player=subs["player"].map(display_name))
                         [["player", "포지션", "경기", "KDA", "승률"]]
                         .rename(columns={"player": "선수"}),
                         hide_index=True, width="stretch",
                         column_config={"KDA": st.column_config.NumberColumn(format="%.2f"),
                                        "승률": st.column_config.NumberColumn(format="percent")})

    staff = roster[~roster["role"].isin(ROLE_ORDER)]
    if not staff.empty:
        st.markdown("**코칭 스태프 · 등록 선수**")
        st.write(", ".join(f"{display_name(r.player)} ({ROLE_KO.get(r.role, r.role)})"
                           for r in staff.drop_duplicates("player").itertuples()))

# ------------------------------------------------------------------ 경기 기록
with tab_matches:
    if ts.empty:
        st.info("이 시즌의 경기 기록이 없습니다.")
    else:
        flow = tg.reset_index(drop=True)
        flow["누적 승률"] = flow["win"].expanding().mean()
        flow["경기"] = range(1, len(flow) + 1)
        fig = px.line(flow, x="경기", y="누적 승률", markers=True,
                      hover_data={"opponent": True, "datetime_kst": "|%Y-%m-%d"})
        fig.update_traces(line_color="#C89B3C")
        fig.update_layout(yaxis_tickformat=".0%", yaxis_range=[0, 1], height=300,
                          margin=dict(t=10, b=10), xaxis_title="세트 순서")
        st.markdown("**시즌 흐름 (세트 누적 승률)**")
        st.plotly_chart(fig, width="stretch")

        left, right = st.columns([3, 2])
        with left:
            st.markdown("**매치 결과**")
            view = ts.sort_values("datetime_kst", ascending=False).assign(
                날짜=lambda d: d["datetime_kst"].dt.strftime("%Y-%m-%d"),
                결과=lambda d: d["win"].map({True: "✅ 승", False: "❌ 패"}),
                스코어=lambda d: d["score"].astype(int).astype(str) + " : " + d["opp_score"].astype(int).astype(str),
                단계=lambda d: d["tab"].map(tab_ko))
            st.dataframe(view[["날짜", "opponent", "스코어", "결과", "단계"]].rename(columns={"opponent": "상대"}),
                         hide_index=True, width="stretch", height=400)
        with right:
            st.markdown("**상대 전적**")
            h2h = ts.groupby("opponent").agg(매치승=("win", "sum"), 매치=("win", "size"),
                                             세트승=("score", "sum"), 세트패=("opp_score", "sum"))
            h2h["매치패"] = h2h["매치"] - h2h["매치승"]
            st.dataframe(h2h[["매치승", "매치패", "세트승", "세트패"]].astype(int)
                         .sort_values("매치승", ascending=False).rename_axis("상대"),
                         width="stretch", height=400)

# ------------------------------------------------------------------ 챔피언
with tab_champs:
    def champ_table(df: pd.DataFrame, column: str, with_win: bool) -> pd.DataFrame:
        ex = champ.explode_champions(df, column)
        if ex.empty:
            return pd.DataFrame()
        t = ex.groupby("champion").agg(횟수=("game_id", "size"), 승률=("win", "mean")).reset_index()
        t = t.sort_values("횟수", ascending=False).head(15)
        t.insert(0, "아이콘", t["champion"].map(champ.icon))
        t.insert(2, "이름", t["champion"].map(champ.name_ko))
        cols = ["아이콘", "이름", "횟수"] + (["승률"] if with_win else [])
        return t[cols]

    cfg = {"아이콘": st.column_config.ImageColumn(width="small"),
           "승률": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)}
    a, b, c = st.columns(3)
    with a:
        st.markdown("**많이 고른 챔피언**")
        st.dataframe(champ_table(tg, "picks", True), hide_index=True, column_config=cfg, width="stretch")
    with b:
        st.markdown("**우리 팀이 밴한 챔피언**")
        st.dataframe(champ_table(tg, "bans", False), hide_index=True, column_config=cfg, width="stretch")
    with c:
        st.markdown("**상대가 이 팀을 상대로 밴한 챔피언**")
        opp_bans = sel_games[sel_games["game_id"].isin(tg["game_id"]) & (sel_games["team"] != team)]
        st.dataframe(champ_table(opp_bans, "bans", False), hide_index=True, column_config=cfg, width="stretch")
    st.caption("승률은 해당 챔피언을 고른 세트의 승률입니다.")

# ------------------------------------------------------------------ 국제전
with tab_intl:
    intl = games[(games["scope"] == "INTL") & (games["year"] == year) & games["team"].isin(names)]
    intl_s = series[(series["scope"] == "INTL") & (series["year"] == year) & series["team"].isin(names)]
    if intl.empty:
        st.info(f"{year}년에는 이 팀의 국제 대회(Worlds, MSI, First Stand, EWC) 출전 기록이 없습니다.")
    else:
        rows = []
        for tour, g in intl.groupby("league_short"):
            s = intl_s[intl_s["league_short"] == tour]
            all_s = series[(series["league_short"] == tour) & (series["year"] == year)]
            last = s.iloc[-1] if not s.empty else None
            if last is not None and not all_s.empty and last["match_id"] == all_s.iloc[-1]["match_id"]:
                result = "🏆 우승" if last["win"] else "🥈 준우승"
            elif last is not None:
                result = f"{tab_ko(last['tab'])}에서 종료"
            else:
                result = "-"
            rows.append({"대회": tour, "세트 전적": f"{int(g['win'].sum())}승 {int((~g['win']).sum())}패",
                         "세트 승률": g["win"].mean(), "최종 결과": result})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"세트 승률": st.column_config.ProgressColumn(
                         format="percent", min_value=0, max_value=1)})

        st.markdown("**상대한 해외 팀**")
        opp = intl.groupby("opponent").agg(세트=("win", "size"), 승=("win", "sum")).reset_index()
        opp["지역"] = opp["opponent"].map(lambda t: info.at[t, "region"] if t in info.index else "")
        opp["패"] = opp["세트"] - opp["승"]
        st.dataframe(opp[["opponent", "지역", "승", "패"]].rename(columns={"opponent": "상대"})
                     .sort_values("승", ascending=False), hide_index=True, width="stretch")

# ------------------------------------------------------------------ 팀 역사
with tab_history:
    hist = rename_history(team)
    if len(names) > 1:
        st.markdown("**팀 이름 변경 이력**")
        st.dataframe(hist.assign(날짜=hist["date"].dt.strftime("%Y-%m-%d"))
                     [["날짜", "original_name", "new_name"]]
                     .rename(columns={"original_name": "이전 이름", "new_name": "새 이름"}),
                     hide_index=True, width="stretch")
    else:
        st.caption("이 팀은 기록된 이름 변경 이력이 없습니다.")

    yearly = games[games["team"].isin(names) & games["scope"].isin(["LCK", "INTL"])]
    by_year = yearly.groupby(["year", "scope"]).agg(승률=("win", "mean"), 세트=("win", "size"),
                                                   이름=("team", lambda s: s.mode().iat[0])).reset_index()
    by_year["구분"] = by_year["scope"].map({"LCK": "LCK", "INTL": "국제전"})
    fig = px.line(by_year, x="year", y="승률", color="구분", markers=True,
                  hover_data={"이름": True, "세트": True, "scope": False},
                  color_discrete_map={"LCK": "#C89B3C", "국제전": "#3B82F6"})
    fig.update_layout(yaxis_tickformat=".0%", yaxis_range=[0, 1], height=350,
                      xaxis_title="연도", yaxis_title="세트 승률", legend_title=None,
                      margin=dict(t=10, b=10))
    fig.update_xaxes(dtick=1)
    st.markdown("**연도별 세트 승률** (이름이 바뀐 시기도 하나의 팀으로 연결)")
    st.plotly_chart(fig, width="stretch")
    st.caption("팀 계보는 Leaguepedia의 팀 이름 변경 기록으로 연결합니다. 기업 인수 등 일부 경우는 연결되지 않을 수 있습니다.")
