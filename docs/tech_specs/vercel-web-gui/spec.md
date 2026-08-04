# Спек: постоянный веб-GUI на Vercel вместо локального Streamlit

Статус: черновик v2 · 2026-08-04 — открытые вопросы v1 закрыты, плацдарм на Vercel создан живьём
Происхождение: прямой запрос куратора — локальный `streamlit run app.py` ресурсоёмок и неудобен для постоянного доступа; куратор просил проверить второй независимый Vercel-проект на бесплатном (Hobby) аккаунте.

## 0. Что и зачем

Заменить локальный Streamlit-просмотрщик (`app.py`, свой `.venv`, запуск руками) на постоянно доступный веб-GUI на Vercel — втором независимом проекте в том же Hobby-аккаунте `helgdemidovs-projects`, где уже живёт `scopus-search-code`. Живая проверка через MCP подтвердила: лимита на число проектов на Hobby нет, второй проект технически свободен.

Streamlit не деплоится на serverless как есть (держит постоянный процесс/WebSocket), поэтому GUI переписывается под Vercel Functions (Python, живьём подтверждена поддержка через `search_vercel_documentation`) + статический фронтенд, без Node/React-тулчейна — сохраняем all-Python стек репозитория.

Граница скоупа: только хостинг/архитектура текущего GUI (карточки, фильтры, статус, тема). LLM-триаж релевантности (`triage-and-autonomy/spec.md`) и сам сбор данных (`run.py`-коннекторы) не трогаются.

## 1. Где живут данные — Vercel Blob как единственный источник истины

`data/jobs.db` (1.6 МБ, 310 строк, 219 организаций — замерено `.venv/bin/python` на боевой БД) полностью умещается в бесплатный лимит **Vercel Blob: 1 ГБ хранилища/мес на Hobby** (живая проверка, август 2026). Это меняет расклад по сравнению с исходным вопросом «какую облачную БД поднимать»:

- **Neon** («Scopus Search», ~300 МБ мусорных данных Scopus, куратор готов удалить) и **Supabase** (2 активных проекта под Scopus — `Scopus Search Project` + `scopus-staging`) — оба Postgres. Мимо: пришлось бы переписывать SQL-диалект `store.py` (`AUTOINCREMENT`→`SERIAL` и т.п.) ради БД на 300 строк — оверинжиниринг.
- **Railway** ($5/мес Hobby, уже несёт Scopus) — технически можно завести второй проект на том же аккаунте (подтверждено: один аккаунт держит много проектов, подписка и usage-биллинг общие на аккаунт), но это либо постоянно работающий сервис, либо ещё один расход из того же $5-пула ради файла на 1.6 МБ.
- **Vercel Blob** — 0 доп. аккаунтов, 0 доп. оплаты, тот же Hobby-аккаунт, который и так заводится под сам GUI. Выбран.

`data/jobs.db` (та же SQLite-схема, `store.py` не меняется) хранится как единственный blob по стабильному пути `jobs.db` (`allowOverwrite: true`, `addRandomSuffix: false` — подтверждено документацией; без этого перезапись создавала бы новый URL на каждый sync). Vercel API-функции скачивают его в `/tmp` при каждом вызове (1.6 МБ — доли секунды) и открывают `sqlite3.connect()` как обычно.

## 2. Локальный пайплайн (`run.py`) — минимальные изменения

`scripts/blob_sync.py` (новый, ~30 строк): `download(dest: Path)` / `upload(src: Path)`, оборачивающие CLI-команды `vercel blob get`/`vercel blob put` через `subprocess` (флаги `--pathname jobs.db --access private --allow-overwrite`, токен из `BLOB_READ_WRITE_TOKEN` в `.env`). CLI выбран сознательно: сырой HTTP PUT-контракт Blob API не задокументирован публично (проверено — документация отдаёт только SDK/CLI-обёртки), а CLI и так нужен локально для деплоя (§3) — не новая зависимость, а переиспользование уже нужного инструмента.

Точка врезки — только `if __name__ == "__main__":` в `run.py`, `main()` не трогается (сохраняет герметичность `test_run.py`, который вызывает `main()` напрямую):

```
blob_sync.download(DB_PATH)   # подтягиваем состояние, включая статусы из веб-GUI
sys.exit(main(run_linkedin=args.linkedin))
blob_sync.upload(DB_PATH)     # публикуем результат прогона
```

Существующая реконсиляция уже не трогает не-`new` статусы (`store.py:118` — `WHERE status='new'`), поэтому статус, проставленный через веб-GUI днём, переживёт полуночный `run.py` без дополнительной защиты.

## 3. Vercel-проект: `web/`

Новая директория `web/` в этом же репозитории (Root Directory в Vercel), деплой **вручную** через `vercel deploy --prod`. С 2026-08-04 у репозитория есть приватный GitHub-remote (`github.com/HelgDemidov/ai-policy-jobs`) — Git-триггерный автодеплой теперь технически подключаем, но сознательно не подключаем: свежие данные и так приходят через Blob (§1), не через редеплой, а `web/` ещё не реализован. Пересмотреть при реализации, если ручной `vercel deploy --prod` станет неудобен — включается один раз в Vercel Dashboard (Settings → Git), спека не потребует.

