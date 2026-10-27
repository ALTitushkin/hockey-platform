"""Факт-гард: пост не уходит, если в тексте есть то, чего нет в данных.

Проверяется любой текст — и шаблонный, и переписанный языковой моделью:
- каждое число в тексте есть в фактах;
- каждая фамилия из реестра в тексте принадлежит игроку из фактов, и никто из фактов не потерян;
- каждый клуб в тексте есть в фактах;
- нет оборотов-слухов;
- в боевом режиме все игроки поста сверены владельцем (status = confirmed).
Пустой список замечаний = можно отправлять на ✅.
"""

import re

RUMOR = ("по данным источников", "по слухам", "сообщает", "инсайд", "якобы")
# Числительные словами и утверждения, которые гард не может сверить с данными.
# Во вводной фразе модели они запрещены: числа живут только в шаблонном блоке.
UNCHECKABLE = re.compile(
    r"\b(одн?[аиоу]?|один|дв[аеу]х?|две|оба|обе|тр[иеё]х?|четыр\w*|пят\w*|шест\w*|сем\w*|восьм\w*|девят\w*|десят\w*"
    r"|дубл\w*|хет-трик\w*|покер\w*|перв\w*|впервые|рекорд\w*|лучш\w*|худш\w*|сери\w*|подряд|юбилей\w*"
    r"|единственн\w*|вновь|снова|опять|очередн\w*)\b",
    re.IGNORECASE,
)


def check_lead(lead: str, facts: dict, players: dict, teams: dict) -> list[str]:
    """Вводная фраза модели: без чисел и несверяемых утверждений, фамилии и клубы — только из фактов."""
    issues = [f"несверяемое слово: «{m}»" for m in sorted({m.group(0) for m in UNCHECKABLE.finditer(lead)})]
    if re.search(r"\d", lead):
        issues.append("цифры во вводной фразе")
    if "<" in lead or "\n" in lead.strip():
        issues.append("разметка или несколько абзацев во вводной фразе")
    return issues + [i for i in check(lead, facts, players, teams) if not i.startswith("потерян игрок")]


def stem(word: str) -> str:
    """Основа для поиска склонённых форм: «Тампа» → «Тамп», «Кучеров» → «Кучеров» (+ «Кучерова»)."""
    if word.endswith(("ий", "ый", "ой")) and len(word) > 5:  # Ковалёвский → Ковалёвск(ого)
        return word[:-2]
    return word[:-1] if word[-1] in "аяиыеоуьй" and len(word) > 4 else word


# После основы — только падежное окончание, а не любое продолжение: иначе «Джонс» находился
# внутри «Джонстон» и «Ночь в НХЛ» 26.10.2026 не вышла из-за ложной «фамилии без данных».
ENDINGS = ("(?:а|я|у|ю|е|ё|ы|и|о|й|ь|ом|ем|ём|ым|им|ой|ей|ою|ею|ов|ев|ых|их|ам|ям|ами|ями|ах|ях"
           "|ий|ый|ого|его|ому|ему|ую|юю|ая|яя)?")


def mentions(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(stem(word))}{ENDINGS}(?!\w)", text) is not None

def check(text: str, facts: dict, players: dict, teams: dict, publish: bool = False) -> list[str]:
    issues = []
    low = text.lower()

    allowed = {str(n) for n in facts["numbers"]}
    stray = sorted({n for n in re.findall(r"\d+", text) if n not in allowed}, key=int)
    if stray:
        issues.append(f"числа не из данных: {', '.join(stray)}")

    by_surname: dict[str, set[int]] = {}
    for pid, rec in players.items():
        by_surname.setdefault(rec["surname"], set()).add(int(pid))
    for surname, pids in by_surname.items():
        if mentions(text, surname) and not pids & facts["pids"]:
            issues.append(f"фамилия без данных: {surname}")
    for pid in sorted(facts["pids"]):
        rec = players[str(pid)]
        if not re.search(rf"\b{re.escape(rec['surname'])}\b", text):
            issues.append(f"потерян игрок: {rec['ru']}")
        if publish and rec.get("status") != "confirmed":
            issues.append(f"написание не сверено: {rec['ru']}")

    for team in teams.values():
        if mentions(text, team) and team not in facts["teams"]:
            issues.append(f"клуб без данных: {team}")

    issues += [f"оборот-слух: «{w}»" for w in RUMOR if w in low]
    return issues
