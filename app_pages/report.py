"""📄 리포트: 팀 시즌 / 선수 커리어 분석을 미리 보고 Excel·PDF 파일로 내려받는다."""
import re

import pandas as pd
import streamlit as st

from utils.data_loader import has_data, load_tournaments
from utils.players import player_games
from utils.teams import ROLE_KO, display_name, season_aliases, team_games
from utils.teams import with_logos

st.title("📄 리포트")
st.caption("팀 시즌 리포트나 선수 커리어 리포트를 만들어 미리 보고, Excel(표 정리용)이나 "
           "PDF(그래프 포함, 인쇄·공유용) 파일로 내려받을 수 있습니다.")

if not has_data():
    st.warning("아직 수집된 데이터가 없습니다.")
    st.stop()

kind = st.radio("리포트 종류", ["🛡️ 팀 시즌 리포트", "👤 선수 커리어 리포트"], horizontal=True)


@st.cache_data(show_spinner=False)
def build_team(year: int, split: str, team: str) -> tuple[dict, bytes, bytes]:
    from utils.report import team_report, to_excel, to_pdf
    data = team_report(year, split, team)
    return data, to_excel(data), to_pdf(data)


@st.cache_data(show_spinner=False)
def build_player(player: str) -> tuple[dict, bytes, bytes]:
    from utils.report import player_report, to_excel, to_pdf
    data = player_report(player)
    return data, to_excel(data), to_pdf(data)


def safe(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", name).strip("_")


data = None
with st.container(border=True):
    if kind.startswith("🛡️"):
        tours = load_tournaments()
        tg = team_games()
        lck = tg[tg["scope"] == "LCK"]
        c1, c2, c3 = st.columns([1, 1, 2])
        year = c1.selectbox("연도", sorted(lck["year"].dropna().unique().astype(int), reverse=True),
                            format_func=lambda y: f"{y}년")
        yt = tours[(tours["scope"] == "LCK") & (tours["year"] == year)].sort_values("date_start")
        split = c2.selectbox("스플릿", ["시즌 전체"] + list(dict.fromkeys(yt["split"].replace("", "기타"))))
        pages = yt["page"] if split == "시즌 전체" else yt.loc[yt["split"].replace("", "기타") == split, "page"]
        season = lck[lck["page"].isin(pages)]
        alias = season_aliases(season)
        teams = sorted(set(alias.values()))
        team = c3.selectbox("팀", teams, index=None, placeholder="팀을 선택하세요")
        if team:
            with st.spinner("리포트를 만드는 중입니다..."):
                data, xlsx, pdf = build_team(int(year), split, team)
            base = f"LCKInsight_팀_{safe(team)}_{year}_{safe(split)}"
    else:
        pg = player_games(include_foreign=True)
        idx = pg[pg["scope"].isin(["LCK", "INTL"])].groupby("player").agg(
            games=("game_id", "size"), role=("role", lambda s: s.mode().iat[0]), team=("team", "last")) \
            .sort_values("games", ascending=False)
        player = st.selectbox(
            "선수", list(idx.index), index=None, placeholder="선수를 선택하거나 이름을 입력하세요",
            format_func=lambda p: f"{display_name(p)} · {ROLE_KO.get(idx.at[p, 'role'], '')} · {idx.at[p, 'team']}")
        if player:
            with st.spinner("리포트를 만드는 중입니다..."):
                data, xlsx, pdf = build_player(player)
            base = f"LCKInsight_선수_{safe(display_name(player))}"

if data is None:
    st.info("👆 리포트 대상을 선택하면 미리보기와 다운로드 버튼이 나타납니다.")
    st.stop()

# ------------------------------------------------------------------ 다운로드
d1, d2, _ = st.columns([1, 1, 2])
d1.download_button("📊 Excel로 받기", xlsx, file_name=f"{base}.xlsx", width="stretch", type="primary",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
d2.download_button("📑 PDF로 받기", pdf, file_name=f"{base}.pdf", mime="application/pdf", width="stretch")
st.caption("Excel: 요약과 표를 시트별로 정리 · PDF: 요약, 그래프, 표를 한 문서로 정리 (A4)")

# ------------------------------------------------------------------ 미리보기
st.markdown(f"### {data['title']}")
summary = data["summary"]
cards = "".join(
    f"<div style='border:1px solid rgba(128,128,128,0.25);border-radius:10px;padding:10px 12px'>"
    f"<div style='font-size:0.75rem;opacity:0.65'>{k}</div><div style='font-weight:700'>{v}</div></div>"
    for k, v in summary.items())
st.markdown(f"<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px'>"
            f"{cards}</div>", unsafe_allow_html=True)

from utils.report import charts  # noqa: E402  (matplotlib는 리포트를 만들 때만 불러온다)

st.markdown("")
cols = st.columns(2)
for col, (title, png) in zip(cols, charts(data)):
    col.markdown(f"**{title}**")
    col.image(png.getvalue(), width="stretch")

percent_cols = {"승률", "킬 관여율"}
for name, df in data["sections"]:
    if isinstance(df, pd.DataFrame) and not df.empty:
        with st.expander(f"{name} ({len(df)}행)", expanded=False):
            dv, logo_cfg = with_logos(df)
            st.dataframe(dv, hide_index=True, width="stretch", column_config={
                **{c: st.column_config.NumberColumn(format="percent") for c in dv.columns if c in percent_cols},
                **logo_cfg})
