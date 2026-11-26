"""📊 메타 분석: 챔피언 픽·밴 경향, 패치별 변화, 팀별 선호 챔피언."""
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import champions as champ
from utils.data_loader import has_data
from utils.meta import champion_table, filtered_games, patch_key, patch_trend, team_champion_matrix
from utils.teams import ROLE_KO, ROLE_ORDER, team_games

st.title("📊 메타 분석")
st.caption("연도·대회·패치를 고르면 그 기간에 어떤 챔피언이 많이 뽑히고 금지(밴)됐는지, 승률은 어땠는지, "
           "패치에 따라 메타가 어떻게 바뀌었는지 보여줍니다.")

if not has_data():
    st.warning("아직 수집된 데이터가 없습니다.")
    st.stop()

# ------------------------------------------------------------------ 필터
tg_all = team_games()
c1, c2, c3 = st.columns([1, 1, 2])
years = sorted(tg_all.loc[tg_all["year"] >= 2016, "year"].dropna().unique().astype(int), reverse=True)
year = c1.selectbox("연도", years, format_func=lambda y: f"{y}년")
scope_label = c2.radio("대회", ["LCK", "국제전", "전체"], horizontal=True)
scopes = {"LCK": ["LCK"], "국제전": ["INTL"], "전체": ["LCK", "INTL"]}[scope_label]
base = filtered_games(scopes, year, None)
patches = sorted(base["patch"].dropna().unique(), key=patch_key)
sel_patches = c3.multiselect("패치 (비우면 전체)", patches, placeholder="전체 패치")
tg = filtered_games(scopes, year, sel_patches or None)

if tg.empty:
    st.info("조건에 맞는 경기가 없습니다.")
    st.stop()

table = champion_table(tg)
table.insert(0, "이름", table.index.map(champ.name_ko))
table.insert(0, "아이콘", table.index.map(champ.icon))
n_games = tg["game_id"].nunique()
blue = tg[tg["side"] == "Blue"]["win"].mean()

m = st.columns(4)
m[0].metric("세트 수", f"{n_games:,}", border=True)
m[1].metric("등장한 챔피언", f"{(table['픽'] > 0).sum()}개", border=True)
m[2].metric("최다 등장", table.iloc[0]["이름"], f"등장률 {table.iloc[0]['등장률']:.0%}",
            delta_color="off", delta_arrow="off", border=True)
m[3].metric("블루 진영 승률", f"{blue:.1%}", border=True)

tab_rank, tab_trend, tab_team = st.tabs(["🏆 챔피언 순위", "📈 패치별 추이", "🔥 팀별 선호 챔피언"])

# ------------------------------------------------------------------ 챔피언 순위
with tab_rank:
    f1, f2 = st.columns([2, 3])
    role = f1.selectbox("포지션", ["전체"] + list(ROLE_ORDER), format_func=lambda r: ROLE_KO.get(r, r))
    min_picks = f2.slider("승률 계산 최소 픽 수", 1, 30, 5,
                          help="픽이 너무 적은 챔피언은 승률이 우연에 크게 좌우되므로 이 값보다 적으면 승률을 숨깁니다.")
    view = table if role == "전체" else table[table["포지션"] == role]
    view = view.assign(승률=view["승률"].where(view["픽"] >= min_picks),
                       포지션=view["포지션"].map(lambda r: ROLE_KO.get(r, r)))
    st.dataframe(view[["아이콘", "이름", "포지션", "픽", "밴", "픽률", "밴률", "등장률", "승률"]],
                 hide_index=True, width="stretch", height=420, column_config={
                     "아이콘": st.column_config.ImageColumn(width="small"),
                     "픽": st.column_config.NumberColumn(format="%d"),
                     "밴": st.column_config.NumberColumn(format="%d"),
                     "픽률": st.column_config.NumberColumn(format="percent"),
                     "밴률": st.column_config.NumberColumn(format="percent"),
                     "등장률": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1,
                                                            help="픽 또는 밴된 세트의 비율"),
                     "승률": st.column_config.NumberColumn(format="percent")})
    st.caption("등장률 = (픽 + 밴) ÷ 세트 수. 프로 경기에서 그 챔피언이 얼마나 '신경 쓰였는지'를 나타냅니다.")

    plot = view[(view["픽"] >= min_picks) & view["승률"].notna()].head(40)
    if not plot.empty:
        fig = px.scatter(plot, x="등장률", y="승률", size="픽", color="포지션", text="이름",
                         hover_data={"픽": True, "밴": True, "등장률": ":.0%", "승률": ":.0%"})
        fig.update_traces(textposition="top center", textfont_size=10)
        fig.add_hline(y=0.5, line_dash="dot", line_color="gray")
        fig.update_layout(height=480, margin=dict(t=40, b=10), legend_title=None,
                          xaxis_tickformat=".0%", yaxis_tickformat=".0%",
                          title=dict(text="등장률 vs 승률 (등장률 상위 40개)", font_size=14))
        st.plotly_chart(fig, width="stretch")
        st.caption("오른쪽 위: 많이 쓰이고 승률도 높은 핵심 챔피언 · 오른쪽 아래: 많이 쓰이지만 승률은 낮은 챔피언")

