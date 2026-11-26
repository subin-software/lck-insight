"""🌏 국제전: 리그 간 상대 전적, 대회별 우승 기록, 팀 상대 전적, 국내 리그와 국제전의 메타 차이."""
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import champions as champ
from utils.data_loader import has_data
from utils.international import (LEAGUE_COLOR, MAJOR, intl_games, intl_series, league_counts, league_matrix,
                                 team_league, tournament_results)
from utils.meta import champion_table
from utils.teams import lineage_of, team_games

STAGE_KO = {"Finals": "결승", "Semifinals": "4강", "Quarterfinals": "8강"}
TOURNAMENTS = ["Worlds", "MSI", "First Stand", "EWC"]

st.title("🌏 국제전")
st.caption("Worlds(롤드컵), MSI, First Stand, EWC 기록으로 LCK와 해외 리그(LPL·LEC·LCS 등)의 실력 차이, "
           "대회별 우승 팀, 팀 간 상대 전적, 국내 리그와 국제전의 메타 차이를 보여줍니다.")

if not has_data():
    st.warning("아직 수집된 데이터가 없습니다.")
    st.stop()

games, series, results = intl_games(), intl_series(), tournament_results()

c1, c2 = st.columns([2, 3])
tours = c1.multiselect("대회", TOURNAMENTS, default=TOURNAMENTS)
y_min, y_max = int(games["year"].min()), int(games["year"].max())
years = c2.slider("기간", y_min, y_max, (2016, y_max))
games = games[games["league_short"].isin(tours) & games["year"].between(*years)]
series = series[series["league_short"].isin(tours) & series["year"].between(*years)]
results = results[results["대회"].isin(tours) & results["연도"].between(*years)]
if games.empty:
    st.info("조건에 맞는 경기가 없습니다.")
    st.stop()

titles = results["우승 리그"].value_counts()
m = st.columns(4)
m[0].metric("국제전 세트", f"{games['game_id'].nunique():,}", border=True)
m[1].metric("대회 수", f"{len(results)}", border=True)
m[2].metric("LCK 우승 횟수", f"{titles.get('LCK', 0)}회", border=True)
m[3].metric("LPL 우승 횟수", f"{titles.get('LPL', 0)}회", border=True)

tab_league, tab_titles, tab_team, tab_meta = st.tabs(
    ["⚔️ 리그 간 상대 전적", "🏆 대회별 결과", "🤝 팀 상대 전적", "🧩 국내 vs 국제 메타"])

# ------------------------------------------------------------------ 리그 간 상대 전적
with tab_league:
    leagues = st.multiselect("비교할 리그", list(LEAGUE_COLOR), default=MAJOR)
    if len(leagues) >= 2:
        left, right = st.columns([3, 2])
        with left:
            mat, cnt = league_matrix(games, leagues), league_counts(games, leagues)
            text = mat.map(lambda v: "" if pd.isna(v) else f"{v:.0%}") + cnt.map(
                lambda n: "" if pd.isna(n) else f"<br>({int(n)}세트)")
            fig = px.imshow(mat, color_continuous_scale="RdBu", zmin=0.2, zmax=0.8, aspect="auto")
            fig.update_traces(text=text.values, texttemplate="%{text}")
            fig.update_layout(height=380, margin=dict(t=40, b=10), coloraxis_showscale=False,
                              xaxis_title="상대 리그", yaxis_title=None,
                              title=dict(text="행 리그가 열 리그를 상대로 거둔 세트 승률", font_size=14))
            st.plotly_chart(fig, width="stretch")
        with right:
            overall = games[games["league"].isin(leagues) & (games["league"] != games["opp_league"])] \
                .groupby("league")["win"].agg(["mean", "size"]).reindex(leagues)
            fig = px.bar(overall.reset_index(), x="league", y="mean", color="league", text_auto=".0%",
                         color_discrete_map=LEAGUE_COLOR)
            fig.update_layout(height=380, margin=dict(t=40, b=10), showlegend=False, xaxis_title=None,
                              yaxis_title="세트 승률", yaxis_tickformat=".0%", yaxis_range=[0, 1],
                              title=dict(text="다른 리그 상대 전체 승률", font_size=14))
            st.plotly_chart(fig, width="stretch")

        st.markdown("**연도별 LCK 상대 승률** — LCK가 각 리그를 상대로 몇 % 이겼는지")
        lck = games[(games["league"] == "LCK") & games["opp_league"].isin([l for l in leagues if l != "LCK"])]
        yearly = lck.groupby(["year", "opp_league"])["win"].agg(["mean", "size"]).reset_index()
        fig = px.line(yearly, x="year", y="mean", color="opp_league", markers=True,
                      hover_data={"size": True}, color_discrete_map=LEAGUE_COLOR,
                      labels={"mean": "LCK 승률", "opp_league": "상대 리그", "size": "세트 수", "year": "연도"})
        fig.add_hline(y=0.5, line_dash="dot", line_color="gray")
        fig.update_layout(height=360, margin=dict(t=10, b=10), yaxis_tickformat=".0%", yaxis_range=[0, 1])
        fig.update_xaxes(dtick=1)
        st.plotly_chart(fig, width="stretch")
        st.caption("50% 선보다 위면 그 해에 LCK가 우세했다는 뜻입니다. 예를 들어 2018~2021년에는 LPL에 밀렸다가 "
                   "이후 다시 앞서는 흐름을 볼 수 있습니다. 세트 수가 적은 해는 값이 크게 출렁일 수 있습니다.")
    else:
        st.info("리그를 2개 이상 선택하세요.")

