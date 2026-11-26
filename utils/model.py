"""세트 승패 예측 모델.

특성(feature)은 모두 '그 경기 이전' 데이터만으로 만든다 (미래 정보 누수 방지).
- elo_diff      : 두 팀 Elo 레이팅 차이 (모든 LCK·국제전 경기를 시간 순으로 반영)
- form_diff     : 최근 10세트 승률 차이
- blue_side     : A팀이 블루 진영이면 1
- champ_diff    : 고른 챔피언 5개의 최근 승률 평균 차이 (오래된 경기일수록 가중치 감소)
- h2h           : 두 팀 상대 전적 승률 (최근 20세트, 기록 없으면 0.5)

모델: 로지스틱 회귀와 랜덤 포레스트를 비교하고, 2025년 이후 경기로 성능을 평가한다.
     확률의 질(로그 손실)이 더 좋은 모델을 최종 모델로 쓴다.
"""
from __future__ import annotations

import math
from collections import defaultdict, deque

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from utils.data_loader import load_games
from utils.teams import lineage_groups

FEATURES = {
    "elo_diff": "팀 Elo 레이팅 차이",
    "form_diff": "최근 10세트 승률 차이",
    "blue_side": "블루 진영",
    "champ_diff": "챔피언 조합 승률 차이",
    "h2h": "상대 전적",
}
TEST_FROM = pd.Timestamp("2025-01-01")
START_YEAR = 2016
ELO_K = 24
ELO_SEASON_KEEP = 0.75        # 새 시즌이 되면 레이팅을 평균(1500) 쪽으로 25% 당긴다
CHAMP_HALF_LIFE_DAYS = 120    # 챔피언 승률: 120일 지난 경기는 가중치 절반
CHAMP_PRIOR_GAMES = 8         # 표본이 적은 챔피언은 50% 쪽으로 당겨 계산


def team_key(team: str) -> str:
    """이름이 바뀐 팀을 하나의 키로 묶는다 (계보에서 사전순 첫 이름)."""
    return lineage_groups().get(team, [team])[0]


class History:
    """경기를 시간 순으로 하나씩 반영하면서, 각 시점의 팀·챔피언 상태를 기억한다."""

    def __init__(self):
        self.elo = defaultdict(lambda: 1500.0)
        self.season = {}
        self.recent = defaultdict(lambda: deque(maxlen=10))
        self.h2h = defaultdict(lambda: deque(maxlen=20))
        self.champ = {}       # 챔피언 → [가중 승수, 가중 경기수, 마지막 시각]
        self.last_time = None

    # ---- 조회 ------------------------------------------------------
    def rating(self, key, year=None):
        if year is not None and self.season.get(key) not in (None, year):
            return 1500 + ELO_SEASON_KEEP * (self.elo[key] - 1500)
        return self.elo[key]

    def form(self, key):
        r = self.recent[key]
        return sum(r) / len(r) if r else 0.5

    def head_to_head(self, a, b):
        r = self.h2h[(a, b)]
        return sum(r) / len(r) if r else 0.5

    def champ_rate(self, name, now):
        if name not in self.champ:
            return 0.5
        w, n, t = self.champ[name]
        decay = 0.5 ** ((now - t).days / CHAMP_HALF_LIFE_DAYS)
        w, n = w * decay, n * decay
        return (w + CHAMP_PRIOR_GAMES * 0.5) / (n + CHAMP_PRIOR_GAMES)

    def comp_rate(self, picks, now):
        picks = [p for p in picks if p and p != "None"]
        return float(np.mean([self.champ_rate(p, now) for p in picks])) if picks else 0.5

    def features(self, a, b, a_blue, a_picks, b_picks, now, year=None) -> dict:
        return {
            "elo_diff": self.rating(a, year) - self.rating(b, year),
            "form_diff": self.form(a) - self.form(b),
            "blue_side": 1.0 if a_blue else 0.0,
            "champ_diff": self.comp_rate(a_picks, now) - self.comp_rate(b_picks, now),
            "h2h": self.head_to_head(a, b),
        }

    # ---- 갱신 ------------------------------------------------------
    def update(self, a, b, a_won, a_picks, b_picks, now, year):
        for k in (a, b):                      # 새 시즌 첫 경기면 평균 쪽으로 회귀
            if self.season.get(k) not in (None, year):
                self.elo[k] = 1500 + ELO_SEASON_KEEP * (self.elo[k] - 1500)
            self.season[k] = year
        expected = 1 / (1 + 10 ** ((self.elo[b] - self.elo[a]) / 400))
        delta = ELO_K * ((1.0 if a_won else 0.0) - expected)
        self.elo[a] += delta
        self.elo[b] -= delta
        self.recent[a].append(1 if a_won else 0)
        self.recent[b].append(0 if a_won else 1)
        self.h2h[(a, b)].append(1 if a_won else 0)
        self.h2h[(b, a)].append(0 if a_won else 1)
        for picks, won in ((a_picks, a_won), (b_picks, not a_won)):
            for p in picks:
                if not p or p == "None":
                    continue
                w, n, t = self.champ.get(p, (0.0, 0.0, now))
                decay = 0.5 ** ((now - t).days / CHAMP_HALF_LIFE_DAYS)
                self.champ[p] = (w * decay + (1 if won else 0), n * decay + 1, now)
        self.last_time = now


