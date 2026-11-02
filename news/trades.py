"""Conservative, offline trade facts. Unsupported wording always requires review."""

import re
from dataclasses import asdict, dataclass

from news import guard


@dataclass(frozen=True)
class Move:
    pid: int
    source: str
    destination: str


@dataclass(frozen=True)
class Trade:
    moves: tuple[Move, ...] = ()
    evidence: str = ""
    consideration: str = ""
    reason: str = "направление обмена не разобрано"

    def data(self) -> dict:
        return asdict(self)


def extract(headline: str, text: str, players: dict[int, str], clubs: dict) -> Trade:
    """Only explicit acquisition/disposal clauses in the headline or lead, never history.

    Player identities come from NHL links; a surname alone is not an identity source.
    Picks, conditions, retained salary and multi-party deals remain manual review.
    """
    aliases = {alias.casefold(): code for code, values in clubs.items() for alias in values if alias}
    team_re = "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    if not team_re or not players:
        return Trade()

    def team(value: str) -> str | None:
        found = {aliases[m.group().casefold()] for m in re.finditer(
            rf"\b(?:{team_re})\b", value, re.I)}
        remainder = re.sub(rf"\b(?:{team_re})\b", "", value, flags=re.I)
        remainder = re.sub(r"\bthe\b", "", remainder, flags=re.I).strip(" .!")
        return next(iter(found)) if len(found) == 1 and not remainder else None

    def people(value: str) -> set[int]:
        # Full name in the lead or an unambiguous linked surname in the headline.
        ids = {pid for pid, name in players.items() if re.search(
            rf"\b{re.escape(name)}\b", value, re.I)}
        if not ids:
            ids = {pid for pid, name in players.items() if re.search(
                rf"\b{re.escape(name.split()[-1])}\b", value, re.I)}
        return ids

    candidates = []
    lead = next((p for p in text.splitlines() if p.strip() and not p.startswith("#")), "")
    # Do not split St. Louis at its period.
    lead = re.split(r"(?<=[.!?])\s+(?=[A-Z])", lead.replace("St. Louis", "St Louis"))[0]
    lead = lead.replace("St Louis", "St. Louis")
    lead_parsed = False
    for sentence in (headline, lead):
        patterns = (
            (r"^(.+?)\s+(?:acquire[sd]?|has acquired|have acquired)\s+(.+?)\s+from\s+(.+?)"
             r"(?:\s+(?:in exchange for|for)\s+(.+))?[.!]?$", False),
            (r"^(.+?)\s+(?:trade[sd]?)\s+(.+?)\s+to\s+(.+?)(?:\s+(?:in exchange for|for)\s+(.+))?[.!]?$", True),
            (r"^(.+?)\s+(?:was )?traded to\s+(.+?)\s+by\s+(.+?)(?:\s+for\s+(.+))?[.!]?$", None),
        )
        for pattern, disposal in patterns:
            match = re.match(pattern, sentence, re.I)
            if not match:
                continue
            a, b, c, consideration = match.groups()
            if disposal is None:
                asset, receiver, sender = a, team(b), team(c)
            else:
                asset = b
                receiver, sender = (team(c), team(a)) if disposal else (team(a), team(c))
            ids = people(asset)
            if not receiver or not sender or receiver == sender or len(ids) != 1:
                continue
            player_name = players[next(iter(ids))]
            asset_rest = re.sub(rf"\b(?:{re.escape(player_name)}|{re.escape(player_name.split()[-1])})\b",
                                "", asset, flags=re.I)
            asset_rest = re.sub(r"\b(?:forward|defenseman|goaltender|goalie)\b", "", asset_rest, flags=re.I)
            if asset_rest.strip():
                continue
            # No incidental third club, conditions, future/past/negated/modal transaction.
            if re.search(r"\b(?:not|could|would|may|might|expected|reportedly|if|after|previously|will)\b",
                         sentence, re.I):
                continue
            all_teams = {aliases[m.group().casefold()] for m in re.finditer(rf"\b(?:{team_re})\b", sentence, re.I)}
            if all_teams != {receiver, sender}:
                continue
            moves = [Move(next(iter(ids)), sender, receiver)]
            opposite = people(consideration or "")
            reason = ""
            if len(opposite) == 1 and not opposite & ids:
                moves.append(Move(next(iter(opposite)), receiver, sender))
                other_name = players[next(iter(opposite))]
                residue = re.sub(rf"\b(?:{re.escape(other_name)}|{re.escape(other_name.split()[-1])})\b",
                                 "", consideration or "", flags=re.I)
                residue = re.sub(r"\b(?:forward|defenseman|goaltender|goalie)\b", "", residue, flags=re.I)
                if residue.strip(" .!"):
                    reason = "компенсация обмена требует проверки"
            else:
                reason = "компенсация обмена требует проверки"
            if not consideration or re.search(r"\b(?:pick|round|conditional|retain|cash|future|and)\b",
                                              consideration, re.I):
                reason = "компенсация обмена требует проверки"
            candidates.append(Trade(tuple(moves), sentence, consideration or "", reason))
            if sentence == lead:
                lead_parsed = True
            break
    if not candidates:
        return Trade()
    if any(c.moves[0] != candidates[0].moves[0] for c in candidates):
        return Trade(reason="заголовок и лид расходятся в направлении обмена")
    complete = [c for c in candidates if c.consideration]
    if len(complete) > 1 and (any(c.moves != complete[0].moves for c in complete)
                              or any(c.reason for c in complete)):
        return Trade(reason="компенсация в заголовке и лиде требует проверки")
    result = max(candidates, key=lambda c: (len(c.moves), bool(c.consideration)))
    if lead and not lead_parsed:
        return Trade(result.moves, result.evidence, result.consideration,
                     "направление/компенсация в лиде требует проверки")
    return result


