# LCK Insight

LCK(2016~2026)와 국제 대회(Worlds, MSI, First Stand, EWC) 경기 데이터를 분석하고,
경기 결과를 예측하고, 리포트를 만들어 주는 Streamlit 웹앱입니다.

## 실행

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## 구조

| 경로 | 역할 |
|---|---|
| `streamlit_app.py` | 앱 진입점, 페이지 목록 |
| `app_pages/` | 페이지별 화면 |
| `utils/` | 데이터 로딩, 분석, 모델, 리포트 함수 |
| `collect.py` | Leaguepedia 데이터 수집 (매일 GitHub Actions로 실행) |
| `data/` | 수집한 CSV |

## 데이터 출처

- [Leaguepedia](https://lol.fandom.com) (CC BY-SA 3.0)
- Riot Games Data Dragon

이 프로젝트는 Riot Games와 관련이 없는 개인 학습용 프로젝트입니다.