def _picks(s: str) -> list[str]:
    return [p.strip() for p in str(s).split(",") if p.strip()]


@st.cache_resource
def build_dataset() -> tuple[pd.DataFrame, History]:
    """모든 경기를 시간 순으로 훑으며 '경기 직전' 특성을 만든다. 최종 상태(History)도 함께 돌려준다."""
    g = load_games()
    g = g[g["scope"].isin(["LCK", "INTL"])].sort_values("datetime_kst")
    groups = lineage_groups()        # 캐시 값은 호출마다 복사되므로 한 번만 가져온다
    hist = History()
    rows = []
    for r in g.itertuples():
        a = groups.get(r.team1, [r.team1])[0]            # team1 = 블루 진영
        b = groups.get(r.team2, [r.team2])[0]
        pa, pb = _picks(r.team1_picks), _picks(r.team2_picks)
        now, year = r.datetime_kst, int(r.year)
        a_won = r.win_team == r.team1
        if year >= START_YEAR:
            f = hist.features(a, b, True, pa, pb, now, year)
            f.update(game_id=r.game_id, datetime=now, year=year, scope=r.scope,
                     team1=r.team1, team2=r.team2, y=int(a_won))
            rows.append(f)
        hist.update(a, b, a_won, pa, pb, now, year)
    data = pd.DataFrame(rows)
    # 진영 효과를 제대로 배우도록, 같은 경기를 B팀 시점(레드 진영)으로 뒤집은 행도 추가
    flipped = data.copy()
    for col in ["elo_diff", "form_diff", "champ_diff"]:
        flipped[col] = -flipped[col]
    flipped["blue_side"] = 0.0
    flipped["h2h"] = 1 - flipped["h2h"]
    flipped["y"] = 1 - flipped["y"]
    flipped[["team1", "team2"]] = data[["team2", "team1"]].values
    return pd.concat([data.assign(view="A"), flipped.assign(view="B")], ignore_index=True), hist


def _models():
    return {
        "로지스틱 회귀": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "랜덤 포레스트": RandomForestClassifier(n_estimators=300, max_depth=6, min_samples_leaf=20,
                                          random_state=42, n_jobs=-1),
    }


