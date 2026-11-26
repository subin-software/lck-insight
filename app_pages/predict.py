"""🔮 승부 예측: 두 팀(과 챔피언 조합)을 고르면 머신러닝 모델이 승리 확률을 예측한다."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils import champions as champ
from utils.data_loader import has_data, load_champions
from utils.model import (FEATURES, TEST_FROM, champ_pool, champ_rate, contributions, evaluate,
                         final_model, importances, predict, series_prob, team_state)
from utils.teams import team_games, team_info

A_COLOR, B_COLOR = "#C89B3C", "#3B82F6"

st.title("🔮 승부 예측")
st.caption("두 팀을 고르면 머신러닝 모델이 한 세트를 이길 확률을 예측합니다. 양 팀 챔피언 조합을 넣으면 "
           "조합까지 반영하고, 챔피언을 바꿨을 때 승률이 어떻게 달라지는지도 비교할 수 있습니다.")

if not has_data():
    st.warning("아직 수집된 데이터가 없습니다.")
    st.stop()

with st.spinner("모델을 준비하는 중입니다 (처음 한 번만 걸립니다)..."):
    _, best_name, _ = final_model()
    report = evaluate()

tab_predict, tab_perf, tab_how = st.tabs(["🔮 예측하기", "📊 모델 성능", "ℹ️ 예측 방법"])

# ------------------------------------------------------------------ 예측하기
with tab_predict:
    tg = team_games()
    last = tg["datetime_kst"].max()
    show_all = st.toggle("과거 팀도 목록에 보이기", value=False,
                         help="끄면 최근 1년 안에 경기한 팀만 보입니다.")
    pool = tg if show_all else tg[tg["datetime_kst"] >= last - pd.Timedelta(days=365)]
    teams = sorted(pool["team"].unique(), key=lambda t: -team_state(t)["elo"])
    info = team_info()

    def label(t: str) -> str:
        region = info.at[t, "region"] if t in info.index else ""
        return f"{t} · {region} · Elo {team_state(t)['elo']:.0f}"

    c1, c2, c3 = st.columns([5, 2, 5])
    team_a = c1.selectbox("A팀", teams, index=None, placeholder="A팀을 선택하세요", format_func=label)
    side = c2.radio("A팀 진영", ["블루", "레드"], horizontal=False)
    team_b = c3.selectbox("B팀", [t for t in teams if t != team_a], index=None,
                          placeholder="B팀을 선택하세요", format_func=label)

    champs = load_champions().sort_values("name_ko")
    champ_options = list(champs["champion"])
    champ_label = dict(zip(champs["champion"], champs["name_ko"]))
    with st.expander("🧩 챔피언 조합 넣기 (선택)", expanded=False):
        d1, d2 = st.columns(2)
        picks_a = d1.multiselect("A팀 챔피언 (최대 5개)", champ_options, max_selections=5,
                                 format_func=lambda c: champ_label.get(c, c))
        picks_b = d2.multiselect("B팀 챔피언 (최대 5개)", [c for c in champ_options if c not in picks_a],
                                 max_selections=5, format_func=lambda c: champ_label.get(c, c))
        st.caption("챔피언을 넣지 않으면 조합 요인은 중립(50%)으로 계산됩니다.")

    if team_a is None or team_b is None:
        st.info("👆 **A팀과 B팀**을 선택하면 예측 결과가 나타납니다.")
    else:
        a_blue = side == "블루"
        p, feats = predict(team_a, team_b, a_blue, picks_a, picks_b)

        fig = go.Figure()
        fig.add_bar(y=[""], x=[p], orientation="h", marker_color=A_COLOR, name=team_a,
                    text=f"{team_a} {p:.0%}", textposition="inside", insidetextanchor="start")
        fig.add_bar(y=[""], x=[1 - p], orientation="h", marker_color=B_COLOR, name=team_b,
                    text=f"{1 - p:.0%} {team_b}", textposition="inside", insidetextanchor="end")
        fig.update_layout(barmode="stack", height=110, showlegend=False, margin=dict(t=5, b=5, l=5, r=5),
                          xaxis=dict(visible=False, range=[0, 1]), yaxis=dict(visible=False),
                          font=dict(size=16, color="white"))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        m = st.columns(3)
        m[0].metric(f"{team_a} 세트 승리 확률", f"{p:.1%}", border=True)
        m[1].metric("3판 2선승(Bo3) 승리 확률", f"{series_prob(p, 3):.1%}", border=True)
        m[2].metric("5판 3선승(Bo5) 승리 확률", f"{series_prob(p, 5):.1%}", border=True)
        st.caption("시리즈 확률은 세트마다 같은 확률로 이긴다고 가정해 계산한 값입니다.")

        left, right = st.columns(2)
        with left:
            st.markdown("**판단 근거** (오른쪽일수록 A팀에 유리)")
            contrib = contributions(feats)
            if contrib is not None:
                cdf = contrib.reset_index()
                cdf.columns = ["요인", "기여도"]
                cdf["유리한 팀"] = cdf["기여도"].map(lambda v: team_a if v >= 0 else team_b)
                fig = px.bar(cdf, x="기여도", y="요인", orientation="h", color="유리한 팀",
                             color_discrete_map={team_a: A_COLOR, team_b: B_COLOR})
                fig.update_layout(height=280, margin=dict(t=10, b=10), legend_title=None, yaxis_title=None,
                                  xaxis_title="기여도 (로그 오즈)")
                st.plotly_chart(fig, width="stretch")
        with right:
            sa, sb = team_state(team_a), team_state(team_b)
            rows = [("Elo 레이팅", f"{sa['elo']:.0f}", f"{sb['elo']:.0f}"),
                    ("최근 10세트 승률", f"{sa['form']:.0%}", f"{sb['form']:.0%}"),
                    ("상대 전적 (최근 20세트)", f"{feats['h2h']:.0%}", f"{1 - feats['h2h']:.0%}"),
                    ("진영", side, "레드" if a_blue else "블루")]
            if picks_a or picks_b:
                ca = sum(champ_rate(c) for c in picks_a) / len(picks_a) if picks_a else 0.5
                cb = sum(champ_rate(c) for c in picks_b) / len(picks_b) if picks_b else 0.5
                rows.append(("챔피언 최근 승률 평균", f"{ca:.1%}", f"{cb:.1%}"))
            st.markdown("**입력된 특성 값**")
            st.dataframe(pd.DataFrame(rows, columns=["항목", team_a, team_b]), hide_index=True, width="stretch")

        # ---------------------------------------------------- 조합 비교
        st.markdown("#### 🔄 챔피언을 바꾸면?")
        if not picks_a:
            st.caption("A팀 챔피언을 1개 이상 넣으면, 한 챔피언을 다른 챔피언으로 바꿨을 때 "
                       "예상 승률이 어떻게 달라지는지 비교할 수 있습니다.")
        else:
            slot = st.selectbox("바꿔 볼 A팀 챔피언", picks_a, format_func=lambda c: champ_label.get(c, c))
            candidates = [c for c in champ_pool() if c not in picks_a and c not in picks_b]
            rows = []
            for c in candidates:
                new = [c if x == slot else x for x in picks_a]
                q, _ = predict(team_a, team_b, a_blue, new, picks_b)
                rows.append({"아이콘": champ.icon(c), "챔피언": champ_label.get(c, c), "예상 승률": q, "변화": (q - p) * 100,
                             "최근 승률": champ_rate(c)})
            alt = pd.DataFrame(rows).sort_values("예상 승률", ascending=False)
            best, worst = alt.head(8), alt.tail(5).iloc[::-1]
            l2, r2 = st.columns(2)
            cfg = {"아이콘": st.column_config.ImageColumn(width="small"),
                   "예상 승률": st.column_config.NumberColumn(format="percent"),
                   "변화": st.column_config.NumberColumn(format="%+.1f%%p", help="현재 조합 대비 예상 승률 변화 (%p)"),
                   "최근 승률": st.column_config.NumberColumn(format="percent")}
            l2.markdown(f"**{champ_label.get(slot, slot)} 대신 쓰면 좋은 챔피언**")
            l2.dataframe(best, hide_index=True, width="stretch", column_config=cfg)
            r2.markdown("**바꾸면 불리해지는 챔피언**")
            r2.dataframe(worst, hide_index=True, width="stretch", column_config=cfg)
            st.caption(f"후보: 최근 경기에서 충분히 쓰인 챔피언 {len(candidates)}개. "
                       "챔피언 요인은 팀 실력(Elo)보다 영향이 작아 변화 폭이 크지 않습니다.")

# ------------------------------------------------------------------ 모델 성능
with tab_perf:
    st.markdown(f"**평가 방법**: {TEST_FROM.year - 1}년까지 {report['n_train']:,}세트로 학습하고, "
                f"{TEST_FROM.year}년 이후 {report['n_test']:,}세트로 평가했습니다 (미래 경기로 평가하는 시간 순 분할).")
    rows = [{"방법": name, "정확도": v["정확도"], "로그 손실": v["로그 손실"], "AUC": v["AUC"]}
            for name, v in report["models"].items()]
    rows += [{"방법": f"기준선: {k}", "정확도": v} for k, v in report["baseline"].items()]
    perf = pd.DataFrame(rows)
    st.dataframe(perf, hide_index=True, width="stretch", column_config={
        "정확도": st.column_config.ProgressColumn(format="percent", min_value=0.5, max_value=0.75),
        "로그 손실": st.column_config.NumberColumn(format="%.3f", help="낮을수록 확률 예측이 정확합니다."),
        "AUC": st.column_config.NumberColumn(format="%.3f", help="1에 가까울수록 승패를 잘 구분합니다.")})
    st.success(f"최종 모델: **{best_name}** (확률의 질을 나타내는 로그 손실이 가장 낮은 모델)")

    left, right = st.columns(2)
    with left:
        cm = report["models"][best_name]["confusion"]
        fig = px.imshow(cm, text_auto=True, color_continuous_scale="Blues",
                        x=["패배 예측", "승리 예측"], y=["실제 패배", "실제 승리"])
        fig.update_layout(height=320, margin=dict(t=30, b=10), coloraxis_showscale=False,
                          title=dict(text=f"혼동 행렬 ({best_name}, 블루 진영 팀 기준)", font_size=14))
        st.plotly_chart(fig, width="stretch")
    with right:
        imp = importances()
        fig = px.bar(x=imp.values, y=imp.index, orientation="h")
        fig.update_traces(marker_color=A_COLOR)
        fig.update_layout(height=320, margin=dict(t=30, b=10), xaxis_title="중요도", yaxis_title=None,
                          title=dict(text="특성 중요도 (표준화 계수 크기)", font_size=14))
        st.plotly_chart(fig, width="stretch")
    st.caption("프로 경기는 실력 차이가 크지 않은 팀끼리 맞붙는 경우가 많아, 공개 데이터만으로는 "
               "정확도 60%대 후반이 현실적인 수준입니다.")

# ------------------------------------------------------------------ 예측 방법
with tab_how:
    st.markdown("""
