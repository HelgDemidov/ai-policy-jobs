# Спек: query-centric коннекторы (Himalayas + Adzuna + JobSpy)

Статус: черновик v1 · 2026-07-25
Происхождение: `docs/BACKLOG.md` «Следующие шаги» п.1; обоснование выбора источников — `docs/job-aggregator-landscape.md` (живое тестирование 2026-07-25).

## 0. Что и зачем

Сейчас `scripts/run.py` умеет только org-centric коннекторы (`fetch(slug)` по известной организации из `orgs.yaml`). Направление 1 показало (см. `docs/ats-aggregator-sweep.md`): 1 хит из ~24 организаций — рост охвата этим путём исчерпан. Добавляем вторую семью коннекторов — query-centric (`fetch(spec)` по поисковому запросу): организации и вакансии приходят из самих данных. Источники отобраны живым тестом: Himalayas (Tier A), Adzuna (Tier B, мультистрановость), JobSpy→LinkedIn (лучшая релевантность, только по флагу — решение куратора), JobSpy→Indeed (второстепенный). Не enterprise: без прокси, без ретраев с backoff, без счётчиков квот — простая машинка.

Решения куратора (2026-07-25): тир — авто-эвристика (см. §4). LinkedIn изначально был выведен из дефолтного прогона под флаг `--linkedin`; в тот же день решение развёрнуто — источник вернулся в дефолтный прогон (обоснование и замеры — `docs/BACKLOG.md`).

## 1. Конфиг поисков: `searches.yaml`

Отдельный файл рядом с `orgs.yaml` (другая грамматика записи, не смешивать):

```yaml
# id — стабильный идентификатор поиска (для логов/сводки), не меняется после заведения.
# manual: true — источник запускается только с флагом `run.py --linkedin` (сейчас это только LinkedIn).
- id: himalayas-policy
  source: himalayas
  query: policy
- id: himalayas-ai-governance
  source: himalayas
  query: AI governance
- id: adzuna-thinktank-gb
  source: adzuna
  phrase: think tank        # what_phrase — точная фраза; широкий what НЕ используем (шум, см. landscape-док)
  country: gb
- id: adzuna-thinktank-be
  source: adzuna
  phrase: think tank
  country: be
- id: jobspy-linkedin-uk
  source: jobspy_linkedin
  query: AI policy analyst
  location: United Kingdom
  manual: true
- id: jobspy-indeed-uk
  source: jobspy_indeed
  query: '"AI policy" OR "AI governance"'   # Indeed требует кавычек для фраз (живой урок)
  location: United Kingdom
  country_indeed: UK
```

Сид-запросы — ровно те, что проверены живьём; куратор дополняет файл руками без правки кода.

## 2. Коннекторы (3 новых модуля в `scripts/`)

Контракт: `fetch(spec: dict) -> list[dict]` — тот же posting-dict, что у ATS-коннекторов, плюс обязательное поле `org` (из данных, не из конфига). Чистые функции, в store не пишут (паттерн `discovery/` из G2AI). `ats_id` — нативный стабильный id источника; фолбэк — `sha256(url)[:16]`.