# ------------------------------------------------------------------ 패치별 추이
with tab_trend:
    year_tg = filtered_games(scopes, year, None)       # 추이는 연도 전체 패치로 본다
    year_patches = sorted(year_tg["patch"].dropna().unique(), key=patch_key)
    if len(year_patches) < 2:
        st.info("패치가 2개 이상이어야 추이를 볼 수 있습니다.")
    else:
        year_table = champion_table(year_tg)
        default = list(year_table.head(5).index)
        picks = st.multiselect("챔피언", list(year_table.index), default=default,
                               format_func=champ.name_ko, max_selections=8)
        if picks:
            trend = patch_trend(year_tg, picks)
            trend["챔피언"] = trend["champion"].map(champ.name_ko)
            left, right = st.columns(2)
            for col, metric in [(left, "등장률"), (right, "승률")]:
                fig = px.line(trend, x="패치", y=metric, color="챔피언", markers=True, hover_data=["경기 수"])
                fig.update_layout(height=360, margin=dict(t=40, b=10), legend_title=None, yaxis_tickformat=".0%",
                                  title=dict(text=f"패치별 {metric}", font_size=14))
                col.plotly_chart(fig, width="stretch")
            st.caption("한 패치의 경기 수가 적으면 값이 크게 출렁일 수 있습니다 (마우스를 올리면 경기 수가 보입니다).")

        # 떠오른 / 저문 챔피언: 연도 전반부 패치 vs 후반부 패치
        half = len(year_patches) // 2
        early = champion_table(year_tg[year_tg["patch"].isin(year_patches[:half])])["등장률"]
        late = champion_table(year_tg[year_tg["patch"].isin(year_patches[half:])])["등장률"]
        diff = (late.reindex(early.index.union(late.index), fill_value=0)
                - early.reindex(early.index.union(late.index), fill_value=0)).sort_values()
        st.markdown(f"**시즌 전반({year_patches[0]}~{year_patches[half - 1]}) → 후반({year_patches[half]}~"
                    f"{year_patches[-1]}) 등장률 변화**")
        up, down = st.columns(2)
        for col, data, title in [(up, diff.tail(6)[::-1], "📈 떠오른 챔피언"), (down, diff.head(6), "📉 저문 챔피언")]:
            col.markdown(title)
            col.dataframe(pd.DataFrame({"아이콘": data.index.map(champ.icon), "챔피언": data.index.map(champ.name_ko),
                                        "등장률 변화": data.values * 100}),
                          hide_index=True, width="stretch", column_config={
                              "아이콘": st.column_config.ImageColumn(width="small"),
                              "등장률 변화": st.column_config.NumberColumn(format="%+.0f%%p")})

# ------------------------------------------------------------------ 팀별 선호 챔피언
with tab_team:
    mat = team_champion_matrix(tg, top=15)
    if mat.empty:
        st.info("데이터가 없습니다.")
    else:
        mat = mat.loc[mat.sum(axis=1).sort_values(ascending=False).index].head(20)
        mat.columns = [champ.name_ko(c) for c in mat.columns]
        fig = px.imshow(mat, text_auto=True, color_continuous_scale="YlOrBr", aspect="auto")
        fig.update_layout(height=max(360, 28 * len(mat) + 120), margin=dict(t=40, b=10),
                          coloraxis_showscale=False, xaxis_title=None, yaxis_title=None,
                          title=dict(text="팀별 픽 횟수 (가장 많이 쓰인 챔피언 15개)", font_size=14))
        fig.update_xaxes(side="top", tickangle=-45)
        st.plotly_chart(fig, width="stretch")
        st.caption("같은 메타 안에서도 팀마다 선호하는 챔피언이 다릅니다. 진할수록 그 팀이 자주 고른 챔피언입니다.")
