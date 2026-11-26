"""LCK Insight: 데이터로 보는 LCK

앱 진입점. 페이지 목록과 공통 설정만 담당하고, 각 화면은 app_pages/ 에 있다.
실행: streamlit run streamlit_app.py
"""
import streamlit as st

st.set_page_config(
    page_title="LCK Insight",
    page_icon="🎮",
    layout="wide",
)

pages = {
    "시작": [
        st.Page("app_pages/home.py", title="홈", icon="🏠", default=True),
        st.Page("app_pages/schedule.py", title="경기 일정", icon="📅"),
    ],
    "분석": [
        st.Page("app_pages/team.py", title="팀 분석", icon="🛡️"),
        st.Page("app_pages/player.py", title="선수 분석", icon="👤"),
        st.Page("app_pages/meta.py", title="메타 분석", icon="📊"),
        st.Page("app_pages/international.py", title="국제전", icon="🌏"),
    ],
    "도구": [
        st.Page("app_pages/predict.py", title="승부 예측", icon="🔮"),
        st.Page("app_pages/report.py", title="리포트", icon="📄"),
    ],
}

st.navigation(pages).run()
