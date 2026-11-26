"""LCK Insight: 데이터로 보는 LCK

앱 진입점. 페이지 목록과 공통 설정만 담당하고, 각 화면은 app_pages/ 에 있다.
실행: streamlit run streamlit_app.py
"""
import importlib
import os
import sys

import streamlit as st

# 서버는 한 번 불러온 utils 모듈을 메모리에 계속 들고 있어서, GitHub에 새 코드를 올려도 옛 코드가 남아
# ImportError가 날 수 있다. 이 파일은 페이지를 열 때마다 다시 실행되므로, 여기서 utils 파일이 바뀌었는지
# 확인하고 바뀌었으면 의존 순서대로 다시 불러온다 (앱 재시작 없이 새 코드 반영).
UTILS_ORDER = ["data_loader", "champions", "teams", "players", "model", "meta", "international",
               "tournaments", "report", "placeholder"]


def reload_changed_utils() -> None:
    import utils
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils")
    mtimes = {n: os.path.getmtime(os.path.join(base, f"{n}.py"))
              for n in UTILS_ORDER if os.path.exists(os.path.join(base, f"{n}.py"))}
    if getattr(utils, "_loaded_mtimes", None) != mtimes:
        # 이미 메모리에 올라온 모듈만 다시 불러온다 (서버를 새로 켠 직후에는 아무것도 없어서 그냥 지나감)
        for n in UTILS_ORDER:
            if f"utils.{n}" in sys.modules:
                importlib.reload(sys.modules[f"utils.{n}"])
        utils._loaded_mtimes = mtimes


reload_changed_utils()

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
        st.Page("app_pages/tournament.py", title="대회 정보", icon="🏆"),
    ],
    "도구": [
        st.Page("app_pages/predict.py", title="승부 예측", icon="🔮"),
        st.Page("app_pages/report.py", title="리포트", icon="📄"),
    ],
}

st.navigation(pages).run()
