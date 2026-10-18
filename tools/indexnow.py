#!/usr/bin/env python3
"""Отправка адресов сайта поисковикам по протоколу IndexNow (запуск из корня репо):

    python tools/indexnow.py            # все URL из docs/sitemap.xml
    python tools/indexnow.py <url> ...  # только перечисленные

Зачем: Яндекс.Вебмастер не подтверждает сайт в подпапке github.io (проверочный
файл ищет в корне домена, а он не наш). IndexNow подтверждения не требует —
владение доказывает файл-ключ docs/<KEY>.txt. Ключ лежит в подпапке, поэтому
принимаются только URL внутри /hockey-platform/. Яндекс пересылает уведомление
другим участникам IndexNow (Bing и др.).

Запускать после пуша, когда изменения уже на проде. Без внешних зависимостей.
Код возврата 1 при отказе поисковика.
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://altitushkin.github.io/hockey-platform/"
KEY = "060dbc70da350a2e1977726047105edd"  # не секрет: тот же ключ публично лежит в docs/
ENDPOINT = "https://yandex.com/indexnow"


def sitemap_urls() -> list[str]:
    xml = (ROOT / "docs" / "sitemap.xml").read_text(encoding="utf-8")
    return re.findall(r"<loc>([^<]+)</loc>", xml)


def main() -> int:
    urls = sys.argv[1:] or sitemap_urls()
    alien = [u for u in urls if not u.startswith(BASE)]
    if alien:
        print(f"URL вне {BASE} ключ не покрывает: {', '.join(alien)}", file=sys.stderr)
        return 1
    body = json.dumps({
        "host": "altitushkin.github.io",
        "key": KEY,
        "keyLocation": f"{BASE}{KEY}.txt",
        "urlList": urls,
    }).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"OK {resp.status}: отправлено {len(urls)} URL в IndexNow")
            return 0
    except urllib.error.HTTPError as e:
        print(f"Отказ {e.code}: {e.read().decode(errors='replace')[:300]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
