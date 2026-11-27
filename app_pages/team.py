"""🛡️ 팀 분석: 시즌·팀을 골라 당시 로스터, 성적, 챔피언, 국제전, 팀 역사를 본다."""
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import champions as champ
from utils.data_loader import has_data, load_players, load_rosters, load_schedule, load_tournaments
from utils.tournaments import standings_from_series, team_year_summary
from utils.teams import (ROLE_KO, ROLE_ORDER, current_status, display_name, lineage_of, season_aliases,
                         history_for, history_html, team_label, team_logo,
                         player_photo, rename_history, team_games, team_info, team_series)

TAB_KO = {"Finals": "결승", "Semifinals": "준결승", "Quarterfinals": "8강",
          "Final": "결승", "Semifinal": "준결승"}


def tab_ko(tab: str) -> str:
    if tab in TAB_KO:
        return TAB_KO[tab]
    if isinstance(tab, str) and tab.startswith("Round "):
        return tab.replace("Round ", "") + "라운드"
    return tab

def open_player(player: str) -> None:
    """선수 분석 페이지로 이동하면서 그 선수를 선택해 둔다."""
    st.session_state["player_pick"] = player
    st.switch_page("app_pages/player.py")


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

sel_games = lck_games[lck_games["page"].isin(pages)].copy()
sel_series = series[series["page"].isin(pages)].copy()


alias = season_aliases(sel_games)
for df in (sel_games, sel_series):
    df["team"] = df["team"].map(lambda t: alias.get(t, t))
    df["opponent"] = df["opponent"].map(lambda t: alias.get(t, t))
season_names = {}           # 표시 이름 → 그 기간에 실제로 쓰인 이름들
for raw, shown in alias.items():
    season_names.setdefault(shown, []).append(raw)


def standings(pages_sel) -> pd.DataFrame:
    """정규 시즌 순위표 (매치 승수 → 세트 득실 → 동률 팀 간 맞대결 → 세트 승수). 기간 중 바뀐 팀 이름은 합친다."""
    sch = load_schedule()
    sch = sch[sch["page"].isin(list(pages_sel)) & (sch["stage"] == "regular")].copy()
    for col in ("team1", "team2"):
        sch[col] = sch[col].map(lambda t: alias.get(t, t))
    t = standings_from_series(sch)
    return t[["순위", "매치승", "매치패", "세트승", "세트패", "세트득실"]] if not t.empty else t


table = standings(pages)
team_list = list(table.index) + sorted(set(sel_games["team"]) - set(table.index))
team = c3.selectbox("팀", team_list, index=None, placeholder="팀을 선택하세요", format_func=team_label,
                    help="정규 시즌 순위 순서로 정렬되어 있습니다.")

if team is None:
    st.info("👆 연도와 스플릿을 고른 뒤 **팀**을 선택하면 분석 결과가 나타납니다.")
    st.stop()

tg = sel_games[sel_games["team"] == team]
ts = sel_series[sel_series["team"] == team]
info = team_info()
names = lineage_of(team)

# ------------------------------------------------------------------ 헤더
h1, h2 = st.columns([1, 8])
if team in info.index and isinstance(info.at[team, "logo"], str):
    h1.image(info.at[team, "logo"], width=72)
sub = f"{year}년 {split}"
used = season_names.get(team, [team])
if len(used) > 1:
    raw = lck_games[lck_games["page"].isin(pages)]
    first = {n: raw.loc[raw["team"] == n, "datetime_kst"].min() for n in used}
    sub += f" · 이 기간 중 이름 변경: {' → '.join(sorted(used, key=first.get))}"
latest, disbanded = current_status(team)
if latest != team:
    sub += f" · 현재 팀 이름: **{team_label(latest)}**"
elif disbanded:
    sub += " · 해체된 팀"
h2.markdown(f"## {team_label(team)}\n{sub}")

tab_overview, tab_roster, tab_matches, tab_champs, tab_intl, tab_history = st.tabs(
    ["📋 개요", "👥 로스터", "📈 경기 기록", "🏆 챔피언", "🌏 국제전", "🕰️ 팀 역사"])