**Проект уже создан (2026-08-04), живьём проверено:** `ai-policy-jobs` (`prj_K2BCJPrgtMsmhtXhNTmI2cGYbZXo`, teamId `team_cWecMchTU2BD1cNpKzcAH6Od`; название `job-search-gui` до переименования 2026-08-04 в Dashboard — для симметрии с GitHub-репозиторием, id и весь остальной конфиг проекта переименование не затрагивает), заведён через MCP-инструмент `deploy_to_vercel` (без локального CLI/логина) заглушкой — `public/index.html` + `api/health.py`. Прод-URL `https://ai-policy-jobs.vercel.app`, билд `READY`, `lambdaRuntimeStats: {"python":1}` подтверждает живой Python-рантайм, `/api/health` отдаёт `{"status":"ok","runtime":"python"}` (проверено `WebFetch`). При реализации кода из этого спека: `cd web && vercel link` подхватит этот же существующий проект по имени — новый заводить не нужно.

- `web/api/postings.py` — GET: скачивает blob, `SELECT * FROM postings`, фильтрация (tier/org/remote/hide-closed/поиск) — логика 1:1 с текущим `app.py:383-391`. Импортирует `scripts/store.py` (тот же `sys.path`-приём, что уже в `app.py:15-16`).
- `web/api/status.py` — POST: скачивает blob, `UPDATE postings SET status=...` (та же query, что `app.py:306-313`), заливает обратно с `ifMatch` на etag скачанной версии (защита от гонки с параллельным `run.py`-sync — на масштабе одного куратора вероятность стремится к нулю, но проверка бесплатна).
- `web/public/` — статический фронтенд, ванильные HTML/CSS/JS, без сборки: карточная сетка (3 в ряд), сайдбар-фильтры, tier-чипы, `<select>` статуса → `fetch POST /api/status`, переключатель темы через `prefers-color-scheme` + `localStorage` (проще текущего iframe-хака `app.py:130-291` — тот обходил отсутствие у Streamlit публичного API смены темы; здесь этого ограничения нет).

## 4. Доступ — shared-secret gate

Vercel Password Protection для production-деплоя требует платного плана (живая проверка документации: «Password protection requires an eligible plan» — на Hobby недоступна). Оставлять GUI публично читаемым нельзя: карточки несут emigrant/citizenship-нарратив куратора и адресный список организаций по чувствительным гео (`docs/BACKLOG.md`). Решение: минимальный собственный гейт — `SITE_PASSWORD` (env var) проверяется в каждой `api/*.py`-функции по cookie, выставляемой простой login-формой в `web/public/`. Не новый сервис, ~20 строк.

**Где хранить `SITE_PASSWORD` (закрыто):** только в Vercel Dashboard проекта `ai-policy-jobs` → Settings → Environment Variables — https://vercel.com/helgdemidovs-projects/ai-policy-jobs/settings/environment-variables (значение вбивается прямо в веб-форму, не через чат). НЕ локальный `.env` репозитория — его читают только локальные Python-скрипты (`adzuna.py`, будущий `blob_sync.py`), до Vercel-функций он не доезжает. НЕ GitHub Secrets — репозиторий с 2026-08-04 зеркалится на приватный `github.com/HelgDemidov/ai-policy-jobs`, но GitHub Actions/CI там не заводили и не планируем (деплой ручной через `vercel deploy --prod`); секреты Actions существуют только внутри workflow, которого нет.

## Design rationale / отвергнутые альтернативы

- **Vercel Global Config (бывш. Edge Config)** — отвергнуто: живьём проверенный лимит **1 МБ на стор на Hobby** ниже текущего размера `jobs.db` (1.6 МБ) уже сейчас; к тому же это read-optimized KV для конфигов/фича-флагов с платной записью ($1/100 writes) — не файловое хранилище и не годится под частые точечные UPDATE статуса.
- **Postgres (Neon/Supabase)** — отвергнуто: 310 строк не требуют реляционной БД; Supabase-аккаунт уже занят двумя Scopus-проектами, Neon — другой SQL-диалект без функциональной выгоды.
- **Ещё один Railway-проект** — отвергнуто: постоянный сервис ради 1.6 МБ файла, тянет тот же $5-пул, что и Scopus.
- **Next.js/React** — отвергнуто: Vercel Python Functions подтверждены живьём, весь остальной репозиторий — Python; статический HTML/CSS/JS без сборки ложится в Vercel's zero-config "Other"-пресет.
- **Коммит снапшота БД в git + автодеплой** — отвергнуто: даже при наличии GitHub-remote (с 2026-08-04) это привязало бы каждый прогон `run.py` к редеплою; Blob разводит «новые данные» и «новый код» по разным механизмам независимо от наличия remote.
- **Сырой HTTP к Blob API вместо CLI** — отвергнуто: точный REST-контракт `PUT` не задокументирован публично (проверено), CLI даёт тот же результат специфицированным способом.
- **Оставить GUI без пароля** — отвергнуто: контент включает чувствительный нарратив и адресный список организаций; Vercel Password Protection недоступна на Hobby (проверено), поэтому добавлен минимальный app-level гейт вместо отказа от защиты.