- **`scripts/himalayas.py`** — `GET https://himalayas.app/jobs/api/search?q={query}&page={n}`, страницы 1–3 (по 20 записей), пауза 1 c между страницами. Без ключа. `description` ← `excerpt` (краткий — приемлемо для v1). ⚠ Точные имена полей id/url/даты в ответе сверить с живым ответом при реализации (в тесте 2026-07-25 печатались только title/companyName; НЕ выдумывать) — эндпоинт именно `/jobs/api/search` с параметром `q`, НЕ `/jobs/api` с `keyword` (живой урок: тот молча игнорирует фильтр и отдаёт всё).
- **`scripts/adzuna.py`** — `GET https://api.adzuna.com/v1/api/jobs/{country}/search/1?what_phrase={phrase}&results_per_page=50` + `app_id`/`app_key`. Ключи — из `.env` в корне (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`, файл уже существует, gitignored): ~8-строчный локальный парсер KEY=VALUE с приоритетом реальных env-переменных — по образцу `core/env.py` из G2AI, без зависимости python-dotenv. Только HTTPS (http даёт 301 — живой урок). `org` ← `company.display_name`, `posted_at` ← `created[:10]`, url ← `redirect_url` (сверить при реализации). Квота 1000 зап./мес: дефолтный набор (2 запроса/прогон) даже при ежедневном запуске ≈ 60/мес — счётчик не нужен (YAGNI).
- **`scripts/jobspy_search.py`** — обёртка над `jobspy.scrape_jobs` (уже в `.venv`, python-jobspy 1.1.82). Два значения `source`: `jobspy_linkedin`, `jobspy_indeed` — раздельный провенанс в БД. `results_wanted=20` на запрос. Для LinkedIn `linkedin_fetch_description=False` по умолчанию (меньше запросов → меньше риск рейт-лимита; полное описание — будущий опциональный `fetch_description: true` в spec'е поиска). DataFrame → posting-dict'ы; NaN → None.

## 3. Store: `scripts/store.py`

1. **Новая колонка `dedup_key`** = нормализованный `f"{org}|{title}"` (lowercase, схлопнутые пробелы, без пунктуации). Миграция — идемпотентный `_ensure_column(conn)` по образцу `_ensure_facets_sensitivity` из G2AI (ALTER TABLE при отсутствии колонки; `jobs.db` с 30 строками уже существует, DROP недопустим). Заполняется при любой вставке (обе семьи коннекторов).
2. **Новая функция `upsert_search_postings(conn, source, postings)`**. Ключевое отличие от `upsert_postings`: **НЕТ реконсиляции в `likely_closed`** — отсутствие вакансии в оконной/ранжированной поисковой выдаче ≠ закрытие (в отличие от полного листинга ATS, где это честный сигнал). Семантика вставки:
   - `(source, ats_id)` уже есть → UPDATE изменяемых полей + `last_seen` (как в ATS-ветке);
   - иначе `dedup_key` совпал с ЛЮБОЙ существующей строкой (другой источник или другой ats_id того же) → НЕ вставлять, у существующей строки обновить `last_seen` («touch»). Это одновременно кросс-источниковый дедуп (LinkedIn-находка не дублирует Lever-строку FLI) и защита от нестабильных ats_id;
   - иначе INSERT со статусом `new` и тиром из эвристики (§4).
   ATS-семья (`upsert_postings`) дедуп-проверку НЕ делает — прямой фид организации всегда ground truth.
3. **Новая функция `expire_stale_search_postings(conn, sources, max_age_days=45)`** — заменитель реконсиляции для поисковой семьи: `status='new'` AND `last_seen` старше порога → `likely_closed`. Ручные статусы (`applied`/`rejected`/`reviewed`) не трогаются — тот же инвариант, что в ATS-ветке.

## 4. Тир-эвристика (решение куратора: авто)

Детерминированно по источнику, без парсинга free-text локаций (они ненадёжны — «London & San Francisco»):
- `himalayas` → `A` (remote-only борд по определению);
- `adzuna` → из `country` спека: `gb/be/de/fr/nl/ch/at/it/es` → `B`; `us` → `C`; иначе NULL;
- `jobspy_*` → `is_remote=True` → `A`; иначе по `location` спека (не вакансии): страна Зап. Европы → `B`, США → `C`, иначе NULL.
Реализация — `derive_tier(source, spec, posting)` в `scripts/query_common.py` (либо внутри `jobspy_search.py`, если общего кода окажется < 20 строк — решить при реализации). Ошибки эвристики видны глазами в Streamlit-карточках и не фатальны.

## 5. Оркестрация: `scripts/run.py`

После существующего цикла по `orgs.yaml` — второй цикл по `searches.yaml`: реестр `SEARCH_CONNECTORS = {"himalayas": ..., "adzuna": ..., "jobspy_linkedin": ..., "jobspy_indeed": ...}`, изоляция отказа per-спек (тот же try/except-паттерн), сводка per-id. Затем один вызов `expire_stale_search_postings`. CLI: `argparse` с единственным флагом `--linkedin` — без него спеки с `manual: true` пропускаются (печатается «skipped (manual)»). Повторный прогон идемпотентен: те же находки → 0 новых, обновлённые `last_seen`.

`app.py` изменений не требует (новые source/org подхватываются сами). Известное следствие: мультиселект Organization разрастётся с ростом числа найденных организаций — приемлемо для v1, зафиксировано как будущее улучшение.

## Design rationale / отвергнутые альтернативы

- **Единый `fetch(search_term)` на все источники** — отвергнуто: живой тест показал, что рабочие запросы разные («think tank» на Adzuna vs «policy» на Himalayas vs «AI policy analyst» на LinkedIn); конфиг per-source обязателен.
- **Реконсиляция `likely_closed` для поисковой семьи как у ATS** — отвергнуто как ложный сигнал: страница 1 поисковой выдачи — окно, не полный листинг. Замена — age-based expiry (45 дней, параметр).
- **Дедуп с location в ключе** — отвергнуто: один и тот же пост часто различается только формой локации (живой пример Ethos: дубли с/без локации); риск схлопнуть две честные вакансии одного title в разных офисах на нашем масштабе принят и задокументирован.
- **Фузи-мэтчинг/семантический дедуп** (industry best practice по promptcloud/cavuno) — отвергнут как enterprise-оверкилл; точный нормализованный ключ достаточен для десятков строк.
- **python-dotenv / счётчик квоты Adzuna / прокси для LinkedIn** — YAGNI на нашем масштабе; G2AI-прецедент (`core/env.py` — свой мини-парсер).
- **Отдельный `--manual`-флаг вместо `--linkedin`** — выбран `--linkedin` как понятный куратору (единственный manual-источник сейчас); грамматика `manual: true` в конфиге уже общая, переименование флага при появлении второго manual-источника тривиально.
- **Продолжать org-centric ATS-охоту вместо query-centric** — закрыто данными направления 1 (1/24).

## Тестовое покрытие

Герметичность обязательна (autouse-guard'ы уже в `tests/conftest.py`; боевая `data/jobs.db` не затрагивается — инвариант репо). Coverage-гейта в репо нет; критерий — зелёный `.venv/bin/pytest` и покрытие каждой новой ветки логики:

- Коммит 1 (store): `_ensure_column` на существующей БД без колонки (миграция) и повторно (идемпотентность); `upsert_search_postings` — вставка/обновление по `(source, ats_id)`; dedup-hit по `dedup_key` из другого источника → skip + touch `last_seen`; отсутствие реконсиляции (пропавшая из выдачи строка остаётся `new`); `expire_stale_search_postings` — старая `last_seen` → `likely_closed`, ручной статус не тронут, ATS-источники не затронуты.
- Коммит 2 (himalayas+adzuna): `requests_mock` на живые формы ответов (зафиксировать реальные JSON-фикстуры при реализации); парсинг полей, пустая выдача, отсутствующие опциональные поля; `.env`-парсер: файл есть/нет, приоритет os.environ.
- Коммит 3 (jobspy): `monkeypatch` на `jobspy.scrape_jobs` (фейковый DataFrame — сеть в тестах недопустима); маппинг DataFrame→dict, NaN→None, разделение source по сайту.
- Коммит 4 (run+тир): цикл по `searches.yaml` с изоляцией отказа; `--linkedin` — включение/пропуск `manual`-спеков; `derive_tier` — таблица случаев (himalayas→A, adzuna gb→B, us→C, jobspy remote→A, неизвестное→None); идемпотентность повторного `main()`.

## План коммитов/PR

(План — на момент, когда куратор решит начать коммитить; сейчас репо без коммитов.)

1. `feat(store): dedup_key + upsert_search_postings + expire_stale — поисковая семья хранения`
2. `feat(connectors): himalayas + adzuna коннекторы (+ .env-парсер)`
3. `feat(connectors): jobspy-обёртка (linkedin/indeed)`
4. `feat(run): searches.yaml + оркестрация поисков + --linkedin + тир-эвристика`

## Чек-лист реализации

- [ ] store: `_ensure_column`, `upsert_search_postings`, `expire_stale_search_postings` + тесты
- [ ] `scripts/himalayas.py` + живая сверка имён полей + фикстуры + тесты
- [ ] `scripts/adzuna.py` + `.env`-парсер + живая сверка `redirect_url` + тесты
- [ ] `scripts/jobspy_search.py` + тесты (monkeypatch)
- [ ] `searches.yaml` (сид из проверенных запросов) + `run.py` (второй цикл, `--linkedin`, expiry) + `query_common.derive_tier` + тесты
- [ ] живой смок: `python3 scripts/run.py` (без `--linkedin`), затем разово с `--linkedin`; проверка карточек в Streamlit
- [ ] обновить `docs/BACKLOG.md` (статус п.1) и `orgs.yaml`-комментарий (примечание о второй семье)

## Вне скоупа

- LLM-стадия анализа/отклика (п.3 бэклога — отдельный спек).
- HTML-скрейп кастомных карьерных страниц шортлиста (п.2 бэклога).
- Уведомления (Telegram/email), cron-автозапуск — после обкатки ручного режима.
- UI-правка тира из Streamlit-карточки; сворачивание org-мультиселекта.
- Прокси-ротация, счётчик квоты Adzuna, фузи-дедуп.
