# Спек: веб-GUI на Postgres — серверная фильтрация, пагинация, единый слой доступа к данным

Статус: черновик v4 · 2026-08-04
Происхождение: `/systematic-debugging` по задержке фильтров на `ai-policy-jobs.vercel.app` (сессия 2026-08-04, коммит `4989539`) → куратор сформулировал 5 критериев редизайна → v1 → куратор перед реализацией добавил 3 требования (конфиги-в-таблицы, Alembic, полнотекстовый поиск) и снял ограничение на Neon-ресурсы Scopus Search → v2 → куратор перед стартом `/feature-workflow` потребовал полноценное тестовое покрытие, включая интеграционные/сквозные тесты, первым шагом процесса, не финальным довеском.

## 0. Что и зачем

v1 закрывала 5 исходных критериев (нет дублирования фильтрации, полный API, запас на рост, серверная фильтрация+пагинация, DIP/SOLID) миграцией с SQLite-в-Blob на Neon Postgres. Куратор до начала реализации добавил три требования, которые v1 сознательно выносила «вне скоупа» — ревизия ниже вводит их полноценно, а не косметически:

1. **Конфиги в таблицы** — `config/orgs.yaml`/`config/searches.yaml` остаются источником правды для куратора (правятся руками, не через код/UI — этот принцип `CLAUDE.md` не отменяется), но синхронизируются в Postgres-таблицы `organizations`/`searches`, дающие критерию 3 («3-4 таблицы») реальное, не отложенное на будущее наполнение.
2. **Alembic** — v1 отклоняла его как избыточный при «одной таблице, стабильной схеме»; эта посылка была верна только для v1 и стала неверна в v2: ниже минимум 5 миграций уже внутри этого же спека (создание 3 таблиц, FK-колонка, полнотекстовый индекс) — именно тот сценарий, для которого Alembic существует.
3. **Полнотекстовый поиск** — v1 отклоняла его по причине «на 1000 строк индекс не нужен для скорости», но это неверная причина отклонения: ценность full-text — не скорость, а качество поиска (стемминг, ранжирование, многословные запросы), не зависящее от объёма данных. Добавляется как `tsvector`-колонка + `websearch_to_tsquery`.

## 0bis. Тестовая стратегия (первый шаг реализации, не финальная сверка)

Проверено 2026-08-04: сегодня `postings.py`/`status.py`'s собственные `BaseHTTPRequestHandler`-классы (парсинг query-string, cookie-проверка, JSON-ответ) не покрыты ни одним pytest-тестом — только `_logic.py`/`_auth.py` тестируются напрямую, HTTP-слой проверялся исключительно вручную curl'ом/браузером. С ростом схемы (3 таблицы, 5 миграций, диалект-ветка под FTS) риск, что модули по отдельности зелёные, а их стыковка — нет, растёт быстрее, чем растёт сама схема. Четыре яруса тестов, каждый закрывает свой класс риска:

