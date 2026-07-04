# Хэндофф · Sprint 7 · Трек B — финальный список на приёмку → PM

> **От:** чат-разработчик (Cowork) · **Кому:** PM · **Дата:** 28.06.2026
> Реализовано по `s7_pm_decision_base.md`. **Не запушено** — жду приёмки (DoD: «перед пушем — финальный список на приёмку»).
> `validate_data.py` → ✅ зелёный: **62 термина, 3 кластера**, зеркала `data/ ↔ docs/data/` идентичны.

## Сделано
- `tools/add_term.py` пропатчен под схему v2.0: категории `basics/org`, запись полного набора полей (`profiles/cluster/see_also/anchor/source/added/status`), авто-дата, пакетный режим `--batch`. *(тулинг — отдельным коммитом)*
- `clusters.json` (оба зеркала): добавлен кластер `leagues` («Лиги», order 3).
- Добавлено 13 терминов (verified, с источником). Алиасы «хит»/«силовой» оба находят `body-check` ✔.

## Добавленные термины (термин · категория · level · источник)

| ID | Термин (ru) | EN | category | level | cluster | source |
|---|---|---|---|---|---|---|
| handedness | Хват | Handedness | basics | novice (База) | — | nhl.com |
| body-check | Силовой приём (алиас «хит») | Body check / hit | basics | novice (База) | — | nhl.com (Rule 41 — Body Checking) |
| draft | Драфт | Draft | org | fan (Средний) | — | nhl.com/draft |
| penalty-box | Штраф-бокс | Penalty box | rule | novice (База) | — | nhl.com |
| deflection | Подправление | Deflection / tip-in | tactic | fan (Средний) | — | nhl.com |
| 1-on-1 | Один в один | 1-on-1 | tactic | novice (База) | — | nhl.com |
| defenseman-types | Типы защитников | Defenseman types | position | fan (Средний) | — | nhl.com |
| nhl | НХЛ | NHL | org | novice (База) | leagues | nhl.com |
| khl | КХЛ | KHL | org | novice (База) | leagues | khl.ru |
| mhl | МХЛ | MHL | org | novice (База) | leagues | mhl.khl.ru |
| vhl | ВХЛ | VHL | org | novice (База) | leagues | vhlru.ru |
| echl | ECHL | ECHL | org | novice (База) | leagues | echl.com |
| nmhl | НМХЛ | NMHL | org | novice (База) | leagues | nmhl.fhr.ru |

`see_also`: подправление → screen/rebound/slot; один-в-один → breakaway/odd-man-rush; лиги — между собой (6×5); штраф-бокс → penalty-kill/delayed-penalty; хват → wrist-shot/slap-shot; драфт → nhl; типы защ. → defenseman.

## ⚠ Требует решения PM — НМХЛ
При выверке источника: **17.04.2026 НМХЛ официально преобразована в Российскую хоккейную лигу (РХЛ)** — первенство России U20 (источники: fhr.ru, championat.com, ru.wikipedia.org). Карточка заведена как **«НМХЛ»** (частый запрос, сайт `nmhl.fhr.ru` ещё жив), а переход на РХЛ отражён в определении и в `notes`. **Выбор PM:**
1. оставить как есть (НМХЛ + упоминание РХЛ в определении) — *по умолчанию*;
2. переименовать карточку в «РХЛ» (НМХЛ как алиас/`ru_slang`);
3. завести обе.

## К пуш-коммиту (задевает `bot/**`) — нашёл при выверке
1. **Лог-фикс «52 → 49 (+3 на выверке)»** = `bot/bot.py:121` `В базе {len(TERMS)} терминов` — `TERMS` включает 3 на выверке, поэтому показывает 52 вместо 49. Фикс: считать verified-only (как в стартовом логе `len(TERMS) - n_unverified`). *Примечание:* после этого пополнения verified-счётчик станет **62 (+3)** — строка станет динамически корректной.
2. **`bot/search.py`:** `CATEGORY_RU` и `CATEGORY_EMOJI` не знают новых категорий `basics/org` — без правки бот покажет в карточке сырой `basics`/`org` вместо метки. Добавлю в тот же `bot/**`-коммит («Базовое / техника», «Лиги / организации»).

## Отложено
- **«Подкидка»** — формат не уточнён (flip / scoop), не добавлял, за PM.

## После приёмки (одним заходом)
add_term.py-патч (коммит 1) · данные `data/**` (коммит 2) · `bot/**` лог-фикс + метки категорий (коммит 3) · CHANGELOG · `git push origin main` (автодеплой бота + сайта).

---
**Источники выверки:** nhl.com · khl.ru · mhl.khl.ru · vhlru.ru · echl.com (en.wikipedia.org/ECHL) · nmhl.fhr.ru · fhr.ru · championat.com · ru.wikipedia.org (НМХЛ→РХЛ).