# ------------------------------------------------------------------ 개요
with tab_overview:
    sets_w, sets_n = int(tg["win"].sum()), len(tg)
    note = dict(delta_color="off", delta_arrow="off", border=True)   # 보조 설명은 화살표 없이 회색으로
    m = st.columns(3)
    m[0].metric("매치 전적 (승-패)", f"{int(ts['win'].sum())}-{int((~ts['win']).sum())}", border=True)
    m[1].metric("세트 승률", f"{sets_w / sets_n:.0%}" if sets_n else "-",
                f"{sets_w}승 {sets_n - sets_w}패", **note)
    m[2].metric("평균 경기 시간", f"{tg['gamelength'].mean():.1f}분" if sets_n else "-", border=True)

    ranks, results = team_year_summary(team, int(year))
    picked = None if split == "시즌 전체" else (split if split.startswith("LCK") else f"LCK {split}")

    def box(title: str, lines: list[str]) -> str:
        body = "".join(lines) or "<div style='opacity:0.6'>기록 없음</div>"
        return (f"<div style='border:1px solid rgba(128,128,128,0.22);border-radius:10px;padding:10px 14px;"
                f"height:100%'><div style='font-size:0.8rem;opacity:0.7;margin-bottom:6px'>{title}</div>{body}</div>")

    def line(label: str, value: str, strong: bool, icon: str = "") -> str:
        return (f"<div style='display:flex;justify-content:space-between;gap:12px;padding:3px 0;"
                f"{'' if strong else 'opacity:0.55;'}'><span>{label}</span>"
                f"<b>{icon}{value}</b></div>")

    def short_label(lbl: str) -> str:            # 'LCK Spring' → 'Spring', 'LCK Cup 그룹 배틀'·'LCK'는 그대로
        return lbl.replace("LCK ", "", 1) if lbl in ("LCK Spring", "LCK Summer") else lbl

    def is_picked(lbl: str) -> bool:
        return picked is None or lbl == picked or (picked == "LCK Cup" and lbl.startswith("LCK Cup"))

    rank_lines = [line(short_label(lbl), txt, is_picked(lbl)) for lbl, txt in ranks]
    medal = {"우승": "🏆 ", "준우승": "🥈 ", "3위": "🥉 "}
    result_lines = [line(lbl, res, picked in (None, lbl), medal.get(res, "")) for lbl, res in results]
    b1, b2 = st.columns([2, 3])
    b1.markdown(box("정규 시즌 순위", rank_lines), unsafe_allow_html=True)
    b2.markdown(box(f"{year}년 대회별 성적", result_lines), unsafe_allow_html=True)
    st.caption("대회별 성적은 고른 스플릿과 상관없이 그 해 전체(LCK·LCK Cup·First Stand·MSI·EWC·Worlds)를 "
               "시간 순으로 보여줍니다. 스플릿을 고르면 해당 줄이 강조됩니다.")

    left, right = st.columns(2)
    with left:
        st.markdown("**진영별 승률**")
        side = tg.groupby("side")["win"].agg(["mean", "size"]).reindex(["Blue", "Red"])
        fig = px.bar(x=["블루", "레드"], y=side["mean"].fillna(0),
                     text=[f"{v:.0%} ({int(n) if pd.notna(n) else 0}경기)" for v, n in
                           zip(side["mean"].fillna(0), side["size"])],
                     color=["블루", "레드"], color_discrete_map={"블루": "#3B82F6", "레드": "#EF4444"})
        fig.update_traces(width=0.32)          # 막대를 얇게
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
        tview = table.reset_index().rename(columns={"team": "팀"})
        tview.insert(1, "로고", tview["팀"].map(team_logo))
        tview["팀"] = tview["팀"].map(team_label)
        st.dataframe(tview.style.apply(
            lambda r: ["background-color: rgba(200,155,60,0.25)" if r["팀"] == team_label(team) else "" for _ in r],
            axis=1), width="stretch", hide_index=True,
            column_config={"로고": st.column_config.ImageColumn(width="small")})
        st.caption("정규 시즌 시리즈 결과 기준 (매치 승수 → 세트 득실 → 동률 팀 간 맞대결 → 세트 승수).")

