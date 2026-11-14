"""Match narratives built from relations, never reconstructed by a language model."""

from news.digest import SUFFIX


def night_lead(reports, players, teams, highlights=None):
    # The lead must describe the same game as the selected headline highlight.
    # Otherwise a goalie from another game can hijack the post's opening.
    if highlights:
        pid = highlights[0][0]
        reports = [r for r in reports if any(x.pid == pid for x in r.skaters + r.goalies)]
    candidates = [(g.saves, r.game_id, g, r) for r in reports for g in r.goalies
                  if g.decision == "W" and str(g.pid) in players]
    if not candidates:
        return None
    _, _, goalie, game = max(candidates, key=lambda c: c[:2])
    if goalie.team not in (game.home, game.away) or not 0 <= goalie.saves <= goalie.shots:
        return None
    opponent = game.away if goalie.team == game.home else game.home
    own, other = ((game.home_score, game.away_score) if goalie.team == game.home
                  else (game.away_score, game.home_score))
    if own <= other:
        return None
    return (f"{players[str(goalie.pid)]['surname']} отразил {goalie.saves} из {goalie.shots} бросков. "
            f"{teams[goalie.team]} — {teams[opponent]} {own}:{other}{SUFFIX.get(game.last_period, '')}.")


def comeback(game, scoring):
    """Completed, continuous goal timeline must agree with the final score. SO excluded."""
    if not isinstance(scoring, list) or game.last_period == "SO" or game.home_score == game.away_score:
        return None
    home_won = game.home_score > game.away_score
    previous = (0, 0)
    worst = (0, 0)
    deficit = 0
    for period in scoring:
        if not isinstance(period, dict) or not isinstance(period.get("goals"), list):
            return None
        for goal in period["goals"]:
            if not isinstance(goal, dict):
                return None
            current = (goal.get("homeScore"), goal.get("awayScore"))
            if any(type(v) is not int or v < 0 for v in current):
                return None
            delta = (current[0] - previous[0], current[1] - previous[1])
            if delta not in ((1, 0), (0, 1)):
                return None
            own, other = current if home_won else current[::-1]
            if other - own > deficit:
                deficit, worst = other - own, (own, other)
            previous = current
    if previous != (game.home_score, game.away_score) or deficit < 3:
        return None
    return {"game_id": game.game_id, "winner": game.home if home_won else game.away,
            "loser": game.away if home_won else game.home, "from": worst,
            "final": (game.home_score, game.away_score) if home_won else (game.away_score, game.home_score),
            "period": game.last_period}


def comeback_text(event, teams):
    a, b = event["from"]
    x, y = event["final"]
    return (f"{teams[event['winner']]} отыгрался с {a}:{b}. "
            f"{teams[event['winner']]} — {teams[event['loser']]} {x}:{y}{SUFFIX.get(event['period'], '')}.")

