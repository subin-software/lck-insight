"""👤 선수 분석: 커리어 추이, 챔피언 폭, 선수 비교(레이더), 플레이 유형 군집(KMeans)."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils import champions as champ
from utils.data_loader import has_data
from utils.players import (ARCHETYPES, MIN_GAMES, RADAR_FEATURES, STYLE_FEATURES, percentiles,
                           player_games, season_table, similar_players, style_clusters, summarize)
from utils.teams import ROLE_KO, ROLE_ORDER, display_name, player_photo

SCOPE_KO = {"LCK": "LCK", "INTL": "국제전", "FOREIGN": "해외 리그"}
SCOPE_COLOR = {"LCK": "#C89B3C", "국제전": "#3B82F6", "해외 리그": "#10B981"}
STYLE_COLOR = {"캐리형": "#EF4444", "팀플레이형": "#3B82F6", "안정형": "#10B981",
               "공격형": "#F59E0B", "조력형": "#8B5CF6"}

st.title("👤 선수 분석")
st.caption("선수를 고르면 커리어 기록(LCK·국제전·해외 리그), 챔피언 폭, 다른 선수와의 비교, "
           "머신러닝(KMeans)으로 분류한 플레이 유형을 보여줍니다.")

if not has_data():
    st.warning("아직 수집된 데이터가 없습니다.")
    st.stop()

pg = player_games(include_foreign=True)

# ------------------------------------------------------------------ 선수 선택
@st.cache_data
def player_index() -> pd.DataFrame:
    """선수 목록: 주 포지션, 마지막 팀, LCK·국제전 경기 수 (많이 뛴 순)."""
    main = pg[pg["scope"].isin(["LCK", "INTL"])].sort_values("datetime_kst")
    idx = main.groupby("player").agg(games=("game_id", "size"), role=("role", lambda s: s.mode().iat[0]),
                                     team=("team", "last"), last=("datetime_kst", "max"))
    return idx.sort_values("games", ascending=False)


idx = player_index()
c1, c2 = st.columns([1, 3])
role_filter = c1.selectbox("포지션", ["전체"] + list(ROLE_ORDER), format_func=lambda r: ROLE_KO.get(r, r))
options = idx if role_filter == "전체" else idx[idx["role"] == role_filter]
default = list(options.index).index("Faker") if "Faker" in options.index else 0
player = c2.selectbox(
    "선수 (이름을 입력해 검색할 수 있습니다)", list(options.index), index=default,
    format_func=lambda p: f"{display_name(p)} · {ROLE_KO.get(idx.at[p, 'role'], idx.at[p, 'role'])} · "
                          f"{idx.at[p, 'team']} ({idx.at[p, 'games']}경기)")

mine = pg[pg["player"] == player].sort_values("datetime_kst")
role = idx.at[player, "role"]
total = summarize(mine)

# ------------------------------------------------------------------ 헤더
h1, h2 = st.columns([1, 4])
last = mine.iloc[-1]
photo = player_photo(player, [last["page"]], int(last["year"]), last["team"])
with h1:
    if photo:
        st.image(photo, width="stretch")
    else:
        st.markdown("<div style='font-size:96px;text-align:center'>👤</div>", unsafe_allow_html=True)
with h2:
    st.markdown(f"## {display_name(player)}")
    years = mine["year"].dropna().astype(int)
    st.caption(f"{ROLE_KO.get(role, role)} · 최근 소속 {last['team']} · "
               f"{years.min()}~{years.max()}년 활동 · 기록된 전체 경기 {total['games']}경기")

m = st.columns(4)
note = dict(delta_color="off", delta_arrow="off", border=True)
m[0].metric("통산 승률", f"{total['win_rate']:.0%}", f"{total['wins']}승 {total['games'] - total['wins']}패", **note)
m[1].metric("통산 KDA", f"{total['kda']:.2f}", border=True)
m[2].metric("킬 관여율", f"{total['kp']:.0%}", border=True)
m[3].metric("국제전", f"{int((mine['scope'] == 'INTL').sum())}경기", border=True)

tab_career, tab_champ, tab_compare, tab_style = st.tabs(
    ["📈 커리어", "🏆 챔피언", "⚔️ 선수 비교", "🧬 플레이 유형"])

# ------------------------------------------------------------------ 커리어
with tab_career:
    yearly_photos = []
    for y, df in mine.groupby("year"):
        url = player_photo(player, list(df["page"].unique()), int(y), df["team"].mode().iat[0])
        if url and url not in [u for u, _ in yearly_photos]:
            yearly_photos.append((url, f"{int(y)} {df['team'].mode().iat[0]}"))
    if yearly_photos:
        st.markdown("**연도별 프로필 사진**")
        cols = st.columns(min(len(yearly_photos), 8))
        for i, (url, cap) in enumerate(yearly_photos[-8:]):
            cols[i].image(url, caption=cap, width="stretch")

    rows = []
    for (y, scope, league, team), df in mine.groupby(["year", "scope", "league_short", "team"]):
        s = summarize(df)
        rows.append({"연도": int(y), "구분": SCOPE_KO[scope], "리그·대회": league, "팀": team,
                     "경기": s["games"], "승률": s["win_rate"], "KDA": s["kda"], "킬 관여율": s["kp"],
                     "분당 CS": s["cs_min"], "분당 딜량": s["dpm"]})
    career = pd.DataFrame(rows).sort_values(["연도", "구분"])
    st.markdown("**시즌별 기록**")
    st.dataframe(career.iloc[::-1], hide_index=True, width="stretch", column_config={
        "연도": st.column_config.NumberColumn(format="%d"),
        "승률": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        "KDA": st.column_config.NumberColumn(format="%.2f"),
        "킬 관여율": st.column_config.NumberColumn(format="percent"),
        "분당 CS": st.column_config.NumberColumn(format="%.1f"),
        "분당 딜량": st.column_config.NumberColumn(format="%.0f"),
    })
    st.caption("해외 리그 기록은 경기 시간이 수집되지 않아 분당 지표가 비어 있습니다. "
               "딜량은 2020년 이후 기록만 있습니다.")

    trend = mine.assign(구분=mine["scope"].map(SCOPE_KO)).groupby(["year", "구분"]).apply(
        lambda d: pd.Series({"KDA": summarize(d)["kda"], "승률": d["win"].mean(), "경기": len(d)}),
        include_groups=False).reset_index()
    left, right = st.columns(2)
    for col, metric, fmt in [(left, "KDA", None), (right, "승률", ".0%")]:
        fig = px.line(trend, x="year", y=metric, color="구분", markers=True, hover_data=["경기"],
                      color_discrete_map=SCOPE_COLOR)
        fig.update_layout(height=300, margin=dict(t=30, b=10), xaxis_title=None, legend_title=None,
                          title=dict(text=f"연도별 {metric}", font_size=14))
        fig.update_xaxes(dtick=1)
        if fmt:
            fig.update_yaxes(tickformat=fmt, range=[0, 1])
        col.plotly_chart(fig, width="stretch")

# ------------------------------------------------------------------ 챔피언
with tab_champ:
    y_min, y_max = int(years.min()), int(years.max())
    period = (st.slider("기간", y_min, y_max, (y_min, y_max)) if y_min < y_max else (y_min, y_max))
    sel = mine[mine["year"].between(*period)]
    pool = sel.groupby("champion").apply(lambda d: pd.Series(summarize(d)), include_groups=False)
    pool = pool.sort_values("games", ascending=False).reset_index()
    a, b, c = st.columns(3)
    a.metric("사용한 챔피언 수", f"{len(pool)}개", border=True)
    b.metric("가장 많이 쓴 챔피언", champ.name_ko(pool.iloc[0]["champion"]) if len(pool) else "-", border=True)
    top3 = pool.head(3)["games"].sum() / max(pool["games"].sum(), 1)
    c.metric("상위 3개 챔피언 비중", f"{top3:.0%}", border=True,
             help="낮을수록 다양한 챔피언을 고르게 사용했다는 뜻입니다.")
    table = pool.head(20).assign(아이콘=lambda d: d["champion"].map(champ.icon),
                                 이름=lambda d: d["champion"].map(champ.name_ko))
    st.dataframe(table[["아이콘", "이름", "games", "win_rate", "kda", "kp"]]
                 .rename(columns={"games": "경기", "win_rate": "승률", "kda": "KDA", "kp": "킬 관여율"}),
                 hide_index=True, width="stretch", column_config={
                     "아이콘": st.column_config.ImageColumn(width="small"),
                     "승률": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                     "KDA": st.column_config.NumberColumn(format="%.2f"),
                     "킬 관여율": st.column_config.NumberColumn(format="percent")})

# ------------------------------------------------------------------ 선수 비교
with tab_compare:
    st.caption("두 선수의 LCK 시즌 기록을 같은 포지션 선수들 사이의 **백분위**(0~100)로 바꿔 비교합니다. "
               f"한 시즌 {MIN_GAMES}경기 이상 뛴 선수-시즌이 비교 기준입니다.")
    seasons = season_table()

    def pick(label: str, who: str, key: str):
        own = seasons[seasons["player"] == who]
        yrs = ["LCK 커리어 전체"] + sorted(own["year"].tolist(), reverse=True)
        return st.selectbox(label, yrs, key=f"{key}_{who}", format_func=lambda y: y if isinstance(y, str) else f"{y}년")

    def values_for(who: str, period) -> tuple[dict, str]:
        lck = pg[(pg["player"] == who) & (pg["scope"] == "LCK")]
        if not isinstance(period, str):
            lck = lck[lck["year"] == period]
        s = summarize(lck)
        s["survival"] = -s["deaths_pg"]
        return s, (lck["role"].mode().iat[0] if not lck.empty else role)

    left, right = st.columns(2)
    with left:
        st.markdown(f"**A: {display_name(player)}**")
        period_a = pick("A 기간", player, "pa")
    with right:
        same_role = idx[(idx["role"] == role) & (idx.index != player)]
        other = st.selectbox("B 선수", list(same_role.index) + [p for p in idx.index if p not in same_role.index
                                                                and p != player],
                             format_func=display_name, key=f"pb_{player}")
        period_b = pick("B 기간", other, "pbp")

    va, ra = values_for(player, period_a)
    vb, rb = values_for(other, period_b)
    if va["games"] == 0 or vb["games"] == 0:
        st.info("선택한 기간에 LCK 기록이 없습니다.")
    else:
        pa, pb = percentiles(va, ra), percentiles(vb, rb)
        keys = [k for k in RADAR_FEATURES if not (np.isnan(pa[k]) or np.isnan(pb[k]))]
        labels = [RADAR_FEATURES[k] for k in keys]
        fig = go.Figure()
        for name, pct, color in [(f"{display_name(player)} ({period_a})", pa, "#C89B3C"),
                                 (f"{display_name(other)} ({period_b})", pb, "#3B82F6")]:
            fig.add_trace(go.Scatterpolar(r=[pct[k] for k in keys] + [pct[keys[0]]], theta=labels + [labels[0]],
                                          fill="toself", name=name, line_color=color, opacity=0.6))
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], ticksuffix="")), height=450,
                          margin=dict(t=30, b=30), legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(fig, width="stretch")
        if ra != rb:
            st.caption(f"두 선수의 포지션이 달라({ROLE_KO.get(ra)} / {ROLE_KO.get(rb)}) 각자 자기 포지션 기준 백분위입니다.")

        fmt = {"games": "{:.0f}", "win_rate": "{:.0%}", "kda": "{:.2f}", "kp": "{:.0%}",
               "gold_share": "{:.1%}", "cs_min": "{:.1f}", "deaths_pg": "{:.2f}", "dmg_share": "{:.1%}"}
        names = {"games": "경기", "win_rate": "승률", "kda": "KDA", "kp": "킬 관여율", "gold_share": "골드 비중",
                 "cs_min": "분당 CS", "deaths_pg": "경기당 데스", "dmg_share": "딜량 비중"}
        comp = pd.DataFrame({
            "지표": list(names.values()),
            display_name(player): [fmt[k].format(va[k]) if pd.notna(va[k]) else "-" for k in names],
            display_name(other) + (" (B)" if display_name(other) == display_name(player) else ""):
                [fmt[k].format(vb[k]) if pd.notna(vb[k]) else "-" for k in names],
        })
        st.dataframe(comp, hide_index=True, width="stretch")
        st.caption("생존력 = 경기당 데스가 적을수록 높음. 딜량 비중은 두 선수 모두 2020년 이후 기록이 있을 때만 표시됩니다.")

# ------------------------------------------------------------------ 플레이 유형
with tab_style:
    clusters, profiles = style_clusters()
    pool = clusters[clusters["role"] == role]
    own = pool[pool["player"] == player].sort_values("year")
    st.caption(
        f"LCK {ROLE_KO.get(role)} 선수-시즌 {len(pool)}개(한 시즌 {MIN_GAMES}경기 이상)를 "
        f"{', '.join(STYLE_FEATURES.values())} 6개 지표로 표준화한 뒤 KMeans로 4개 유형으로 나눴습니다. "
        "유형 이름은 각 군집의 평균 특징과 가장 잘 맞는 이름을 자동으로 붙인 것입니다.")
    if own.empty:
        st.info(f"이 선수는 LCK에서 한 시즌 {MIN_GAMES}경기 이상 뛴 기록이 없어 유형 분석 대상이 아닙니다.")
    else:
        st.markdown("**시즌별 플레이 유형**")
        cols = st.columns(min(len(own), 6))
        for i, (_, r) in enumerate(own.tail(6).iterrows()):
            with cols[i].container(border=True):
                st.caption(f"{r['year']} · {r['team']}")
                st.markdown(f"<span style='color:{STYLE_COLOR[r['style']]};font-weight:700'>{r['style']}</span>",
                            unsafe_allow_html=True)

        left, right = st.columns([3, 2])
        with left:
            fig = px.scatter(pool, x="pc1", y="pc2", color="style", color_discrete_map=STYLE_COLOR,
                             hover_data={"player": True, "year": True, "team": True, "pc1": False, "pc2": False},
                             opacity=0.35)
            fig.add_trace(go.Scatter(x=own["pc1"], y=own["pc2"], mode="markers+text+lines",
                                     text=own["year"].astype(str), textposition="top center",
                                     marker=dict(size=12, color="black", symbol="star"),
                                     line=dict(color="black", width=1, dash="dot"),
                                     name=display_name(player)))
            fig.update_layout(height=420, margin=dict(t=30, b=10), legend_title=None,
                              title=dict(text="유형 지도 (주성분 분석으로 2차원 축소)", font_size=14),
                              xaxis_title="주성분 1", yaxis_title="주성분 2")
            st.plotly_chart(fig, width="stretch")
        with right:
            prof = profiles[profiles["role"] == role].set_index("style")[list(STYLE_FEATURES)]
            prof.columns = list(STYLE_FEATURES.values())
            fig = px.imshow(prof, color_continuous_scale="RdBu_r", zmin=-1.5, zmax=1.5, text_auto=".1f",
                            aspect="auto")
            fig.update_layout(height=420, margin=dict(t=30, b=10), coloraxis_showscale=False,
                              title=dict(text="유형별 평균 특징 (표준점수)", font_size=14))
            st.plotly_chart(fig, width="stretch")
        for name, (desc, _) in ARCHETYPES.items():
            if name in prof.index:
                st.markdown(f"- <span style='color:{STYLE_COLOR[name]};font-weight:700'>{name}</span>: {desc}",
                            unsafe_allow_html=True)

        st.markdown("**비슷한 플레이 스타일의 선수**")
        target = st.selectbox("기준 시즌", own["year"].tolist()[::-1], format_func=lambda y: f"{y}년")
        sim = similar_players(player, target, role)
        st.dataframe(sim.assign(선수=sim["player"].map(display_name))[["선수", "year", "team", "style", "distance"]]
                     .rename(columns={"year": "시즌", "team": "팀", "style": "유형", "distance": "거리"}),
                     hide_index=True, width="stretch", column_config={
                         "시즌": st.column_config.NumberColumn(format="%d"),
                         "거리": st.column_config.NumberColumn(format="%.2f", help="작을수록 비슷합니다.")})
