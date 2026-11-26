import streamlit as st


def coming_soon(title: str, description: str, planned: list[str]) -> None:
    """아직 구현하지 않은 페이지에 계획된 기능을 보여준다."""
    st.title(title)
    st.write(description)
    st.info("이 페이지는 준비 중입니다.")
    st.markdown("**구현 예정 기능**")
    st.markdown("\n".join(f"- {item}" for item in planned))
