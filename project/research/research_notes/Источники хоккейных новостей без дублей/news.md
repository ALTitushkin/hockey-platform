# Дополнительные хоккейные новостные ленты

## Какие ленты действительно доступны и что в них есть?

### Takeaway
Для пилота наиболее практичны DailyFaceoff RSS и официальный AHL RSS. ESPN технически читается, но ограничения роботов и неподтверждённые условия API требуют отдельного решения; THW RSS исключить из автоматического сбора из-за прямого robots Disallow /feed/.

### Cited Findings
- Проверка: реальные HTTP GET через PowerShell Invoke-WebRequest с обычным TLS, без авторизации, cookies, обхода капчи или подмены агента. HTTP Date ответов — Sat, 31 Oct 2026 19:00:01–19:00:07 GMT, что совпадает с датой среды 31.10.2026. Web fetch не смог прочитать XML из-за unsupported content-type; это ограничение инструмента, а не отказ источника. Первое sandbox-чтение завершилось TLS Authentication failed, затем сетевое чтение было выполнено с явным штатным одобрением.
- **DailyFaceoff:** [https://www.dailyfaceoff.com/feed](https://www.dailyfaceoff.com/feed) HTTP200 application/xml, 25 items. Поля title, description, link, guid, category, dc:creator, pubDate, enclosure, content:encoded, media:thumbnail/media:content. Первый guid равен ссылке `https://www.dailyfaceoff.com/news/tampa-bay-lightning-jon-cooper-nikita-kucherov-fully-committed-team-trade-request-nhl`, дата `Sat, 31 Oct 2026 18:49:59 GMT`. Полный HTML content:encoded — 3946 символов, description — 97. Важно читать XML namespace/CDATA корректно: PowerShell `.encoded.InnerText` ошибочно дал 0; прямой обход ChildNodes подтвердил 3946. [Robots](https://www.dailyfaceoff.com/robots.txt) Allow /, Disallow /api/ и /cms/; эти закрытые пути не запрашивались. Независимое издание, не официальный орган NHL/NHLPA: [контакты DFO](https://www.dailyfaceoff.com/contact-us).
- **Официальный AHL:** [https://theahl.com/feed](https://theahl.com/feed) HTTP200 application/rss+xml, 10 items. WordPress RSS с title, link, pubDate, guid вида `https://theahl.com/?p=100360`, dc:creator, category, description и content:encoded HTML. Последняя запись `Monsters meet Admirals in AHLTV Freeview today`, дата `Sat, 31 Oct 2026 11:00:47 +0000`, ведёт на YouTube; следующая `Tynan reaches 700 AHL points`, дата `Sat, 31 Oct 2026 02:00:08 +0000`, content:encoded 1855 символов. Ссылки часто содержат utm_* и #new_tab. Есть оригиналы и короткие анонсы внешних текстов NHL/FloHockey; в последних body лишь абзац и ссылка, не полный материал. [Robots](https://theahl.com/robots.txt) закрывает /wp-admin/, задаёт Crawl-delay: 10, feed не закрыт.
- **ESPN JSON:** [https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/news?limit=5](https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/news?limit=5) HTTP200 application/json, 5 articles. Поля id, nowId, contentKey, headline, description, published, lastModified, categories (athlete/team/league), byline, links.web.href, links.api.self.href, premium. У первого id=50338055, published=lastModified=`2026-10-31T18:51:31Z`, premium=false; это новость о Кучерове. Полного story в list response нет. Ссылка для читателя: [ESPN story](https://www.espn.com/nhl/story/_/id/50338055/coach-says-nikita-kucherov-committed-lightning). API detail не запрашивался, наличие полного body там не установлено; использовать его для обхода premium нельзя. [API robots](https://site.api.espn.com/robots.txt) вернул Access Denied/403, условия открытого developer API не подтверждены.
- **ESPN RSS:** [https://www.espn.com/espn/rss/nhl/news](https://www.espn.com/espn/rss/nhl/news) HTTP200, 10 items, title/description/dc:creator/link/pubDate/guid; полного body нет. Первый guid=`US-EN-50338055`, ссылка та же, что в JSON; дата RSS `Sat, 31 Oct 2026 14:44:28 EST` не совпадает с published JSON. [www robots](https://www.espn.com/robots.txt) полностью запрещает ChatGPT-User, GPTBot и anthropic-ai среди прочих. [Страница RSS information](https://www.espn.com/espn/news/story?page=rssinfo) в web fetch показала проверку робота; дальнейшего обхода не выполнялось. После обнаружения запретов RSS/страницы ESPN больше не запрашивались.
- **The Hockey Writers:** [https://thehockeywriters.com/feed/](https://thehockeywriters.com/feed/) технически HTTP200 application/rss+xml, 8 items. title/link/pubDate/guid/categories/description, content:encoded отсутствует. Первый item — исторический материал про Calder Trophy 1945–46, guid=`https://thehockeywriters.com/?p=1711984`, pubDate=`Sat, 31 Oct 2026 17:15:00 +0000`, ссылка [материал](https://thehockeywriters.com/revisiting-calder-trophy-seasons-edgar-laprades-1945-46-season/). [Robots](https://thehockeywriters.com/robots.txt) явно Disallow /feed/, Crawl-delay: 5. Запрет обнаружен после первичного теста доступности; последующих запросов feed не было, автоматизацию не рекомендовать.

### Inferences
- DFO полезен для оперативных травм/составов/обменов и цитат, AHL — для проспектов и фарм-клубов «наших». Это редакционная оценка образцов, не измерение уникального охвата.
- THW по проверенному образцу смешивает текущие события и ретроспективы; даже без robots это слабый кандидат на основной срочный поток.

### Gaps
- История uptime, изменения схем, лимиты запросов, ETag/Last-Modified, глубина пагинации, контрактные права на AI-пересказ не проверены. Один успешный GET не означает SLA или лицензию.
- Официальные клубные RSS отдельно не проверялись: официальный дополнительный кандидат здесь AHL.

## Как избегать дублей и неполного пересказа?

### Takeaway
Добавлять источники следует ради новых фактов, объединяя сообщения об одном событии; увеличение числа лент само по себе не доказывает увеличение ценности.

### Cited Findings
- Один инфоповод о Кучерове одновременно первый в [DFO RSS](https://www.dailyfaceoff.com/feed), [ESPN JSON](https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/news?limit=5) и [ESPN RSS](https://www.espn.com/espn/rss/nhl/news). Это наблюдение дубля события, не подтверждение самого сообщения независимой проверкой.
- AHL уже отдаёт ссылки на NHL, например [материал о первом старте Postava](https://www.nhl.com/news/detroit-red-wings-edmonton-oilers-game-recap-october-26-2026), и анонсы FloHockey; одна только уникальность AHL guid не означает новый первоисточник. Источник: [AHL RSS](https://theahl.com/feed).

### Inferences
- Нормализовать source_id как `источник:guid/id`; отдельно canonical URL: удалить utm_* и декоративные фрагменты, сохранить итоговую публичную ссылку. Для ESPN RSS и JSON извлекать numeric story id и считать одним источником.
- Далее ключ события: игрок/команда + тип события + дата события; для матчей gameId. Обновление injury/trade с новым существенным фактом допустимо как update, простое изменение lastModified — не новый пост. Нечёткое сходство заголовков требует контекста; одинаковое имя игрока недостаточно.
- Приоритет первичного подтверждения — лига/клуб; DFO/ESPN использовать как дополнение с атрибуцией сообщения. Полный body DFO/AHL удобен для извлечения фактов, но качество и наличие первичной ссылки проверять. Короткие RSS description ESPN/THW не дают оснований сочинять детали.
- Пилот: DFO+AHL, редкий опрос (например 15 минут, AHL минимум 10 секунд между запросами на хост), сохранение id/url/date/body hash и event_id. Измерять новые релевантные события после вычитания NHL, а не число статей; автоматической публикации в этом исследовании не было.

### Gaps
- Сравнение с текущим NHL feed40 за общую неделю, доля дублей, скорость первичного сообщения и реальный прирост «наших» не измерены. Процент прироста обещать нельзя.

## Какие права на пересказ подтверждены?

### Takeaway
Ссылка не заменяет разрешение на копирование текста/фотографий. Самостоятельное изложение проверяемых фактов и подтверждённая возможность автоматически получать контент — отдельные вопросы; RSS HTTP200 не решает второй.

### Cited Findings
- US Copyright Office различает неохраняемые факты и охраняемую форму выражения: [FAQ](https://www.copyright.gov/help/faq/faq-general.html). Это базовый ориентир авторского права США, а не индивидуальная оценка российского Telegram-канала.
- [Исследование Copyright Office о защите издателей](https://www.copyright.gov/policy/publishersprotections/202206-Publishers-Protections-Study.pdf) отдельно объясняет: неохраняемость фактов не делает готовые news stories свободными для копирования.
- Robots-статусы выше относятся к автоматическому доступу, не лицензируют перепубликацию: [DFO](https://www.dailyfaceoff.com/robots.txt), [AHL](https://theahl.com/robots.txt), [ESPN](https://www.espn.com/robots.txt), [THW](https://thehockeywriters.com/robots.txt).

### Inferences
- Рабочая редакционная граница: краткое самостоятельное изложение нескольких фактов на русском с названием источника и ссылкой, без построчного перевода, переноса структуры статьи и копирования чужих фото. Для слуха явно указывать автора/издание и степень подтверждения. Это снижает риск копирования выражения, но не является юридической гарантией.
- Подключать DFO/AHL в пилот только после проверки действующих условий использования/автоматизации; ESPN оставить исследованным техническим резервом, THW feed не подключать. Не обходить premium, капчу, запрещённые robots пути и не маскировать агента.

### Gaps
- Явные лицензии DFO/AHL на систематический AI-пересказ и разрешение ESPN API не найдены и не подтверждены. Отдельные условия фото, договорные ограничения, применимое право и ограничения коммерческого канала не оценены. Нельзя писать «легальность подтверждена».