# ------------------------------------------------------------------ 대회별 결과
with tab_titles:
    left, right = st.columns([3, 2])
    with left:
        view = results.sort_values(["연도", "대회"], ascending=[False, True]).assign(
            **{"LCK 최고 성적": lambda d: d["LCK 최고 성적"].map(
                lambda s: {"우승": "🏆 우승", "준우승": "🥈 준우승"}.get(s, STAGE_KO.get(s, s)))})
        st.dataframe(view[["연도", "대회", "우승", "우승 리그", "결승 스코어", "준우승", "LCK 최고 성적"]],
                     hide_index=True, width="stretch", height=480,
                     column_config={"연도": st.column_config.NumberColumn(format="%d")})
    with right:
        tc = results.groupby(["우승 리그", "대회"]).size().reset_index(name="우승")
        fig = px.bar(tc, x="우승 리그", y="우승", color="대회", text_auto=True,
                     category_orders={"우승 리그": list(titles.index)})
        fig.update_layout(height=480, margin=dict(t=40, b=10), legend_title=None, xaxis_title=None,
                          title=dict(text="리그별 우승 횟수", font_size=14))
        st.plotly_chart(fig, width="stretch")
    st.caption("결승은 각 대회의 마지막 경기로 판단합니다. 팀 이름은 당시 이름입니다 (예: SK Telecom T1 → T1).")