@st.cache_resource
def evaluate() -> dict:
    """2024년까지 학습 → 2025년 이후 경기로 평가. 기준선(Elo가 높은 팀 선택)과 비교한다."""
    data, _ = build_dataset()
    train, test = data[data["datetime"] < TEST_FROM], data[data["datetime"] >= TEST_FROM]
    x_cols = list(FEATURES)
    result = {"n_train": len(train) // 2, "n_test": len(test) // 2, "models": {}}
    test_a = test[test["view"] == "A"]
    for name, model in _models().items():
        model.fit(train[x_cols], train["y"])
        prob = model.predict_proba(test_a[x_cols])[:, 1]
        pred = (prob >= 0.5).astype(int)
        result["models"][name] = {
            "정확도": accuracy_score(test_a["y"], pred),
            "로그 손실": log_loss(test_a["y"], prob),
            "AUC": roc_auc_score(test_a["y"], prob),
            "confusion": confusion_matrix(test_a["y"], pred),
        }
    base = (test_a["elo_diff"] > 0).astype(int)
    result["baseline"] = {"Elo 높은 팀": accuracy_score(test_a["y"], base),
                          "항상 블루 승": test_a["y"].mean()}
    # 앱은 '확률'을 보여주므로 확률의 질을 재는 로그 손실이 가장 낮은 모델을 고른다
    result["best"] = min(result["models"], key=lambda m: result["models"][m]["로그 손실"])
    return result


@st.cache_resource
def final_model():
    """평가에서 고른 모델을 전체 데이터로 다시 학습한다."""
    data, hist = build_dataset()
    best = evaluate()["best"]
    model = _models()[best]
    model.fit(data[list(FEATURES)], data["y"])
    return model, best, hist


def predict(team_a: str, team_b: str, a_blue: bool = True, a_picks=(), b_picks=()) -> tuple[float, dict]:
    """A팀이 한 세트를 이길 확률과 사용한 특성 값."""
    model, _, hist = final_model()
    a, b = team_key(team_a), team_key(team_b)
    now = hist.last_time
    f = hist.features(a, b, a_blue, list(a_picks), list(b_picks), now)
    g = hist.features(b, a, not a_blue, list(b_picks), list(a_picks), now)
    # A 시점 예측과 (1 - B 시점 예측)을 평균해, A/B 순서를 바꿔도 결과가 정확히 뒤집히게 한다
    pa = model.predict_proba(pd.DataFrame([f])[list(FEATURES)])[0, 1]
    pb = model.predict_proba(pd.DataFrame([g])[list(FEATURES)])[0, 1]
    return float((pa + 1 - pb) / 2), f


def contributions(f: dict) -> pd.Series | None:
    """로지스틱 회귀일 때 특성별 기여도(표준화 값 × 계수, 로그 오즈 단위)."""
    model, best, _ = final_model()
    if best != "로지스틱 회귀":
        return None
    scaler, lr = model.named_steps["standardscaler"], model.named_steps["logisticregression"]
    z = (np.array([f[k] for k in FEATURES]) - scaler.mean_) / scaler.scale_
    return pd.Series(z * lr.coef_[0], index=[FEATURES[k] for k in FEATURES])


def importances() -> pd.Series:
    model, best, _ = final_model()
    if best == "로지스틱 회귀":
        coef = model.named_steps["logisticregression"].coef_[0]
        return pd.Series(np.abs(coef), index=[FEATURES[k] for k in FEATURES]).sort_values()
    return pd.Series(model.feature_importances_, index=[FEATURES[k] for k in FEATURES]).sort_values()


def series_prob(p: float, best_of: int) -> float:
    """세트 승률 p로 Bo3/Bo5 시리즈를 이길 확률 (세트가 서로 독립이라고 가정)."""
    need = best_of // 2 + 1
    return sum(math.comb(need - 1 + k, k) * p ** need * (1 - p) ** k for k in range(need))


def team_state(team: str) -> dict:
    """팀의 현재 Elo, 최근 10세트 승률."""
    _, _, hist = final_model()
    key = team_key(team)
    return {"elo": hist.rating(key), "form": hist.form(key), "games": len(hist.recent[key])}


def champ_rate(name: str) -> float:
    _, _, hist = final_model()
    return hist.champ_rate(name, hist.last_time)


def champ_pool(min_weight: float = 5.0) -> list[str]:
    """최근 경기(가중치 반영)에서 충분히 쓰인 챔피언 목록 — 조합 비교 후보."""
    _, _, hist = final_model()
    out = []
    for name, (_, n, t) in hist.champ.items():
        if n * 0.5 ** ((hist.last_time - t).days / CHAMP_HALF_LIFE_DAYS) >= min_weight:
            out.append(name)
    return out
