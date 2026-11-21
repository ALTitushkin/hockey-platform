"""Травмы НХЛ: неофициальный JSON ESPN (тот же, что на их сайте; без ключа и без документации).

Второй слой проверки «наши в составах»: первый — состав прошлого матча клуба (`nhl.last_lineup`).
ESPN ловит того, кто травмировался в прошлом матче или только что попал в список травмированных.
Сопоставляем по полному имени латиницей: id ESPN и НХЛ разные. Источник недоступен — пустое множество:
пост выходит по составу прошлого матча, а не молчит.
"""

import unicodedata

from news.nhl import ESPN_INJURIES as ESPN
from news.nhl import fetch_json

# «Day-To-Day» не берём: такие часто выходят на лёд — их отсечёт состав прошлого матча, если не играли
OUT = {"Injured Reserve", "Long Term Injured Reserve", "Out", "Suspension"}
REASONS = {
    "Personal": "личные причины", "Illness": "болезнь", "Suspension": "дисквалификация",
    "Coach's Decision": "решение тренера", "Healthy Scratch": "решение тренера",
    "Contract Dispute": "контрактный спор",
}
INJURY_TYPES = set(
    "Abdomen Achilles Ankle Back Concussion Elbow Finger Foot Groin Hand Hip Knee Leg Neck "
    "Pectoral Shoulder Wrist".split()
) | {"Lower Body", "Upper Body"}


def absence_reason(status: str) -> str:
    return {
        "Injured Reserve": "травма", "Long Term Injured Reserve": "травма",
        "Suspension": "дисквалификация", "Out": "причина не указана",
    }.get(status, status)


def norm(name: str) -> str:
    """«Alexander Romanov» и «Alexandér  Romanov» — одно имя: без диакритики, регистра и лишних пробелов."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().replace(".", "").split())


def injured(fetch=fetch_json) -> dict[str, str]:
    """→ {нормализованное имя: статус} для тех, кто не играет."""
    try:
        data = fetch(ESPN)
    except RuntimeError:
        return {}
    out = {}
    for team in data.get("injuries", []):
        for i in team.get("injuries", []):
            status = i.get("status")
            detail = (i.get("details") or {}).get("type")
            reason = REASONS.get(detail)
            name = norm(i.get("athlete", {}).get("displayName", ""))
            if not name:
                continue
            if status == "Day-To-Day" and reason:
                out[name] = f"под вопросом: {reason}"
            elif status in OUT:
                out[name] = reason or ("травма" if detail in INJURY_TYPES else status)
    return out
