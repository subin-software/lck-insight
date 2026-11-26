"""data/ 폴더의 CSV를 읽어오는 함수 모음. 모든 로딩은 캐시해서 한 번만 읽는다."""
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@st.cache_data
def load_csv(name: str) -> pd.DataFrame:
    """data/<name>.csv 를 읽는다. 파일이 없으면 빈 DataFrame을 돌려준다."""
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_update_log() -> pd.DataFrame:
    return load_csv("update_log")
