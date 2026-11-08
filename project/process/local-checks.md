# Локальные проверки новостника на Windows

08.11.2026. Для проекта подготовлено отдельное `.venv` в релизном worktree.
Полный Python3.12.13 установлен в `D:/MyFolder/.tools/python/cpython-3.12.13-windows-x86_64-none/`;
окружение не зависит от установленного Python/пакетов профиля на дискеC.
В нём Pillow12.3.0, tzdata2026.6, Ruff0.17.4. Продовые requirements не менялись.

Проверки из корня репозитория:

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -q
.venv/Scripts/python.exe -X utf8 -m news.test_news
.venv/Scripts/python.exe -X utf8 -m unittest news.test_delivery -q
.venv/Scripts/ruff.exe check news/ tests/ tools/check_story_publications.py
```

`-X utf8` нужен для кириллицы/эмодзи и чтения UTF-8 фикстур на Windows с Python3.12.
Для stdlib-only инструментов продолжает действовать отдельный runtime из AGENT_RULES;
не добавлять в него зависимости проекта.

Восстановление этого окружения при необходимости:

```powershell
uv python install 3.12.13 --install-dir D:/MyFolder/.tools/python
uv venv --python D:/MyFolder/.tools/python/cpython-3.12.13-windows-x86_64-none/python.exe .venv
uv pip install --python .venv/Scripts/python.exe -r news/requirements.txt ruff
```

Пересборка сохранённых инфоповодов без сети/модели/публикаций:

```powershell
.venv/Scripts/python.exe -X utf8 tools/check_story_publications.py --drafts news/out/audit-2026-11-08 --output news/out/stabilization-replay --at 2026-11-08T13:00:00+03:00
```

`--at` задаёт момент редакционного решения, не меняет дату самого события.
Исходные частные черновики и результат остаются в игнорируемой news/out/.
Скрипт не заменяет полный тест цепочки с квитанциями; тот выполнен через mock транспорта.