# ------------------------------------------------------------------ 팀 상대 전적
with tab_team:
    lg = team_league()
    counts = series.groupby("team").size().sort_values(ascending=False)
    label = lambda t: f"{t} ({lg.get(t, '기타')})"
    t1, t2 = st.columns(2)
    team_a = t1.selectbox("팀 A", list(counts.index), index=None, placeholder="팀을 선택하세요", format_func=label)
    if team_a is None:
        st.info("👆 팀을 선택하면 그 팀의 국제전 기록과 상대 전적이 나타납니다.")
    else:
        names = lineage_of(team_a)             # 이름이 바뀐 시기 기록도 함께 (예: SK Telecom T1 → T1)
        mine = series[series["team"].isin(names)]
        opps = mine.groupby("opponent").size().sort_values(ascending=False)
        team_b = t2.selectbox("팀 B (선택하면 맞대결 기록)", list(opps.index), index=None,
                              placeholder="전체 상대", format_func=label)
        if team_b is None:
            by_league = games[games["team"].isin(names)].groupby("opp_league")["win"].agg(["mean", "size"])
            mm = st.columns(3)
            mm[0].metric("국제전 매치 전적", f"{int(mine['win'].sum())}승 {int((~mine['win']).sum())}패", border=True)
            mm[1].metric("세트 승률", f"{games[games['team'].isin(names)]['win'].mean():.0%}", border=True)
            mm[2].metric("우승", f"{results['우승'].isin(names).sum()}회", border=True)
            if len(names) > 1:
                st.caption("이름이 바뀐 시기의 기록을 합친 값입니다: " + " · ".join(names))
            st.dataframe(by_league.rename(columns={"mean": "세트 승률", "size": "세트 수"}).rename_axis("상대 리그"),
                         width="stretch", column_config={"세트 승률": st.column_config.ProgressColumn(
                             format="percent", min_value=0, max_value=1)})
        else:
            h2h = mine[mine["opponent"].isin(lineage_of(team_b))].sort_values("datetime_kst", ascending=False)
            mm = st.columns(2)
            mm[0].metric(f"{team_a} 매치 전적", f"{int(h2h['win'].sum())}승 {int((~h2h['win']).sum())}패", border=True)
            mm[1].metric("세트 득실", f"{int(h2h['score'].sum())} : {int(h2h['opp_score'].sum())}", border=True)
            st.dataframe(h2h.assign(날짜=h2h["datetime_kst"].dt.strftime("%Y-%m-%d"),
                                    스코어=h2h["score"].astype(int).astype(str) + " : " + h2h["opp_score"].astype(int).astype(str),
                                    결과=h2h["win"].map({True: "✅ 승", False: "❌ 패"}),
                                    단계=h2h["tab"].map(lambda t: STAGE_KO.get(t, t)))
                         [["날짜", "tournament", "단계", "스코어", "결과"]].rename(columns={"tournament": "대회"}),
                         hide_index=True, width="stretch")

# ------------------------------------------------------------------ 국내 vs 국제 메타
with tab_meta:
    year = st.selectbox("연도", sorted(games["year"].unique().astype(int), reverse=True),
                        format_func=lambda y: f"{y}년", key="meta_year")
    tg = team_games()
    lck_t = champion_table(tg[(tg["scope"] == "LCK") & (tg["year"] == year)])
    intl_t = champion_table(tg[(tg["scope"] == "INTL") & (tg["year"] == year) & tg["league_short"].isin(tours)])
    if lck_t.empty or intl_t.empty:
        st.info("그 해의 LCK 또는 국제전 기록이 없습니다.")
    else:
        both = pd.DataFrame({"LCK 등장률": lck_t["등장률"], "국제전 등장률": intl_t["등장률"]}).fillna(0)
        both["차이"] = both["국제전 등장률"] - both["LCK 등장률"]
        both.insert(0, "챔피언", both.index.map(champ.name_ko))
        both.insert(0, "아이콘", both.index.map(champ.icon))
        cfg = {"아이콘": st.column_config.ImageColumn(width="small"),
               "LCK 등장률": st.column_config.NumberColumn(format="percent"),
               "국제전 등장률": st.column_config.NumberColumn(format="percent"),
               "차이": st.column_config.NumberColumn(format="%+.0f%%p")}
        a, b = st.columns(2)
        a.markdown("**국제전에서 더 많이 등장한 챔피언**")
        a.dataframe(both.sort_values("차이", ascending=False).head(8).assign(차이=lambda d: d["차이"] * 100),
                    hide_index=True, width="stretch", column_config=cfg)
        b.markdown("**LCK에서 더 많이 등장한 챔피언**")
        b.dataframe(both.sort_values("차이").head(8).assign(차이=lambda d: d["차이"] * 100),
                    hide_index=True, width="stretch", column_config=cfg)
        top = both.sort_values("LCK 등장률", ascending=False).head(25)
        fig = px.scatter(top, x="LCK 등장률", y="국제전 등장률", text="챔피언")
        fig.add_shape(type="line", x0=0, y0=0, x1=1, y1=1, line=dict(dash="dot", color="gray"))
        fig.update_traces(textposition="top center", marker_color="#C89B3C")
        fig.update_layout(height=420, margin=dict(t=40, b=10), xaxis_tickformat=".0%", yaxis_tickformat=".0%",
                          title=dict(text="LCK 등장률 vs 국제전 등장률 (LCK 상위 25개)", font_size=14))
        st.plotly_chart(fig, width="stretch")
        st.caption("점선 위쪽은 국제전에서 더 중요하게 다뤄진 챔피언, 아래쪽은 LCK에서 더 많이 쓰인 챔피언입니다.")
