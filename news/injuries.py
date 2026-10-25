"""Травмы НХЛ: неофициальный JSON ESPN (тот же, что на их сайте; без ключа и без документации).

Второй слой проверки «наши в составах»: первый — состав прошлого матча клуба (`nhl.last_lineup`).
ESPN ловит того, кто травмировался в прошлом матче или только что попал в список травмированных.
Сопоставляем по полному имени латиницей: id ESPN и НХЛ разные. Источник недоступен — пустое множество:
пост выходит по составу прошлого матча, а не молчит.
"""

import unicodedata

from news.nhl import fetch_json

ESPN = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries"
# «Day-To-Day» не берём: такие часто выходят на лёд — их отсечёт состав прошлого матча, если не играли
OUT = {"Injured Reserve", "Long Term Injured Reserve", "Out", "Suspension"}


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
            if i.get("status") in OUT:
                out[norm(i.get("athlete", {}).get("displayName", ""))] = i["status"]
    return out