**1. 특성 만들기** — 2016년 이후 LCK·국제전 모든 세트를 시간 순으로 훑으면서, **그 경기 직전까지의 정보만으로**
다음 값을 계산합니다. 경기 결과를 미리 알고 계산하면(데이터 누수) 성능이 부풀려지기 때문입니다.
""")
    st.table(pd.DataFrame({
        "특성": list(FEATURES.values()),
        "계산 방법": [
            "모든 팀 1500점에서 시작, 세트마다 승패로 점수 갱신(K=24). 새 시즌엔 평균 쪽으로 25% 회귀. "
            "국제전 경기로 리그 간 실력 차이도 반영",
            "두 팀의 최근 10세트 승률 차이",
            "A팀이 블루 진영이면 1 (블루 진영 승률이 약간 높음)",
            "고른 챔피언들의 최근 승률 평균 차이. 120일마다 가중치가 절반으로 줄고, 표본이 적으면 50% 쪽으로 보정",
            "두 팀의 최근 20세트 상대 전적 승률",
        ]}))
    st.markdown("""
**2. 모델 학습** — 로지스틱 회귀와 랜덤 포레스트를 학습합니다. 같은 경기를 반대 팀 시점으로 뒤집은 데이터도 넣어
진영과 팀 순서에 따른 치우침을 없앴습니다.

**3. 모델 선택** — 2025년 이후 경기로 평가해 확률 예측이 더 정확한(로그 손실이 낮은) 모델을 고릅니다.

**4. 예측** — 선택한 두 팀의 현재 상태(마지막 경기 기준)로 특성을 만들어 확률을 계산합니다.
A/B 순서를 바꿔도 결과가 정확히 반대가 되도록 양쪽 시점의 예측을 평균합니다.

**한계** — 선수 교체, 패치 변화, 경기 당일 컨디션은 반영하지 못합니다. 이름이 바뀐 팀은 하나의 팀으로 이어서 계산하지만,
로스터가 크게 바뀌어도 레이팅은 이어집니다.
""")