1. **Unit (как в v1/v2, без изменений)** — `tests/web/test_repo.py`, `tests/test_postgres_sync.py`: SQLite-in-memory, без сети, часть обычного `.venv/bin/pytest`.
2. **HTTP-интеграционные (новое, но герметично)** — `tests/web/test_handlers.py`: поднимает `postings.handler`/`status.handler`/`login.handler` на `HTTPServer(("127.0.0.1", 0), ...)` в фоновом потоке, стучится настоящими HTTP-запросами (через `requests`), движок БД — `tmp_path`-SQLite через переопределение `_repo.get_engine()`. Закрывает ровно тот разрыв, что найден выше — сегодня никто не проверяет, что `_parse_filters`/cookie-проверка/`write_json` реально стыкуются с `_repo`.
3. **Пайплайн-интеграционные (новое, герметично)** — `tests/test_run_pipeline.py`: настоящий `run.main(...)` с замоканными по HTTP коннекторами (`requests-mock`, уже есть в `requirements-dev.txt`) → полная цепочка `postgres_sync`'а (5 функций подряд) против `tmp_path`-SQLite вместо Postgres → проверяет итоговое состояние всех 3 таблиц разом и идемпотентность повторного прогона. Это главный источник риска во всём спеке («стыкуются ли новые функции синхронизации с уже работающим `store.py`»), и по историческому прецеденту этого репозитория (см. `docs/backlog/BACKLOG.md` про однажды нарушенную герметичность) — именно такие межмодульные сценарии проскакивают мимо unit-тестов.
4. **Postgres-интеграционные, только CI (новое, НЕ герметично сознательно)** — `tests/integration/test_migrations.py`: требует настоящий Postgres (CI service-container, `postgres:17`), гоняет `alembic upgrade head`, сверяет результат с `_schema.py`'s metadata (drift-check по образцу `scopus_search_code`'s `alembic check`, `.github/workflows/tests.yml:114-118` в референсе), проверяет `search_vector`/GIN и реальное ранжирование `websearch_to_tsquery` — то, что в принципе не воспроизводимо на SQLite (см. §5). Помечается `@pytest.mark.integration`, исключается из дефолтного прогона (`pyproject.toml`: `addopts = "-m 'not integration'"`) — `.venv/bin/pytest` у куратора остаётся ровно таким же быстрым и герметичным, каким был; новый CI-джоб `test-integration` — единственное место, где это реально гоняется.

**Не добавляется:** браузерный E2E-фреймворк (Playwright/Cypress и т.п.) как новая постоянная зависимость — это отдельное, более тяжёлое решение (новый рантайм, новый CI-джоб, новое обслуживание), которое куратор не называл явно. Роль «сквозного от пользователя» яруса остаётся за живой проверкой в браузере через chrome-devtools в Step 6 `/feature-workflow` (уже дважды успешно применялась в этой сессии) — с явным замером задержки (curl+TTFB), а не только визуальным осмотром.

Тестовая инфраструктура (маркер, CI-джоб, каркас `tests/integration/`) — **один из первых двух коммитов плана** (сразу после зависимостей, от которых сама же зависит), не последний: остальные коммиты пишутся против уже существующих ярусов, а не наоборот.

## 1. Диагноз (не изменился с v1)

Живой замер на проде: обработка на сервере — 0.157с, тело ответа — 1.7 МБ (полные описания всех 344 вакансий), задержка 2-15с — целиком передача этого тела. Причина — Blob хранит файл целиком, у него нет `WHERE`/`LIMIT`; «серверная» фильтрация в `_logic.py` была Python-циклом после `SELECT *`, а не SQL. Референс `scopus_search_code` (FastAPI+Postgres+SQLAlchemy, 8 таблиц, ~140k строк) подтверждает правильный паттерн: тонкий клиент + один репозиторий, строящий `WHERE` один раз для списка и подсчёта — недостижимо поверх Blob, достижимо поверх настоящей СУБД.

## 2. Хранилище: Neon Postgres

- Новый проект в аккаунте куратора (`quiet-sea-26110140`, создан 2026-08-04) — **фактический регион `aws-us-west-2`, не запланированный `aws-us-east-1`**. Причина расхождения: единственный доступный инструмент провижининга в этой сессии (`mcp__neon__create_project`) не принимает параметр региона — ни через MCP, ни через `neonctl` (CLI требует интерактивный OAuth-логин в браузере, недоступный в этой среде). Последствие измеримо, но не критично: `us-west-2` всё равно на одном континенте с дефолтным регионом функций Vercel (`iad1`, US East — подтверждено заголовком `x-vercel-id: fra1::iad1::...` на живом проде), что даёт кросс-континентальные ~60-80мс RTT вместо трансатлантических ~100-110мс у `eu-central-1` — и то, и другое на порядки меньше тех 2-15 секунд, которые были в исходной проблеме, потому что именно они были следствием скачивания всего Blob-файла, а не сетевой задержки как таковой. Живая перепровизовка в `us-east-1` вручную через консоль Neon — не заблокировано, но не оправдано ради разницы в единицы-десятки мс при уже решённой проблеме на порядки секунд; при желании куратор может сделать это позже отдельным шагом.
- **Уточнение по вводной куратора об удалении данных Scopus Search.** Проверено 2026-08-04: free-tier Neon даёт квоты **на проект**, не на аккаунт (100 проектов, у каждого своих 0.5 ГБ хранилища / 100 CU-часов в месяц) — новый проект job-search получает собственную квоту независимо от того, что лежит в Scopus Search. Технической необходимости удалять данные Scopus Search для провижининга job-search нет — эта посылка в вводной куратора не подтвердилась. Если куратор всё равно хочет прибрать Scopus Search по несвязанным причинам (не нужны, экономия), это отдельная задача на живой, чужой для этого спека проект — не делаю это неявным следствием текущей работы и не выполняю без отдельного явного запроса.

