#!/usr/bin/env python3
"""Проверка рубрики «В этот день» и синк батча исследователя (запуск из корня репо):

    python tools/validate_calendar.py          # проверить data/calendar.json + отчёт покрытия
    python tools/validate_calendar.py --sync   # проверить батч tools/calendar-build/hockey_calendar.json
                                               # и, если он чистый, записать его в data/calendar.json

Проверки: ключ MM-DD и реальная дата (29 февраля допустимо); у события есть
year (int) / text / cat / reg / conf из допустимых значений; нет дублей текста
внутри даты; video (если есть) — http(s)-ссылка. Отчёт: N/366, самая длинная
дыра, месяцы по заполненности. Код 1 при любой ошибке — гейт деплоя в CI.

Без зависимостей. Покрытие считает тот же calendar_feature.coverage(), что бот
печатает при старте, — цифры в CI и в логе бота не разъедутся.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bot"))
from calendar_feature import CAT_EMOJI, DAYS_IN_MONTH, MONTH_GEN, coverage  # noqa: E402

TARGET = ROOT / "data/calendar.json"
BATCH = ROOT / "tools/calendar-build/hockey_calendar.json"
CATS = set(CAT_EMOJI)
REGS = {"RU", "NHL", "INT", "WORLD"}
CONFS = {"high", "med"}
KEY_RE = re.compile(r"^(\d{2})-(\d{2})$")


def validate(cal) -> list[str]:
    errors: list[str] = []
    if not isinstance(cal, dict):
        return ["ожидался объект {MM-DD: [события]}"]
    for key, events in cal.items():
        m = KEY_RE.match(key)
        if not m or not (1 <= int(m.group(1)) <= 12 and 1 <= int(m.group(2)) <= DAYS_IN_MONTH[int(m.group(1))]):
            errors.append(f"{key}: не реальная дата MM-DD")
            continue
        if not isinstance(events, list):
            errors.append(f"{key}: значение должно быть списком")
            continue
        seen = set()
        for i, ev in enumerate(events):
            where = f"{key}[{i}]"
            if not isinstance(ev.get("year"), int):
                errors.append(f"{where}: year должен быть целым")
            if not ev.get("text"):
                errors.append(f"{where}: пустой text")
            elif ev["text"] in seen:
                errors.append(f"{where}: дубль события внутри даты")
            seen.add(ev.get("text"))
            for field, allowed in (("cat", CATS), ("reg", REGS), ("conf", CONFS)):
                if ev.get(field) not in allowed:
                    errors.append(f"{where}: {field}={ev.get(field)!r} не из {sorted(allowed)}")
            video = ev.get("video")
            if video is not None and not re.match(r"^https?://\S+$", str(video)):
                errors.append(f"{where}: video не похоже на ссылку: {video!r}")
    return errors


def report(cal: dict) -> str:
    n, gap = coverage(cal)
    by_month = []
    for mm, days in DAYS_IN_MONTH.items():
        filled = sum(1 for d in range(1, days + 1) if cal.get(f"{mm:02d}-{d:02d}"))
        by_month.append(f"{MONTH_GEN[mm][:3]} {filled}/{days}")
    return f"покрытие {n}/366 ({n * 100 // 366}%), макс. дыра {gap} дн.\n  " + " · ".join(by_month)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sync", action="store_true", help="проверить батч исследователя и записать в data/calendar.json")
    args = ap.parse_args()

    src = BATCH if args.sync else TARGET
    cal = json.loads(src.read_text(encoding="utf-8"))
    errors = validate(cal)
    if errors:
        print(f"❌ {src.relative_to(ROOT).as_posix()}: {len(errors)} ошибок")
        for e in errors[:50]:
            print(f"  - {e}")
        return 1

    if args.sync:
        before = json.loads(TARGET.read_text(encoding="utf-8")) if TARGET.exists() else {}
        TARGET.write_text(json.dumps(cal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"↻ синк: {coverage(before)[0]}/366 → {coverage(cal)[0]}/366 в data/calendar.json")
    print(f"✅ {(TARGET if args.sync else src).relative_to(ROOT).as_posix()}: {report(cal)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