# ------------------------------------------------------------------ 로스터
with tab_roster:
    rosters = load_rosters()
    roster = rosters[rosters["page"].isin(pages) & rosters["team"].isin(used)]
    players = load_players()
    played = players[players["page"].isin(pages) & players["team"].isin(used)]
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
                if st.button("선수 분석 →", key=f"go_{p['player']}", width="stretch"):
                    open_player(p["player"])

        subs = stat[~stat.index.isin(starters.index)]
        if not subs.empty:
            st.markdown("**교체 출전 선수** (줄을 누르면 선수 분석으로 이동)")
            subs = subs.reset_index(drop=True)
            picked_sub = st.dataframe(subs.assign(포지션=subs["role"].map(lambda r: ROLE_KO.get(r, r)),
                                                  선수=subs["player"].map(display_name))
                                      [["선수", "포지션", "경기", "KDA", "승률"]],
                                      hide_index=True, width="stretch", on_select="rerun",
                                      selection_mode="single-row", key=f"subs_{team}_{year}_{split}",
                                      column_config={"KDA": st.column_config.NumberColumn(format="%.2f"),
                                                     "승률": st.column_config.NumberColumn(format="percent")})
            if picked_sub and picked_sub.selection.rows:
                open_player(subs.loc[picked_sub.selection.rows[0], "player"])

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
            view = view.assign(로고=view["opponent"].map(team_logo), 상대=view["opponent"].map(team_label))
            st.dataframe(view[["날짜", "로고", "상대", "스코어", "결과", "단계"]],
                         hide_index=True, width="stretch", height=400,
                         column_config={"로고": st.column_config.ImageColumn(width="small")})
        with right:
            st.markdown("**상대 전적**")
            h2h = ts.groupby("opponent").agg(매치승=("win", "sum"), 매치=("win", "size"),
                                             세트승=("score", "sum"), 세트패=("opp_score", "sum"))
            h2h["매치패"] = h2h["매치"] - h2h["매치승"]
            h2h["승률"] = h2h["세트승"] / (h2h["세트승"] + h2h["세트패"])     # 세트 기준 승률
            h2h = h2h.sort_values(["매치승", "승률"], ascending=False).reset_index()
            h2h.insert(0, "로고", h2h["opponent"].map(team_logo))
            h2h["상대"] = h2h["opponent"].map(team_label)
            st.dataframe(h2h[["로고", "상대", "매치승", "매치패", "세트승", "세트패", "승률"]],
                         hide_index=True, width="stretch", height=400, column_config={
                             "로고": st.column_config.ImageColumn(width="small"),
                             "승률": st.column_config.NumberColumn(format="percent", help="세트 기준 승률")})

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
        year_results = dict(team_year_summary(team, int(year))[1])
        medal = {"우승": "🏆 ", "준우승": "🥈 ", "3위": "🥉 "}
        tour_order = intl.groupby("league_short")["datetime_kst"].min().sort_values().index   # 열린 순서대로
        for tour in tour_order:
            g = intl[intl["league_short"] == tour]
            s = intl_s[intl_s["league_short"] == tour].sort_values("datetime_kst")
            result = year_results.get(tour, "-")
            last_opp = ""
            if not s.empty and result not in ("우승", "-"):
                last = s.iloc[-1]                      # 탈락(또는 준우승)이면 마지막 상대
                last_opp = (f"{team_label(last['opponent'])} "
                            f"({int(last['score'])}:{int(last['opp_score'])} {'승' if last['win'] else '패'})")
            rows.append({"대회": tour, "세트 전적": f"{int(g['win'].sum())}승 {int((~g['win']).sum())}패",
                         "세트 승률": g["win"].mean(), "최종 결과": medal.get(result, "") + result,
                         "마지막 상대": last_opp})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"세트 승률": st.column_config.ProgressColumn(
                         format="percent", min_value=0, max_value=1)})

        st.markdown("**상대한 해외 팀**")
        opp = intl.groupby("opponent").agg(세트=("win", "size"), 승=("win", "sum")).reset_index()
        opp["지역"] = opp["opponent"].map(lambda t: info.at[t, "region"] if t in info.index else "")
        opp["패"] = opp["세트"] - opp["승"]
        opp = opp.assign(로고=opp["opponent"].map(team_logo), 상대=opp["opponent"].map(team_label))
        st.dataframe(opp[["로고", "상대", "지역", "승", "패"]].sort_values("승", ascending=False),
                     hide_index=True, width="stretch",
                     column_config={"로고": st.column_config.ImageColumn(width="small")})

# ------------------------------------------------------------------ 팀 역사
with tab_history:
    # 이름별 시작 날짜: 이름 변경 기록의 날짜, 없으면 그 이름으로 치른 첫 경기 날짜
    hist = rename_history(team)
    lineage_games = games[games["team"].isin(names)]
    starts = {}
    for n in names:
        renamed = hist.loc[hist["new_name"] == n, "date"].dropna()
        played = lineage_games.loc[lineage_games["team"] == n, "datetime_kst"]
        candidates = [d for d in [renamed.min() if not renamed.empty else None,
                                  played.min() if not played.empty else None] if d is not None]
        if candidates:
            starts[n] = min(candidates)
    flow = sorted(starts.items(), key=lambda kv: kv[1])
    st.markdown("**팀 이름 변화**")
    curated = history_for(team)
    if curated:
        st.markdown(history_html(curated), unsafe_allow_html=True)
        st.caption("팀 이름 변천사는 직접 정리한 자료(data/team_history.json) 기준입니다. "
                   "여러 줄이 하나로 모이는 곳은 두 팀이 합쳐진 시점입니다.")
    elif len(flow) > 1:
        chips = []
        for i, (n, d) in enumerate(flow):
            last = i == len(flow) - 1
            chips.append(
                f"<div style='display:inline-flex;flex-direction:column;align-items:center;padding:8px 14px;"
                f"border-radius:10px;border:1px solid {'#C89B3C' if last else 'rgba(128,128,128,0.35)'};"
                f"background:{'rgba(200,155,60,0.12)' if last else 'transparent'}'>"
                f"<span style='font-weight:700'>{team_label(n)}</span>"
                f"<span style='font-size:0.78rem;opacity:0.7'>{d:%Y.%m.%d}&#126;</span></div>")
        arrow = "<span style='font-size:1.3rem;opacity:0.5;margin:0 6px'>→</span>"
        st.markdown(f"<div style='display:flex;flex-wrap:wrap;align-items:center;gap:4px'>"
                    f"{arrow.join(chips)}</div>", unsafe_allow_html=True)
        st.caption("날짜는 Leaguepedia 이름 변경 기록 기준이며, 기록이 없으면 그 이름으로 치른 첫 경기 날짜입니다.")
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
