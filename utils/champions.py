"""챔피언 이름(Leaguepedia 영문 표기) → 한글 이름, 아이콘 주소."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.data_loader import load_champions

# Leaguepedia 와 Data Dragon 의 영문 표기가 다른 챔피언
NAME_FIX = {"Nunu": "Nunu & Willump"}


@st.cache_data
def _table() -> pd.DataFrame:
    df = load_champions()
    return df.set_index("champion") if not df.empty else df


def _key(name: str) -> str:
    return NAME_FIX.get(name, name)


def name_ko(name: str) -> str:
    t = _table()
    key = _key(name)
    return t.at[key, "name_ko"] if not t.empty and key in t.index else name


def icon(name: str) -> str | None:
    t = _table()
    key = _key(name)
    return t.at[key, "icon"] if not t.empty and key in t.index else None


def explode_champions(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """'A,B,C' 형태의 픽·밴 문자열을 챔피언 1개당 1행으로 펼친다."""
    out = df.assign(champion=df[column].fillna("").str.split(",")).explode("champion")
    out["champion"] = out["champion"].str.strip()
    return out[~out["champion"].isin(["", "None"])]   # 'None' = 밴을 하지 않은 칸
