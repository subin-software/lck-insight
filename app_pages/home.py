import streamlit as st

from utils.data_loader import load_update_log

st.title("🎮 LCK Insight")
st.subheader("데이터로 보는 LCK: 분석, 예측, 리포트")

st.markdown(
    """
LCK(League of Legends Champions Korea) 2016~2026 시즌과 국제 대회
(Worlds, MSI, First Stand, EWC) 경기 데이터를 바탕으로
팀·선수·챔피언을 분석하고, 경기 결과를 예측하고, 분석 리포트를 만들어 주는 웹앱입니다.
"""
)

st.markdown("### 주요 기능")
features = [
    ("📅 경기 일정", "월간 캘린더로 지난 경기 스코어와 예정 경기를 확인합니다."),
    ("🛡️ 팀 분석", "시즌과 팀을 고르면 당시 로스터, 성적, 팀 역사를 보여줍니다."),
    ("👤 선수 분석", "선수의 커리어 추이, 선수 비교, 플레이 유형 분류를 제공합니다."),
    ("📊 메타 분석", "챔피언별 픽률·밴률·승률과 패치별 변화를 분석합니다."),
    ("🌏 국제전", "LCK와 해외 리그의 상대 전적, 대회별 성적을 비교합니다."),
    ("🔮 승부 예측", "두 팀과 챔피언 조합을 고르면 승리 확률을 예측합니다."),
    ("📄 리포트", "선택한 팀·선수의 분석 결과를 Excel·PDF로 내려받습니다."),
]
cols = st.columns(2)
for i, (name, desc) in enumerate(features):
    with cols[i % 2]:
        st.markdown(f"**{name}**  \n{desc}")

st.markdown("### 사용 방법")
st.markdown(
    """
1. 왼쪽 메뉴에서 원하는 페이지를 선택합니다.
2. 각 페이지 상단에서 시즌, 팀, 선수 등을 고릅니다.
3. 결과 표와 그래프를 확인하고, 필요하면 리포트 페이지에서 파일로 저장합니다.
"""
)

st.markdown("### 데이터 업데이트")
log = load_update_log()
if log.empty:
    st.info("아직 수집 기록이 없습니다. 데이터는 매일 한 번 자동으로 갱신됩니다.")
else:
    last = log.iloc[-1]
    st.metric("마지막 업데이트", str(last["updated_at"]), f"새 경기 {int(last['new_games'])}건")
    with st.expander("업데이트 기록"):
        st.dataframe(log.iloc[::-1], hide_index=True, width="stretch")

st.caption(
    "데이터 출처: Leaguepedia (lol.fandom.com, CC BY-SA 3.0), Riot Games Data Dragon. "
    "이 앱은 Riot Games와 관련이 없는 개인 학습용 프로젝트입니다."
)
