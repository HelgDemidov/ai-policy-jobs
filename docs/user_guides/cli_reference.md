# Job Search — CLI reference

## Подключение (новая сессия Claude CLI)

```bash
cd ~/Рабочий\ стол/job-search && claude
```
Полный путь: `/home/fastcentrifuge/Рабочий стол/job-search`. Отдельный, независимый git-репозиторий — НЕ worktree G2AI, входить туда не нужно. Свежая сессия сразу подхватит `CLAUDE.md` этой папки.

**Streamlit UI:** http://localhost:8501 (после запуска ниже; порт по умолчанию, если свободен). Никаких других сетевых адресов/серверов в проекте нет — SQLite - локальный файл, ATS/агрегаторы вызываются исходящими HTTP-запросами, входящих портов не открывают. Ключи Adzuna — `.env` в корне (не в git).

## Запуск

```bash
.venv/bin/python scripts/run.py            # синхронизация: все ATS + все search-источники, КРОМЕ LinkedIn
.venv/bin/python scripts/run.py --linkedin  # то же + LinkedIn (рейт-лимит/ToS-риск — запускать осознанно, не в cron)
.venv/bin/streamlit run app.py              # UI на localhost:8501
.venv/bin/pytest                            # тесты (77+, герметично)
```

⚠ Не bare `python3` — `python-jobspy`/`pandas` есть только в `.venv`.

## Прямой доступ к БД

```bash
sqlite3 data/jobs.db "SELECT org, title, status FROM postings WHERE status='new'"
```
Статусы: `new` → `reviewed`/`applied`/`rejected` (вручную) / `likely_closed` (авто, только если ещё `new`).

## Конфиги (правятся вручную, без кода)

- `orgs.yaml` — организации для ATS-коннекторов: `{org, tier, ats: lever|greenhouse|personio, slug}`.
- `searches.yaml` — поисковые запросы: `{id, source: himalayas|adzuna|jobspy_linkedin|jobspy_indeed, query/phrase, country/location, manual: true (опц.)}`.

Детали и живые уроки по каждому источнику — `docs/BACKLOG.md`, `docs/job-aggregator-landscape.md`.
