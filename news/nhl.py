"""Сборщик НХЛ: неофициальный api-web.nhle.com (без ключа и без документации).

Справочник эндпоинтов сообщества: https://github.com/Zmalski/NHL-API-Reference
Ответы кэшируются на ~19 с, для утреннего дайджеста опрашиваем один раз.
"""

import json
import time
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from news.competition import Scope

WEB = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"
UA = "KulturaHokkeyaNews/0.1 (+https://altitushkin.github.io/hockey-platform/)"
FINAL_STATES = {"OFF", "FINAL"}
API_HOSTS = {"api-web.nhle.com", "api.nhle.com", "forge-dapi.d3.nhle.com"}


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in API_HOSTS or parsed.username
            or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("Неподдержанный адрес NHL API")


class _ApiRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_json(url: str, retries: int = 3, timeout: int = 20) -> dict:
    try:
        validate_url(url)
    except ValueError as error:
        raise RuntimeError("Адрес NHL API заблокирован") from error
    opener = urllib.request.build_opener(_ApiRedirect())
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with opener.open(req, timeout=timeout) as resp:
                return json.load(resp)
        except Exception as e:  # сеть/5xx/битый JSON — пробуем ещё, потом сдаёмся
            last = e
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"НХЛ API не ответил: {url}: {last}")


@dataclass
class SkaterLine:
    pid: int
    team: str
    goals: int
    assists: int
    points: int
    sog: int


@dataclass
class GoalieLine:
    pid: int
    team: str
    saves: int
    shots: int
    decision: str | None  # W / L / O (поражение в ОТ или по буллитам) / None — не получил решения


@dataclass
class GameReport:
    game_id: int
    home: str
    away: str
    home_score: int
    away_score: int
    last_period: str  # REG / OT / SO
    skaters: list[SkaterLine] = field(default_factory=list)
    goalies: list[GoalieLine] = field(default_factory=list)
    scope: dict | None = None


def parse_box(box: dict, ours: set[int] | None) -> GameReport:
    """Бокс-скор → отчёт только по «нашим» (игроки не из реестра отбрасываются); ours=None — все игроки."""
    rep = GameReport(
        game_id=box["id"],
        home=box["homeTeam"]["abbrev"],
        away=box["awayTeam"]["abbrev"],
        home_score=box["homeTeam"]["score"],
        away_score=box["awayTeam"]["score"],
        last_period=(box.get("gameOutcome") or {}).get("lastPeriodType", "REG"),
    )
    phase = {1: "preseason", 2: "regular", 3: "playoffs"}.get(box.get("gameType"))
    if phase and box.get("season"):
        try:
            rep.scope = Scope(str(box["season"]), phase).data()
        except ValueError:
            pass  # Result remains usable, scope-dependent milestones do not.
    for side in ("homeTeam", "awayTeam"):
        team = box[side]["abbrev"]
        stats = box["playerByGameStats"][side]
        for p in stats.get("forwards", []) + stats.get("defense", []):
            if ours is None or p["playerId"] in ours:
                rep.skaters.append(SkaterLine(p["playerId"], team, p["goals"], p["assists"], p["points"], p["sog"]))
        for g in stats.get("goalies", []):
            # Вратарь, просидевший на скамейке, в бокс-скоре тоже есть — с нулём бросков.
            if (ours is None or g["playerId"] in ours) and g.get("shotsAgainst", 0) > 0:
                rep.goalies.append(GoalieLine(g["playerId"], team, g["saves"], g["shotsAgainst"], g.get("decision")))
    return rep


def pending_games(nhl_date: str) -> int:
    """Сколько матчей даты ещё не закончено (перенесённые и отменённые не ждём)."""
    games = fetch_json(f"{WEB}/score/{nhl_date}").get("games", [])
    return sum(1 for g in games if g.get("gameState") not in FINAL_STATES and g.get("gameScheduleState") == "OK")


def collect_night(nhl_date: str, ours: set[int] | None) -> list[GameReport]:
    """Все завершённые матчи даты (по времени Северной Америки), где играли наши; ours=None — все матчи."""
    reports = []
    for game in fetch_json(f"{WEB}/score/{nhl_date}").get("games", []):
        if game.get("gameState") not in FINAL_STATES:
            continue
        rep = parse_box(fetch_json(f"{WEB}/gamecenter/{game['id']}/boxscore"), ours)
        if ours is None or rep.skaters or rep.goalies:
            reports.append(rep)
    return reports


def upcoming_games(nhl_date: str) -> list[dict]:
    """Матчи даты, которые ещё не начались: {"start": UTC ISO, "home", "away"} по времени начала."""
    games = fetch_json(f"{WEB}/score/{nhl_date}").get("games", [])
    out = [{"start": g["startTimeUTC"], "home": g["homeTeam"]["abbrev"], "away": g["awayTeam"]["abbrev"]}
           for g in games if g.get("gameState") in ("FUT", "PRE") and g.get("gameScheduleState") == "OK"]
    return sorted(out, key=lambda g: g["start"])


def last_lineup(team: str, season: str, before: str, scope: Scope | None = None) -> set[int]:
    """Кто сыграл в последнем завершённом матче регулярки клуба до даты (полевые и вратари с бросками).
    Так отсекаем травмированных, «не в составе» и отправленных в фарм: в статистике сезона они есть."""
    scope = scope or Scope(season)
    if scope.competition != "nhl" or scope.profile.game_type is None:
        raise ValueError("Составу NHL нужен NHL-профиль")
    if scope.edition != season:
        raise ValueError("Сезон состава не совпадает с областью статистики")
    games = fetch_json(f"{WEB}/club-schedule-season/{team}/{season}").get("games", [])
    done = [g for g in games
            if g.get("gameType") == scope.profile.game_type and g.get("gameState") in FINAL_STATES
            and g["gameDate"] < before]
    if not done:
        return set()
    box = fetch_json(f"{WEB}/gamecenter/{done[-1]['id']}/boxscore")
    side = "homeTeam" if box["homeTeam"]["abbrev"] == team else "awayTeam"
    stats = box["playerByGameStats"][side]
    # вратари — оба заявленных: сменщик прошлого матча сегодня может выйти в старте
    return {p["playerId"] for k in ("forwards", "defense", "goalies") for p in stats.get(k, [])}


def fetch_nationals(season: str, codes: tuple[str, ...] = ("RUS", "BLR")) -> list[dict]:
    """Полевые и вратари сезона по гражданству — источник пополнения реестра."""
    out = []
    for kind, name_key in (("skater", "skaterFullName"), ("goalie", "goalieFullName")):
        for code in codes:
            exp = urllib.request.quote(f'seasonId={season} and nationalityCode="{code}"')
            data = fetch_json(f"{STATS}/{kind}/bios?limit=-1&cayenneExp={exp}")
            for p in data.get("data", []):
                out.append({"pid": p["playerId"], "name": p[name_key], "country": code, "team": p["currentTeamAbbrev"],
                            "goalie": kind == "goalie"})
    return out