def prompt(facts: Trade, names: dict, clubs: dict) -> str:
    if not facts.moves:
        return "\n\nНаправление обмена не разобрано: не делай догадок. Пост требует проверки."
    lines = []
    for move in facts.moves:
        name = names.get(str(move.pid), {}).get("ru")
        if name and move.source in clubs and move.destination in clubs:
            lines.append(f"{clubs[move.destination]} получил: {name}; {clubs[move.source]} отдал: {name}.")
    return ("\n\nПроверенные направления обмена (не меняй местами):\n" + "\n".join(lines)
            + "\nНазывай направление словами получил/отдал. Компенсацию бери только из источника.")


def check(text: str, facts: Trade, names: dict, clubs: dict) -> tuple[list[str], list[str]]:
    issues, notes = [], []
    if facts.reason:
        notes.append(f"обмен: {facts.reason}")
    if not facts.moves:
        return issues, notes
    verified = set()
    for sentence in re.split(r"[.!?\n]+", text):
        if not sentence.strip():
            continue
        direction = re.search(r"\b(получил[аи]?|отдал[аи]?)\b", sentence, re.I)
        transactional = re.search(r"получ|отда|обмен|переш|переход|отправ|взамен|направл|достал|приобр",
                                  sentence, re.I)
        if not transactional:
            # Even without a transfer verb, "Wood is now in Nashville" is a claim
            # about affiliation. Only club-free statistical context can auto-pass.
            has_club = any(guard.mentions(sentence, name) for name in clubs.values())
            has_player = any(guard.mentions(sentence, rec["surname"]) for rec in names.values())
            stats = re.search(r"набрал|сыграл|пров[её]л|забил|очк|матч|передач|шайб|гол[ауы]?\b", sentence, re.I)
            if has_club or (has_player and not stats):
                notes.append("обмен: принадлежность игрока/клуба требует проверки")
            continue
        matched = False
        if direction:
            before, after = sentence[:direction.start()], sentence[direction.end():]
            subjects = {code for code, name in clubs.items() if guard.mentions(before, name)}
            assets = {m.pid for m in facts.moves if str(m.pid) in names
                      and guard.mentions(after, names[str(m.pid)]["surname"])}
            if len(subjects) == 1 and len(assets) == 1:
                pid, club = next(iter(assets)), next(iter(subjects))
                move = next(m for m in facts.moves if m.pid == pid)
                receiving = direction.group().lower().startswith("получ")
                expected = move.destination if receiving else move.source
                if club != expected:
                    issues.append(f"направление обмена противоречит источнику: {names[str(pid)]['ru']}")
                else:
                    verified.add(pid)
                    # A second club or extra transaction clause needs separate verification.
                    remainder = re.split(r"[,;]|\b(?:а|но|взамен)\b", after, flags=re.I)
                    matched = len(remainder) == 1 and not re.search(
                        r"\b(?:из|от|в|для|за|не)\b", sentence, re.I)
                    matched &= len(re.findall(r"получ|отда|обмен|переш|переход|отправ|взамен|направл|достал|приобр",
                                              sentence, re.I)) == 1
        if not matched:
            notes.append("обмен: формулировка направления/компенсации требует проверки")
    if facts.moves[0].pid not in verified:
        notes.append("обмен: нет проверенной формулировки получил/отдал для героя")
    return list(dict.fromkeys(issues)), list(dict.fromkeys(notes))