## 3. Схема данных

**`postings`** — как в v1, порт `store.py`'s SQLite DDL на Postgres-типы (SERIAL вместо AUTOINCREMENT, тот же `CHECK(status IN (...))`, `UNIQUE(source, ats_id)`), плюс `org_id INTEGER REFERENCES organizations(id)` (см. ниже) и индексы на `org`, `tier`, `status`, `workplace_type`.

**`organizations`** (новая) — измерено 2026-08-04: `config/orgs.yaml` содержит **5** курируемых записей (`org`, `tier`, `ats`, `slug`), но в `postings` сейчас **244** различных значения `org` — подавляющее большинство из query-семейства источников (himalayas 107, adzuna 44, jobspy_indeed 59, jobspy_linkedin 35 различных орг.), которые в `orgs.yaml` не перечислены и перечислены быть не могут (query-коннекторы находят организации из данных, а не по заранее известному списку — см. комментарий в самом `orgs.yaml`). Из этого следует форма таблицы:

```sql
CREATE TABLE organizations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    tier TEXT,              -- NULL для discovered — курируется только для orgs.yaml-организаций
    ats TEXT,                -- lever|greenhouse|personio; NULL для discovered
    slug TEXT,                -- NULL для discovered
    origin TEXT NOT NULL CHECK (origin IN ('curated', 'discovered')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Наполняется в два прохода при каждой синхронизации (см. §7): (1) upsert 5 строк из `orgs.yaml` (`origin='curated'`, обновляет tier/ats/slug при изменении в YAML), (2) для каждого `DISTINCT org` из локального `postings`, отсутствующего в таблице — insert-стаб (`origin='discovered'`, остальные поля NULL) c `ON CONFLICT (name) DO NOTHING`, чтобы никогда не затереть курируемую запись. **Важно, что это НЕ меняет:** `postings.tier` остаётся независимой колонкой, как сегодня в `store.py` — измерено, что tier для query-семейства вычисляется коннектором по географии (postings из adzuna/himalayas/jobspy носят tier даже для организаций, которых нет в `orgs.yaml`), а не выводится из организации. `organizations.tier` — это ДОПОЛНИТЕЛЬНАЯ курируемая метаинформация, не источник правды для фильтрации по tier; `postings.org_id` — мягкая связь для будущих джойнов/аналитики, не замена существующей фильтрации по `postings.org`/`postings.tier`.

**`searches`** (новая) — измерено: `config/searches.yaml`, **6** записей, поля разнятся по источнику (himalayas: `query`; adzuna: `phrase`+`country`; jobspy: `query`+`location`(+`country_indeed` у indeed)). Нормализовать в плоские колонки без потерь нельзя без N nullable-полей под источник — вместо этого:

```sql
CREATE TABLE searches (
    id SERIAL PRIMARY KEY,
    search_id TEXT NOT NULL UNIQUE,  -- searches.yaml's own 'id', напр. 'himalayas-policy'
    source TEXT NOT NULL,
    query_text TEXT,                  -- coalesce(query, phrase)
    location TEXT,                     -- coalesce(location, country, country_indeed)
    manual BOOLEAN NOT NULL DEFAULT false,
    raw JSONB NOT NULL,                 -- полная исходная запись YAML, без потерь
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`searches` синхронизируется **полным зеркалированием** (delete+insert из `searches.yaml`), не upsert — в отличие от `organizations`, у `searches` нет второго ("discovered") источника данных, который нужно бы сохранить, поэтому зеркалирование безопасно и, в отличие от upsert-only, само убирает записи об удалённых из YAML спеках.

**`postings.search_id` — сознательно НЕ добавляется.** Проверено: `store.py`'s `upsert_search_postings(conn, source, postings)` (`scripts/store.py:235`) не принимает и не сохраняет id конкретного search-спека — только широкий `source` (`himalayas`, не `himalayas-policy`). Добавить эту связь означало бы менять сигнатуру upsert-функций и коннекторы, вызывающие их — то есть трогать инвариантную, уже корректную логику `store.py`, ради функциональности, которую куратор не запрашивал. `searches` — самостоятельная справочная таблица, не связанная FK с `postings`.

Ни `organizations`, ни `searches` не получают в этом спеке UI-поверхности в веб-GUI — только схема и синхронизация; отображение в интерфейсе (если понадобится) — отдельное решение позже.

## 4. Миграции: Alembic

Референс — `scopus_search_code`'s `alembic/` (26 миграций, `alembic/env.py:1-113`). Переносим форму, не сложность (там 8 таблиц/140k строк, `_include_object`-исключения под GiST/партиальные индексы, async-движок, merge-миграции от параллельных веток — ничего из этого не оправдано на нашем масштабе):

- `alembic/env.py` — `target_metadata` указывает на общий `MetaData()` из `web/api/_schema.py` (единое определение `postings`/`organizations`/`searches`, как и для тестов — см. §6). URL Postgres — `os.environ["DATABASE_URL"]` напрямую (в этом репо нет settings-синглтона, как у `scopus_search`; читать env — уже устоявшийся паттерн, см. `_auth.py`/`_blob.py`).
- Именование — `NNNN_slug.py` последовательно с самого начала (референс сам рекомендует это в ретроспективе, вместо того как у них разъехалось между случайным hex и последовательным).
**Две миграции, не пять — решение принято при реализации, не в этом черновике.** Изначальный план дробил раскат на `0001_create_postings`/`0002_create_organizations`/`0003_create_searches`/`0004_add_postings_org_id` — но это симулировало бы органическую историю, которой не было: `_schema.py`'s `postings` уже содержит `org_id` с самого начала (не добавлен позже через `ALTER`), а все три таблицы деплоятся в одном релизе, не в четырёх последовательных. У референса (`scopus_search_code`) миграция-на-таблицу отражает реальный факт «эта таблица добавлена в отдельном спринте» — у нас такого факта нет, изображать его было бы лишней церемонией. Итог: `0001_initial_schema.py` (все три таблицы через `alembic revision --autogenerate` против настоящей пустой Neon-БД — гарантирует точное совпадение с `_schema.py`, а не ручной DDL, рискующий разъехаться), `0002_add_search_vector.py` — raw `op.execute` (генерируемая колонка не выразима через обычный Core `Column`, тот же паттерн, что у референса для GiST-индексов).
- `alembic upgrade head` — вызывается из `scripts/postgres_sync.py` (программно, `alembic.config.Config` + `alembic.command.upgrade`, не подпроцессом) в начале каждого прогона `run.py` — идемпотентно, тот же принцип, что у референса («safe on every deploy»), адаптированный под наш деплой без Docker-энтрипойнта.
- Тесты Alembic не используют — как и у референса, `tests/web/test_repo.py` строит схему прямо из `_schema.py`'s `MetaData.create_all()` против SQLite-in-memory, минуя миграции полностью (быстрее и герметичнее). Alembic — единственный источник правды схемы **для Postgres**, `_schema.py`'s `MetaData` — единственный источник правды **для тестов и для `target_metadata`**; они обязаны совпадать, что и обеспечивает Alembic autogenerate при последующих правках схемы.

## 5. Полнотекстовый поиск

`search_vector` — генерируемая колонка на `postings` (только в Postgres-миграции `0002`, НЕ в переносимом `_schema.py`'s `Table` — `tsvector` не существует в SQLite, и это единственная сознательная точка, где код перестаёт быть диалект-независимым):

```sql
ALTER TABLE postings ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B')
  ) STORED;
CREATE INDEX ix_postings_search_vector ON postings USING GIN (search_vector);
```

Заголовок весит больше описания (`'A'` > `'B'`) — совпадение в title ранжируется выше. `websearch_to_tsquery` (не `plainto_tsquery`) — понимает бытовой синтаксис поисковой строки («в кавычках» — точная фраза, `-слово` — исключение), ближе к ожиданиям от поля поиска, чем `plainto_tsquery`.

`_repo.py`'s построение запроса намеренно ветвится по диалекту — единственное такое ветвление во всём слое:
```python
if engine.dialect.name == "postgresql" and query_text:
    where.append(postings.c.search_vector.op("@@")(func.websearch_to_tsquery("english", query_text)))
    order_by = func.ts_rank(postings.c.search_vector, func.websearch_to_tsquery("english", query_text)).desc()
else:
    # SQLite (тесты) и Postgres без активного поиска — прежнее LIKE-совпадение
    like = f"%{query_text.lower()}%"
    where.append(or_(func.lower(postings.c.title).like(like), func.lower(postings.c.description).like(like)))
    order_by = postings.c.posted_at.desc()
```
Тесты проверяют «поиск находит нужные строки» (LIKE-путь) — само ранжирование/стемминг `tsvector` в pytest не воспроизводимо без реального Postgres в тестах (что нарушило бы герметичность) и проверяется только живым прогоном на проде (чек-лист).

## 6. Единый слой доступа: `web/api/_schema.py` + `web/api/_repo.py`

Без изменений в архитектуре относительно v1: одна `MetaData()`, диалект-независимые `Table`-определения (кроме `search_vector`, см. §5), `_repo.py`'s `_build_where`/`list_postings`/`set_status` принимают `engine` явным параметром — тесты передают SQLite-in-memory, прод передаёт Neon. Инверсия зависимостей — без ABC/DI-фреймворка, тем же обоснованием, что в v1 (референсный repo сам называет полный слой абстракций избыточным при 3-4 таблицах).

## 7. HTTP-слой и пайплайн `run.py`

Без изменений от v1 в `postings.py`/`status.py` (тонкие обработчики, `{"items", "total", "page", "size"}`, `size` по умолчанию 60, максимум 200).

`scripts/postgres_sync.py` теперь пять функций, в этом порядке при каждом прогоне `run.py.__main__`:
1. `ensure_schema(pg_engine)` — `alembic upgrade head` программно.
2. `pull_statuses(pg_engine, sqlite_conn)` — как в v1, fail-loud при ошибке.
3. *(коннекторы `store.py` прогоняются, без изменений)*
4. `sync_organizations(pg_engine, orgs_yaml_path, sqlite_conn)` — upsert curated + discovered, `ON CONFLICT (name) DO NOTHING` для discovered.
5. `sync_searches(pg_engine, searches_yaml_path)` — полное зеркалирование из YAML.
6. `mirror_to_postgres(pg_engine, sqlite_conn)` — как в v1 (одна транзакция, TRUNCATE+INSERT), теперь дополнительно резолвит `org_id` джойном по `organizations.name = postings.org` при вставке.

Порядок 4→6 обязателен: `org_id` резолвится по уже наполненной `organizations`.

## 8. Фронтенд — без изменений от v1

Тонкий клиент, серверная пагинация, кнопка «Load more». Поле поиска ведёт себя иначе только на бэкенде (ранжирование вместо substring-фильтра) — контракт запроса (`?query=...`) не меняется, фронтенду не нужно знать о `tsvector`.

## Design rationale / отвергнутые альтернативы

- **`organizations`: upsert (не полное зеркалирование), в отличие от `searches`.** У `organizations` два независимых источника данных (курируемый YAML + обнаруженные из `postings.org`) — зеркалирование по одному YAML стёрло бы 239 из 244 организаций. У `searches` единственный источник — YAML, поэтому там безопасно и даже правильно зеркалировать полностью (стирает записи об удалённых спеках).
- **`postings.tier`/`postings.org` остаются собственными колонками, не выводятся джойном из `organizations`.** Измерено: tier для query-семейства зависит от географии конкретной вакансии, а не от организации — джойн на `organizations.tier` дал бы неверный результат для 239 из 244 организаций (у которых `organizations.tier IS NULL`). `org_id` — дополнительная связь для будущего, не замена текущей фильтрации.
- **`postings.search_id` не добавляется.** Потребовало бы менять сигнатуру `store.py`'s upsert-функций (инвариант, который этот и предыдущий спек сознательно не трогают) ради функциональности, которую куратор не запрашивал — запрошена была конвертация конфигов в таблицы, не сквозная трассировка вакансии до search-спека.
- **`search_vector` — единственное диалект-зависимое место в `_repo.py`.** Portable-схема через SQLAlchemy Core (обоснование не изменилось с v1) не покрывает нативный Postgres FTS — у SQLite нет эквивалента `tsvector`/`GIN`/`websearch_to_tsquery` (FTS5 — структурно другой механизм, virtual table, не колонка). Вместо расширения диалект-независимости на весь модуль — один явный `if engine.dialect.name == "postgresql"` в одном месте, задокументированный, а не спрятанный.
- **Не форсируем Alembic-миграцию для backfill `org_id`.** `mirror_to_postgres` и так перезаливает `postings` целиком на каждом прогоне — отдельная одноразовая data-миграция дублировала бы то, что обычный прогон сделает сам через несколько минут после первого деплоя.
- **Не выполняю очистку Neon-проекта Scopus Search.** Вводная куратора была основана на посылке (общая квота на аккаунт), которая не подтвердилась при проверке (квота — на проект); без технической необходимости трогать чужой живой проект в рамках этого спека не буду.

## Тестовое покрытие

Полная стратегия — §0bis (четыре яруса, тестовая инфраструктура как первый коммит). Кратко по модулям:

- `tests/web/test_repo.py` (unit) — `org_id`-резолюция, полнотекстовый поиск по LIKE-fallback-ветке (диалект `sqlite` в тестовом `engine.dialect.name`).
- `tests/web/test_handlers.py` (HTTP-интеграционные, новое) — реальный `HTTPServer` на loopback против `postings.handler`/`status.handler`/`login.handler`.
- `tests/test_postgres_sync.py` (unit) — `sync_organizations` (upsert не затирает curated), `sync_searches` (зеркалирование убирает удалённые спеки), `mirror_to_postgres` с `org_id`-резолюцией.
- `tests/test_run_pipeline.py` (пайплайн-интеграционные, новое) — полный `run.main()` → вся цепочка `postgres_sync` → итоговое состояние + идемпотентность.
- `tests/integration/test_migrations.py` (Postgres-интеграционные, CI-only, новое) — реальные миграции + FTS-ранжирование на настоящем Postgres.
- Герметичность **дефолтного** `.venv/bin/pytest` не меняется — ни один из первых трёх ярусов не открывает `data/jobs.db`, не стучится во внешнюю сеть, не поднимает реальный Postgres; четвёртый ярус физически не может быть герметичным (тестирует Postgres-специфичный SQL) и поэтому явно вынесен в CI-only `integration`-маркер, а не в общий прогон.

## План коммитов

Тот же принцип упорядочивания, что в v1/v2 (переключение чтения на Postgres — только после первого реального наполнения БД), плюс новый принцип из §0bis: тестовая инфраструктура — первый коммит, каждый следующий коммит пишется вместе со своим ярусом тестов, а не после него:

Порядок ниже отличается от черновика v3 ещё в одном месте: зависимости (`sqlalchemy`/`psycopg`/`alembic`) обязаны идти ПЕРВЫМ коммитом, не пятым — `_schema.py`, Alembic и `_repo.py` не импортируются без них. Более ранняя версия плана сама на этом бы упала при первом же `git commit` — поймано на повторном самопроверочном проходе перед началом кода, а не посреди реализации.

1. `chore: add sqlalchemy + psycopg[binary] + alembic to web/requirements.txt and requirements.txt`
2. `test: add integration tier — pytest marker, CI postgres service job, tests/integration/ scaffold` (теперь может писать реальный smoke-тест на подключение — psycopg уже доступен)
3. `feat(web): add _schema.py — postings/organizations/searches Table definitions`
4. `feat(db): add alembic — env.py wired to _schema.py metadata, migrations 0001-0002` (+ `tests/integration/test_migrations.py` наполняется здесь же, не в конце)
5. `feat(web): add _repo.py — filtering, pagination, org_id join, FTS dialect branch` (+ `tests/web/test_repo.py`)
6. `feat(scripts): add postgres_sync.py (ensure_schema/pull_statuses/sync_organizations/sync_searches/mirror_to_postgres), wire into run.py __main__` (+ `tests/test_postgres_sync.py` и `tests/test_run_pipeline.py`)
7. **[ручной шаг, не коммит]** — `.venv/bin/python scripts/run.py` локально: прогоняет `alembic upgrade head`, впервые наполняет все 3 таблицы в Postgres
8. `feat(web): rewrite postings.py/status.py as thin handlers over _repo` (безопасно только после шага 7; + `tests/web/test_handlers.py`)
9. `feat(web): app.js — server-side pagination, drop client-side filter cache`
10. `chore: remove _blob.py, blob_sync.py, _logic.py, their tests, Blob env vars`
11. `docs: close spec, update CLAUDE.md/cli_reference.md`

## Чек-лист реализации

- [x] `pyproject.toml` — `integration`-маркер зарегистрирован, `addopts = "-m 'not integration'"`; `tests/integration/` каркас; `.github/workflows/tests.yml` — новый `test-integration`-джоб с Postgres service-контейнером (`fe7a922`)
- [x] `web/api/_schema.py` — `postings`/`organizations`/`searches` Table-определения, индексы
- [x] `alembic/env.py` + `alembic.ini`, миграции `0001`-`0002` (см. §4) — `include_object`-исключение для `search_vector`/`ix_postings_search_vector` добавлено по образцу референса, `alembic check` живьём подтверждает отсутствие дрейфа
- [x] `tests/integration/test_migrations.py` — миграции применяются на реальном Postgres (Neon, `quiet-sea-26110140`), схема совпадает с `_schema.py`'s metadata, FTS-ранжирование проверено вживую (title-match 0.995 > description-only-match 0.366)
- [x] `web/api/_repo.py` — `_build_where` (с FTS-веткой), `list_postings`, `set_status`, `get_engine`; попутно нашёл и починил регресс в собственном черновике — забыл перенести `COALESCE(posted_at, first_seen)` из старого `_logic.py`
- [x] `tests/web/test_repo.py` (15 тестов) — LIKE-fallback ветка через SQLite; Postgres-ветка (`websearch_to_tsquery`) дополнительно проверена вживую через сам `_repo.list_postings` против реального Neon, не только через raw SQL
- [x] `web/api/postings.py`/`status.py` переписаны как тонкие обработчики — `status.py` заодно упростился: транзакционный `UPDATE` вместо tempfile+ETag+blob-upload
- [x] `tests/web/test_handlers.py` (11 тестов) — HTTP-интеграционные тесты через реальный `HTTPServer` на loopback, `tmp_path`-SQLite вместо `_repo.get_engine()`. Живая находка по пути: `login.py`'s `Secure`-cookie корректно не пересылается `requests` обратно по голому HTTP (как и настоящим браузером) — тест поправлен на прямое сравнение значения куки, не на то, что джар сам её отправит повторно
- [x] `sqlalchemy==2.0.51`, `psycopg[binary]==3.3.4` (сверено на PyPI 2026-08-04) — в `web/requirements.txt` И корневом `requirements.txt`; `alembic==1.19.0` — ТОЛЬКО в корневой `requirements.txt` (`edd3395`)
- [ ] Neon-проект создан в `aws-us-east-1`, подключён через Vercel Marketplace, `DATABASE_URL` в Vercel env + локальном `.env`
- [x] `scripts/postgres_sync.py` — `ensure_schema`, `pull_statuses`, `sync_organizations`, `sync_searches`, `mirror_to_postgres`, `get_engine`; `run.py.__main__` использует его вместо `blob_sync`. Попутно добавлена защита `mirror_to_postgres` от опустошения Postgres при (ошибочно) пустой локальной SQLite — параллель с уже существующей в `store.py` защитой от «успешный-но-пустой ответ = всё закрыто», которой не было в исходном плане
- [x] `tests/test_postgres_sync.py` (7 тестов) — по каждой из функций синхронизации
- [x] `tests/test_run_pipeline.py` (3 теста) — полный `run.main()` → `postgres_sync`-цепочка → все 3 таблицы, идемпотентность, и (главное) сохранение статуса, записанного «через веб-GUI», при повторном прогоне — свойство, которое раньше давал `blob_sync`
- [x] Postgres впервые наполнен реальным прогоном `scripts/run.py` ЛОКАЛЬНО (включая `alembic upgrade head`) — до деплоя коммита, переключающего `postings.py`/`status.py` на `_repo`. Итог: 349 postings (349 local — идентично), 249 organizations (5 curated + 244 discovered), 6 searches, 0 строк с неразрешённым `org_id`. Повторный прогон подтвердил идемпотентность на ВСЕХ уровнях разом (локальная SQLite: 0 new; Postgres: те же 349/249/6 после второго прогона) — не только на уровне коннекторов, как раньше
- [x] `web/public/app.js` — серверная пагинация, кнопка «Load more». Решение, не зафиксированное в черновике спека: откуда берутся значения фильтров tier/org без полного клиентского датасета — отдельный одноразовый небаластный запрос (`size=2000`) только для заполнения виджетов, не для рендера карточек; переиспользует ту же пагинированную ручку `/api/postings`, без нового эндпойнта
- [ ] `_blob.py`, `blob_sync.py`, `_logic.py`, их тесты, Blob env vars — удалены
- [ ] Живая проверка на проде: фильтр/пагинация/refresh/статус-запись/полнотекстовый поиск (ранжирование, стемминг) — с замером фактической задержки (curl+TTFB)
- [ ] `docs/backlog/BACKLOG.md`, `CLAUDE.md`, `docs/user_guides/cli_reference.md` обновлены

## Открытые вопросы

- ~~Удалять ли старый Blob-стор (`jobs.db`) сразу...~~ **Решено куратором перед стартом `/feature-workflow` (2026-08-04): оставить непривязанным как путь отката.** Код/env-переменные удаляются в рамках коммита 10, сам Blob-стор в дашборде Vercel остаётся нетронутым — ручное удаление куратором позже, отдельным, более поздним решением.
- Нужен ли Streamlit (`app/app.py`) в будущем перевод на тот же Postgres ради консистентности с веб-GUI, или он остаётся на локальном `data/jobs.db` бессрочно? Не блокирует этот спек.

## Вне скоупа

- UI-поверхности для `organizations`/`searches` в веб-GUI — только схема и синхронизация в этом спеке.
- `postings.search_id` / трассировка вакансии до конкретного search-спека — потребовало бы менять инвариантную логику `store.py` (см. rationale).
- Изменение `store.py`'s upsert/reconciliation-логики в любом виде.
- Очистка/удаление данных в Neon-проекте «Scopus Search» — отдельная, не связанная с этим спеком задача.
- Изменения в `app/app.py` (Streamlit) и его источнике данных.
- Конвертация географической/tier-классификации query-семейства (сейчас — логика коннектора) в БД-таблицу — не запрошено, не измерено, что там вообще есть что нормализовывать.
