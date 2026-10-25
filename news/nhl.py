"""Сборщик НХЛ: неофициальный api-web.nhle.com (без ключа и без документации).

Справочник эндпоинтов сообщества: https://github.com/Zmalski/NHL-API-Reference
Ответы кэшируются на ~19 с, для утреннего дайджеста опрашиваем один раз.
"""

import json
import time
import urllib.request
from dataclasses import dataclass, field

WEB = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"
UA = "KulturaHokkeyaNews/0.1 (+https://altitushkin.github.io/hockey-platform/)"
FINAL_STATES = {"OFF", "FINAL"}


def fetch_json(url: str, retries: int = 3, timeout: int = 20) -> dict:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except Exception as e:  # сеть/5xx/битый JSON — пробуем ещё, потом сдаёмся
            last = e
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


def parse_box(box: dict, ours: set[int]) -> GameReport:
    """Бокс-скор → отчёт только по «нашим». Игроки не из реестра отбрасываются."""
    rep = GameReport(
        game_id=box["id"],
        home=box["homeTeam"]["abbrev"],
        away=box["awayTeam"]["abbrev"],
        home_score=box["homeTeam"]["score"],
        away_score=box["awayTeam"]["score"],
        last_period=(box.get("gameOutcome") or {}).get("lastPeriodType", "REG"),
    )
    for side in ("homeTeam", "awayTeam"):
        team = box[side]["abbrev"]
        stats = box["playerByGameStats"][side]
        for p in stats.get("forwards", []) + stats.get("defense", []):
            if p["playerId"] in ours:
                rep.skaters.append(SkaterLine(p["playerId"], team, p["goals"], p["assists"], p["points"], p["sog"]))
        for g in stats.get("goalies", []):
            # Вратарь, просидевший на скамейке, в бокс-скоре тоже есть — с нулём бросков.
            if g["playerId"] in ours and g.get("shotsAgainst", 0) > 0:
                rep.goalies.append(GoalieLine(g["playerId"], team, g["saves"], g["shotsAgainst"], g.get("decision")))
    return rep


def pending_games(nhl_date: str) -> int:
    """Сколько матчей даты ещё не закончено (перенесённые и отменённые не ждём)."""
    games = fetch_json(f"{WEB}/score/{nhl_date}").get("games", [])
    return sum(1 for g in games if g.get("gameState") not in FINAL_STATES and g.get("gameScheduleState") == "OK")


def collect_night(nhl_date: str, ours: set[int]) -> list[GameReport]:
    """Все завершённые матчи даты (по времени Северной Америки), где играли наши."""
    reports = []
    for game in fetch_json(f"{WEB}/score/{nhl_date}").get("games", []):
        if game.get("gameState") not in FINAL_STATES:
            continue
        rep = parse_box(fetch_json(f"{WEB}/gamecenter/{game['id']}/boxscore"), ours)
        if rep.skaters or rep.goalies:
            reports.append(rep)
    return reports


def fetch_nationals(season: str, codes: tuple[str, ...] = ("RUS", "BLR")) -> list[dict]:
    """Полевые и вратари сезона по гражданству — источник пополнения реестра."""
    out = []
    for kind, name_key in (("skater", "skaterFullName"), ("goalie", "goalieFullName")):
        for code in codes:
            exp = urllib.request.quote(f'seasonId={season} and nationalityCode="{code}"')
            data = fetch_json(f"{STATS}/{kind}/bios?limit=-1&cayenneExp={exp}")
            for p in data.get("data", []):
                out.append({"pid": p["playerId"], "name": p[name_key], "country": code, "team": p["currentTeamAbbrev"]})
    return out
