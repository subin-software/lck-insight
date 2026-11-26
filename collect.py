"""Leaguepedia + Riot Data Dragon 데이터 수집 스크립트.

- 로컬에서 직접 실행하거나, GitHub Actions가 매일 한 번 실행한다.
- 앱(Streamlit)은 이 스크립트가 만든 data/*.csv 만 읽는다.
  (Leaguepedia는 요청 제한이 엄격해서 앱이 직접 API를 부르지 않는다.)

수집 범위
- LCK: 정규 리그·플레이오프·LCK Cup (승강전 제외)
- 국제전: Worlds, MSI, First Stand, EWC 본선 (Play-In 포함, 지역 예선·선발전 제외)
- LCK 출신 선수가 해외 주요 리그(LPL, LEC, LCS 등)에서 뛴 경기의 선수 기록

실행
    python collect.py            # 데이터가 없으면 전체 수집, 있으면 새 데이터만 수집
    python collect.py --full     # 처음부터 전체 다시 수집
    python collect.py --probe    # 테이블마다 2행씩만 받아 필드 확인
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

API_URL = "https://lol.fandom.com/api.php"
DDRAGON = "https://ddragon.leagueoflegends.com"
HEADERS = {"User-Agent": "LCK-Insight student project (Streamlit app)"}
DATA_DIR = Path(__file__).resolve().parent / "data"
KST = timezone(timedelta(hours=9))

REQUEST_INTERVAL = 4   # 요청 사이 대기 시간(초)
PAGE_SIZE = 500        # cargoquery 1회 최대 행 수
NAME_BATCH = 80        # IN (...) 목록 한 번에 넣을 이름 수
INCREMENTAL_OVERLAP_DAYS = 3    # 증분 수집 시 겹쳐서 다시 받을 기간
SCHEDULE_REFRESH_DAYS = 30      # 일정은 최근 30일 + 미래 경기를 매번 새로 받는다

# ---------------------------------------------------------------- 수집 범위
LCK_LEAGUE = "LoL Champions Korea"
INTERNATIONAL_LEAGUES = {
    "World Championship": "Worlds",
    "Mid-Season Invitational": "MSI",
    "First Stand": "First Stand",
    "Esports World Cup": "EWC",
}
# LCK 출신 선수의 해외 리그 기록을 받을 리그 (Leaguepedia 리그 이름 → 짧은 이름)
FOREIGN_LEAGUES = {
    "Tencent LoL Pro League": "LPL",
    "LoL EMEA Championship": "LEC",
    "Europe League Championship Series": "EU LCS",
    "League of Legends Championship Series": "LCS",
    "North America League Championship Series": "NA LCS",
    "League of Legends Championship of The Americas": "LTA",
    "League of Legends Championship of The Americas North": "LTA North",
    "League of Legends Championship of The Americas South": "LTA South",
    "League of Legends Championship Pacific": "LCP",
    "Pacific Championship Series": "PCS",
    "LoL Master Series": "LMS",
    "Vietnam Championship Series": "VCS",
    "LoL Japan League": "LJL",
    "Circuit Brazilian League of Legends": "CBLOL",
    "Liga Latinoamerica": "LLA",
    "Turkish Championship League": "TCL",
    "LoL Continental League": "LCL",
    "Oceanic Pro League": "OPL",
    "LoL Circuit Oceania": "LCO",
    "Garena Premier League": "GPL",
}
LEAGUE_SHORT = {LCK_LEAGUE: "LCK", **INTERNATIONAL_LEAGUES, **FOREIGN_LEAGUES}


def _in(values) -> str:
    return "(" + ",".join(json.dumps(v, ensure_ascii=False) for v in values) + ")"


# 대회 페이지(Tournaments=T) 조건
WHERE_LCK = f'T.League="{LCK_LEAGUE}" AND T.IsQualifier="0" AND T.TournamentLevel="Primary"'
WHERE_INTL = (
    f"T.League IN {_in(INTERNATIONAL_LEAGUES)} AND T.TournamentLevel=\"Primary\""
    ' AND T.OverviewPage NOT LIKE "%Regional Finals%"'
    ' AND T.OverviewPage NOT LIKE "%Qualif%"'
)
WHERE_SCOPE = f"(({WHERE_LCK}) OR ({WHERE_INTL}))"
WHERE_FOREIGN = (
    f"T.League IN {_in(FOREIGN_LEAGUES)} AND T.IsQualifier=\"0\""
    ' AND T.TournamentLevel="Primary"'
)

# ---------------------------------------------------------------- 필드 정의 (Cargo 필드 → CSV 컬럼)
TOURNAMENT_FIELDS = {
    "T.OverviewPage": "page", "T.Name": "name", "T.League": "league", "T.Year": "year",
    "T.Split": "split", "T.DateStart": "date_start", "T.Date": "date_end",
    "T.IsQualifier": "is_qualifier",
}
GAME_FIELDS = {
    "SG.GameId": "game_id", "SG.MatchId": "match_id", "SG.OverviewPage": "page",
    "SG.DateTime_UTC": "datetime_utc", "SG.Patch": "patch", "SG.N_GameInMatch": "game_in_match",
    "SG.Team1": "team1", "SG.Team2": "team2", "SG.WinTeam": "win_team", "SG.Winner": "winner",
    "SG.Gamelength_Number": "gamelength",
    "SG.Team1Picks": "team1_picks", "SG.Team2Picks": "team2_picks",
    "SG.Team1Bans": "team1_bans", "SG.Team2Bans": "team2_bans",
    "SG.Team1Kills": "team1_kills", "SG.Team2Kills": "team2_kills",
    "SG.Team1Gold": "team1_gold", "SG.Team2Gold": "team2_gold",
    "SG.Team1Dragons": "team1_dragons", "SG.Team2Dragons": "team2_dragons",
    "SG.Team1Barons": "team1_barons", "SG.Team2Barons": "team2_barons",
    "SG.Team1Towers": "team1_towers", "SG.Team2Towers": "team2_towers",
}
PLAYER_FIELDS = {
    "SP.GameId": "game_id", "SP.OverviewPage": "page", "SP.DateTime_UTC": "datetime_utc",
    "SP.Link": "player", "SP.Team": "team", "SP.TeamVs": "team_vs", "SP.Role": "role",
    "SP.Side": "side", "SP.Champion": "champion",
    "SP.Kills": "kills", "SP.Deaths": "deaths", "SP.Assists": "assists",
    "SP.CS": "cs", "SP.Gold": "gold", "SP.DamageToChampions": "damage",
    "SP.VisionScore": "vision", "SP.TeamKills": "team_kills", "SP.TeamGold": "team_gold",
    "SP.PlayerWin": "win",
}
SCHEDULE_FIELDS = {
    "MS.MatchId": "match_id", "MS.OverviewPage": "page", "MS.DateTime_UTC": "datetime_utc",
    "MS.Team1": "team1", "MS.Team2": "team2", "MS.Team1Score": "team1_score",
    "MS.Team2Score": "team2_score", "MS.Winner": "winner", "MS.BestOf": "best_of",
    "MS.Tab": "tab", "MS.Round": "round",
}
ROSTER_FIELDS = {
    "TP.OverviewPage": "page", "TP.Team": "team", "TP.Link": "player", "TP.Role": "role",
}
TEAM_FIELDS = {
    "TE._pageName": "team", "TE.Short": "short", "TE.Region": "region",
    "TE.Image": "image", "TE.IsDisbanded": "is_disbanded",
}
PLAYER_IMAGE_FIELDS = {
    "PI.Link": "player", "PI.FileName": "file", "PI.Team": "team",
    "PI.Tournament": "page", "PI.SortDate": "sort_date",
}
REDIRECT_FIELDS = {"TR.AllName": "alias", "TR._pageName": "team"}
RENAME_FIELDS = {
    "RN.OriginalName": "original_name", "RN.NewName": "new_name", "RN.Date": "date",
    "RN.Verb": "verb", "RN.IsSamePage": "is_same_page",
}


# ---------------------------------------------------------------- API 호출
def _request(params: dict, max_retries: int = 6) -> dict:
    """요청 제한·일시 오류가 나면 대기 시간을 늘려 가며 다시 시도한다."""
    for attempt in range(max_retries):
        try:
            resp = requests.post(API_URL, data=params, headers=HEADERS, timeout=60)
            if resp.status_code == 429:
                raise RuntimeError("HTTP 429")
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            wait = 20 * (attempt + 1)
            print(f"  ! 요청 실패({exc}), {wait}초 후 재시도", flush=True)
            time.sleep(wait)
            continue
        if data.get("error", {}).get("code") == "ratelimited":
            wait = 30 * (attempt + 1)
            print(f"  ! 요청 제한, {wait}초 대기", flush=True)
            time.sleep(wait)
            continue
        if "error" in data:
            raise RuntimeError(data["error"])
        return data
    raise RuntimeError("요청이 계속 실패해 수집을 중단합니다.")


def cargo_query(tables: str, fields: dict[str, str], where: str = "", join_on: str = "",
                order_by: str = "", max_rows: int | None = None, label: str = "") -> pd.DataFrame:
    """Leaguepedia Cargo API를 페이지 단위로 끝까지 조회해 DataFrame으로 돌려준다."""
    field_str = ",".join(f"{src}={dst}" for src, dst in fields.items())
    rows: list[dict] = []
    offset = 0
    while True:
        limit = PAGE_SIZE if max_rows is None else min(PAGE_SIZE, max_rows - len(rows))
        data = _request({
            "action": "cargoquery", "format": "json", "tables": tables,
            "fields": field_str, "where": where, "join_on": join_on,
            "order_by": order_by, "limit": limit, "offset": offset,
        })
        batch = [item["title"] for item in data.get("cargoquery", [])]
        rows.extend(batch)
        if label:
            print(f"  {label}: {len(rows)}행", flush=True)
        time.sleep(REQUEST_INTERVAL)
        if len(batch) < limit or (max_rows is not None and len(rows) >= max_rows):
            break
        offset += limit
    df = pd.DataFrame(rows, columns=list(fields.values()))
    # Cargo는 밑줄 포함 필드를 공백으로 바꿔 돌려주기도 하므로 컬럼 이름을 다시 맞춘다
    return df.rename(columns=lambda c: c.replace(" ", "_"))


def batched(values, size=NAME_BATCH):
    values = sorted(set(v for v in values if isinstance(v, str) and v))
    for i in range(0, len(values), size):
        yield values[i:i + size]


# ---------------------------------------------------------------- 테이블별 수집
def fetch_tournaments() -> pd.DataFrame:
    df = cargo_query("Tournaments=T", TOURNAMENT_FIELDS,
                     where=f"{WHERE_SCOPE} OR ({WHERE_FOREIGN})", order_by="T.DateStart",
                     label="대회")
    df["league_short"] = df["league"].map(LEAGUE_SHORT)
    df["scope"] = "FOREIGN"
    df.loc[df["league"] == LCK_LEAGUE, "scope"] = "LCK"
    df.loc[df["league"].isin(INTERNATIONAL_LEAGUES), "scope"] = "INTL"
    return df


def fetch_games(since: str | None) -> pd.DataFrame:
    where = WHERE_SCOPE + (f' AND SG.DateTime_UTC >= "{since}"' if since else "")
    return cargo_query("ScoreboardGames=SG,Tournaments=T", GAME_FIELDS, where=where,
                       join_on="SG.OverviewPage=T.OverviewPage",
                       order_by="SG.DateTime_UTC,SG.GameId", label="경기")


def fetch_players(since: str | None) -> pd.DataFrame:
    where = WHERE_SCOPE + (f' AND SP.DateTime_UTC >= "{since}"' if since else "")
    return cargo_query("ScoreboardPlayers=SP,Tournaments=T", PLAYER_FIELDS, where=where,
                       join_on="SP.OverviewPage=T.OverviewPage",
                       order_by="SP.DateTime_UTC,SP.GameId,SP.Side,SP.Role_Number",
                       label="선수 기록")


def fetch_foreign_players(alumni: list[str], since: str | None) -> pd.DataFrame:
    """LCK 출신 선수가 해외 주요 리그에서 남긴 선수 기록."""
    frames = []
    for i, names in enumerate(batched(alumni), 1):
        where = f"{WHERE_FOREIGN} AND SP.Link IN {_in(names)}"
        if since:
            where += f' AND SP.DateTime_UTC >= "{since}"'
        frames.append(cargo_query(
            "ScoreboardPlayers=SP,Tournaments=T", PLAYER_FIELDS, where=where,
            join_on="SP.OverviewPage=T.OverviewPage",
            order_by="SP.DateTime_UTC,SP.GameId,SP.Side,SP.Role_Number",
            label=f"해외 리그 기록 {i}번째 묶음"))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=PLAYER_FIELDS.values())


def fetch_schedule(since: str | None) -> pd.DataFrame:
    where = WHERE_SCOPE
    if since:
        where += f' AND (MS.DateTime_UTC >= "{since}" OR MS.DateTime_UTC IS NULL)'
    return cargo_query("MatchSchedule=MS,Tournaments=T", SCHEDULE_FIELDS, where=where,
                       join_on="MS.OverviewPage=T.OverviewPage",
                       order_by="MS.DateTime_UTC,MS.MatchId", label="일정")


def fetch_rosters(min_year: int | None) -> pd.DataFrame:
    where = WHERE_SCOPE + (f' AND T.Year >= "{min_year}"' if min_year else "")
    return cargo_query("TournamentPlayers=TP,Tournaments=T", ROSTER_FIELDS, where=where,
                       join_on="TP.OverviewPage=T.OverviewPage",
                       order_by="TP.OverviewPage,TP.Team,TP.N_PlayerInTeam", label="로스터")


def fetch_team_info(team_names: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """팀 이름(옛 이름 포함) → 현재 팀 페이지, 팀 정보, 팀명 변경 이력."""
    redirects = []
    for names in batched(team_names):
        redirects.append(cargo_query("TeamRedirects=TR", REDIRECT_FIELDS,
                                     where=f"TR.AllName IN {_in(names)}"))
    redirects = pd.concat(redirects, ignore_index=True).drop_duplicates("alias")

    pages = sorted(set(redirects["team"]) | set(team_names))
    teams, renames = [], []
    for names in batched(pages):
        teams.append(cargo_query("Teams=TE", TEAM_FIELDS, where=f"TE._pageName IN {_in(names)}"))
        renames.append(cargo_query(
            "TeamRenames=RN", RENAME_FIELDS,
            where=f"RN.OriginalName IN {_in(names)} OR RN.NewName IN {_in(names)}"))
    teams = pd.concat(teams, ignore_index=True).drop_duplicates("team")
    renames = pd.concat(renames, ignore_index=True).drop_duplicates()
    print(f"  팀 정보: 팀 {len(teams)}개, 별칭 {len(redirects)}개, 이름 변경 {len(renames)}건", flush=True)
    return teams, redirects, renames


def image_url(file_name: str) -> str:
    """위키 파일 이름 → 실제 이미지 주소 (MD5 해시 폴더 규칙, API 호출 불필요)."""
    name = file_name.replace(" ", "_")
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    return f"https://static.wikia.nocookie.net/lolesports_gamepedia_en/images/{h[0]}/{h[:2]}/{quote(name)}"


def fetch_player_images(player_names) -> pd.DataFrame:
    """선수별 시즌·대회 프로필 사진 목록. 이미지 파일은 받지 않고 주소만 저장한다."""
    frames = []
    for i, names in enumerate(batched(player_names), 1):
        frames.append(cargo_query("PlayerImages=PI", PLAYER_IMAGE_FIELDS,
                                  where=f"PI.Link IN {_in(names)}",
                                  label=f"선수 사진 {i}번째 묶음"))
    if not frames:
        return pd.DataFrame(columns=[*PLAYER_IMAGE_FIELDS.values(), "url"])
    df = pd.concat(frames, ignore_index=True).dropna(subset=["file"])
    df = df[df["file"].astype(str) != ""]
    df["url"] = df["file"].map(image_url)
    return df


def fetch_champions() -> pd.DataFrame:
    """Data Dragon 최신 버전의 챔피언 영문·한글 이름과 아이콘 주소."""
    version = requests.get(f"{DDRAGON}/api/versions.json", timeout=30).json()[0]
    en = requests.get(f"{DDRAGON}/cdn/{version}/data/en_US/champion.json", timeout=30).json()["data"]
    ko = requests.get(f"{DDRAGON}/cdn/{version}/data/ko_KR/champion.json", timeout=30).json()["data"]
    rows = [{
        "champion": c["name"],              # Leaguepedia 표기와 같은 영문 이름
        "ddragon_id": cid,
        "name_ko": ko[cid]["name"],
        "icon": f"{DDRAGON}/cdn/{version}/img/champion/{c['image']['full']}",
        "version": version,
    } for cid, c in en.items()]
    print(f"  챔피언: {len(rows)}개 (패치 {version})", flush=True)
    return pd.DataFrame(rows).sort_values("champion")


# ---------------------------------------------------------------- 저장·병합
def read(name: str) -> pd.DataFrame:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def write(name: str, df: pd.DataFrame) -> None:
    df.to_csv(DATA_DIR / f"{name}.csv", index=False, encoding="utf-8")


def upsert(old: pd.DataFrame, new: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """키가 같은 행은 새 데이터로 바꾸고, 새 행은 추가한다."""
    if old.empty:
        return new.drop_duplicates(keys, keep="last")
    merged = pd.concat([old, new.astype(str)], ignore_index=True)
    return merged.drop_duplicates(keys, keep="last")


def since_from(df: pd.DataFrame, days: int) -> str | None:
    if df.empty or "datetime_utc" not in df:
        return None
    last = pd.to_datetime(df["datetime_utc"], errors="coerce").max()
    if pd.isna(last):
        return None
    return (last - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def append_update_log(new_games: int, note: str) -> None:
    log = read("update_log")
    row = pd.DataFrame([{
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "new_games": new_games,
        "note": note,
    }])
    write("update_log", pd.concat([log, row], ignore_index=True))


# ---------------------------------------------------------------- 실행
def probe() -> None:
    """각 테이블에서 2행씩 받아 필드 이름이 맞는지 확인한다."""
    checks = [
        ("대회", lambda: cargo_query("Tournaments=T", TOURNAMENT_FIELDS, where=WHERE_LCK, max_rows=2)),
        ("경기", lambda: cargo_query("ScoreboardGames=SG,Tournaments=T", GAME_FIELDS, where=WHERE_LCK,
                                   join_on="SG.OverviewPage=T.OverviewPage", max_rows=2)),
        ("선수", lambda: cargo_query("ScoreboardPlayers=SP,Tournaments=T", PLAYER_FIELDS, where=WHERE_INTL,
                                   join_on="SP.OverviewPage=T.OverviewPage", max_rows=2)),
        ("일정", lambda: cargo_query("MatchSchedule=MS,Tournaments=T", SCHEDULE_FIELDS, where=WHERE_LCK,
                                   join_on="MS.OverviewPage=T.OverviewPage", max_rows=2)),
        ("로스터", lambda: cargo_query("TournamentPlayers=TP,Tournaments=T", ROSTER_FIELDS, where=WHERE_LCK,
                                    join_on="TP.OverviewPage=T.OverviewPage", max_rows=2)),
        ("팀", lambda: cargo_query("Teams=TE", TEAM_FIELDS, where='TE._pageName="T1"')),
        ("별칭", lambda: cargo_query("TeamRedirects=TR", REDIRECT_FIELDS, where='TR.AllName="SK Telecom T1"')),
        ("이름 변경", lambda: cargo_query("TeamRenames=RN", RENAME_FIELDS, where='RN.NewName="T1"')),
    ]
    for name, fn in checks:
        print(f"== {name}")
        print(fn().to_string())


def main(full: bool = False) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    games_old = pd.DataFrame() if full else read("games")
    incremental = not games_old.empty
    mode = "증분" if incremental else "전체"
    print(f"[{mode} 수집 시작]", flush=True)

    tournaments = fetch_tournaments()

    since = since_from(games_old, INCREMENTAL_OVERLAP_DAYS) if incremental else None
    games_new = fetch_games(since)
    games = upsert(games_old, games_new, ["game_id"])
    added = len(games) - len(games_old)

    players_old = pd.DataFrame() if full else read("players")
    players_new = fetch_players(since)
    players = upsert(players_old, players_new, ["game_id", "player", "team"])

    # LCK 출신 선수 = LCK 경기에 한 번이라도 나온 선수
    lck_pages = set(tournaments.loc[tournaments["scope"] == "LCK", "page"])
    alumni = sorted(players.loc[players["page"].isin(lck_pages), "player"].unique())
    foreign_old = pd.DataFrame() if full else read("players_foreign")
    foreign_since = since_from(foreign_old, INCREMENTAL_OVERLAP_DAYS) if incremental else None
    foreign_new = fetch_foreign_players(alumni, foreign_since)
    foreign = upsert(foreign_old, foreign_new, ["game_id", "player", "team"])

    # 새 경기에 나온 선수만 사진 목록을 다시 받는다 (새 시즌 사진은 새 경기와 함께 올라온다)
    photo_targets = set(players_new["player"]) | set(foreign_new["player"])
    images = upsert(pd.DataFrame() if full else read("player_images"),
                    fetch_player_images(photo_targets), ["player", "file"])

    schedule_since = (datetime.now(timezone.utc) - timedelta(days=SCHEDULE_REFRESH_DAYS)
                      ).strftime("%Y-%m-%d") if incremental else None
    schedule = upsert(pd.DataFrame() if full else read("schedule"),
                      fetch_schedule(schedule_since), ["match_id"])

    roster_min_year = datetime.now(KST).year - 1 if incremental else None
    rosters = upsert(pd.DataFrame() if full else read("rosters"),
                     fetch_rosters(roster_min_year), ["page", "team", "player", "role"])

    team_names = set(games["team1"]) | set(games["team2"]) | set(schedule["team1"]) \
        | set(schedule["team2"]) | set(rosters["team"]) | set(foreign["team"])
    teams, redirects, renames = fetch_team_info(sorted(team_names))

    champions = fetch_champions()

    for name, df in [("tournaments", tournaments), ("games", games), ("players", players),
                     ("players_foreign", foreign), ("player_images", images),
                     ("schedule", schedule), ("rosters", rosters),
                     ("teams", teams), ("team_redirects", redirects), ("team_renames", renames),
                     ("champions", champions)]:
        write(name, df)
        print(f"  저장: {name}.csv ({len(df)}행)", flush=True)

    append_update_log(added, f"{mode} 수집 완료")
    print(f"[완료] 새 경기 {added}건", flush=True)


def collect_all_images() -> None:
    """이미 수집한 모든 선수의 사진 목록을 받는다 (사진 기능을 나중에 추가했을 때 한 번 실행)."""
    names = set(read("players").get("player", [])) | set(read("players_foreign").get("player", []))
    images = fetch_player_images(names)
    write("player_images", images)
    print(f"  저장: player_images.csv ({len(images)}행, 선수 {images['player'].nunique()}명)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", action="store_true", help="처음부터 전체 다시 수집")
    parser.add_argument("--probe", action="store_true", help="필드 확인용으로 2행씩만 조회")
    parser.add_argument("--images", action="store_true", help="기존 선수 전체의 사진 목록만 수집")
    args = parser.parse_args()
    try:
        if args.probe:
            probe()
        elif args.images:
            collect_all_images()
        else:
            main(full=args.full)
    except Exception as exc:  # 실패해도 기존 CSV는 그대로 둔다
        print(f"[실패] {exc}", file=sys.stderr)
        if not (args.probe or args.images):
            append_update_log(0, f"수집 실패: {str(exc)[:80]}")
        sys.exit(1)