## Тестовое покрытие

Герметично — `tests/` не трогает боевую `data/jobs.db`, сеть в тестах недопустима.

- `scripts/blob_sync.py`: монкипатч `subprocess.run` — download/upload дёргают правильные CLI-флаги, ошибка CLI не глушится молча.
- `web/api/`: логика вынесена в тестируемые функции (`web/api/_logic.py` — чистые `list_postings(conn, filters)` / `set_status(conn, ...)`), Vercel-хендлеры — тонкие обёртки; тесты дёргают логику напрямую с `tmp_path`-БД, без поднятия dev-сервера.
- `tests/test_store.py` / `test_run.py` — без изменений, схема и upsert-логика не тронуты.
- Гейт (§4): happy path с верным паролем + отказ без пароля/с неверным.

## План коммитов

1. `feat(blob): scripts/blob_sync.py — download/upload jobs.db через Vercel CLI, врезка в run.py __main__` + тесты
2. `feat(web): web/api/ — postings/status Python-функции поверх store.py` + тесты логики
3. `feat(web): web/public/ — статическая карточная сетка, фильтры, тема (паритет с app.py)`
4. `feat(web): shared-secret гейт доступа` + тесты
5. `docs: BACKLOG.md/CLAUDE.md/cli_reference.md — Vercel-проект, blob-токен, команда деплоя`

`app.py`/Streamlit в план не входит: куратор решил (2026-08-04) оставить его как есть до приёмки и обкатки нового GUI, ретайр — отдельный будущий коммит вне этого спека.

## Чек-лист реализации

- [ ] `scripts/blob_sync.py` + тесты (монкипатч `subprocess`)
- [ ] врезка sync в `run.py` `__main__`
- [ ] `web/api/_logic.py` (`list_postings`, `set_status`) + тесты
- [ ] `web/api/postings.py`, `web/api/status.py` (тонкие Vercel-хендлеры)
- [ ] `web/public/index.html` + `style.css` + `app.js` — карточки/фильтры/тема/статус
- [x] Vercel-проект `ai-policy-jobs` (переименован из `job-search-gui` 2026-08-04) создан и живьём проверен (2026-08-04, `deploy_to_vercel` MCP, заглушка `public/index.html`+`api/health.py`, `READY`, `/api/health` отвечает)
- [x] Vercel Blob store создан и подключён к проекту (2026-08-04, Dashboard → Storage, `job-search-gui-blob`, `store_tzXWWO2Y42v4IL6X`, регион `fra1`, Private, с read-write токеном)
- [x] `SITE_PASSWORD` вбит в Settings → Environment Variables проекта `ai-policy-jobs`
- [x] `BLOB_READ_WRITE_TOKEN` в локальном `.env`, живьём проверен полным циклом `vercel blob put`/`list`/`del` (2026-08-04) — рабочий, тестовый файл подчищен, стор пуст

**Живая находка:** ни `vercel env pull`, ни `vercel env run` не отдают реальное значение `BLOB_READ_WRITE_TOKEN` — Vercel-переменные с флагом «Sensitive» отдаются как плейсхолдер `"[SENSITIVE]"` через оба канала, не только в Dashboard. Единственный способ получить значение — через саму панель управления Blob-подключением («Manage Blob Connection»), не через общий Environment Variables UI/CLI-pull.
- [ ] shared-secret гейт + тесты
- [ ] `cd web && vercel link` (подхватывает существующий `ai-policy-jobs`, новый проект не создавать) + `vercel deploy --prod` — реальный код поверх заглушки
- [ ] живой смок: открыть URL, проверить фильтры/статус-запись/тему в браузере
- [ ] `docs/BACKLOG.md`, `CLAUDE.md`, `docs/user_guides/cli_reference.md` обновлены

## Открытые вопросы

Нет — все вопросы v1 закрыты куратором 2026-08-04 (Streamlit остаётся до приёмки нового GUI; `SITE_PASSWORD` — только в Vercel Dashboard; Vercel-проект создан и назван).

## Вне скоупа

- LLM-триаж релевантности (`triage-and-autonomy/spec.md`) — отдельный спек.
- Перенос самого сбора данных (`run.py`-коннекторы) на Vercel — коллекция остаётся локальной под тем же systemd-таймером; Vercel получает только готовый blob.
- Git-triggered автодеплой на Vercel — GitHub-remote с 2026-08-04 это уже позволяет технически, но в этом заходе сознательно не подключаем (§3); деплой остаётся ручным.
- Многопользовательский доступ/роли — один shared-secret на одного куратора достаточно.
- Очистка мусорных данных из Neon-проекта Scopus — отдельное действие вне этого GUI-спека (Neon в этом спеке не используется вообще).
