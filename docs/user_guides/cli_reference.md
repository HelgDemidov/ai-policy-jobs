# Job Search — CLI reference

## Технический раздел

### Подключение (новая сессия Claude CLI)

```bash
cd ~/Рабочий\ стол/job-search && claude
```
Полный путь: `/home/fastcentrifuge/Рабочий стол/job-search`. Отдельный, независимый git-репозиторий; свежая сессия сразу подхватит `CLAUDE.md` этой папки.

**Streamlit UI:** http://localhost:8501 (после запуска ниже; порт по умолчанию, если свободен). Никаких других сетевых адресов/серверов в проекте нет — SQLite - локальный файл, ATS/агрегаторы вызываются исходящими HTTP-запросами, входящих портов не открывают. Ключи Adzuna — `.env` в корне (не в git).

## Запуск

```bash
.venv/bin/python scripts/run.py            # синхронизация: все ATS + все search-источники, включая LinkedIn
.venv/bin/python scripts/run.py --linkedin  # то же (флаг включает спеки с manual: true — сейчас таких нет)
.venv/bin/streamlit run app.py              # UI на localhost:8501
.venv/bin/pytest                            # тесты (77+, герметично)
```

⚠ Не bare `python3` — `python-jobspy`/`pandas` есть только в `.venv`.

**Живой урок: активационный email-prompt Streamlit при первом запуске.** Перед стартом любого `streamlit run` пакет безусловно проверяет наличие `~/.streamlit/credentials.toml` (`runtime/credentials.py`, без исключений для headless/non-tty окружений); если файла нет — печатает приветствие «Welcome to Streamlit!» и ждёт email через интерактивный `click.prompt`. В обычном терминале достаточно нажать Enter (пустой email допустим). Но при запуске из неинтерактивной оболочки без stdin (например, фоновым процессом) `click.prompt` получает EOF и падает с ошибкой вместо вопроса. Обход — заранее создать файл с пустым email, тогда проверка проходит молча и вопрос больше не появляется:
```bash
mkdir -p ~/.streamlit && printf '[general]\nemail = ""\n' > ~/.streamlit/credentials.toml
```
Уже сделано на этой машине 2026-07-25 — при живом воспроизведении обнаружилось, что файл до этого момента не существовал, хотя приложение уже запускалось и проверялось ранее (см. `docs/BACKLOG.md`, раздел про интерфейс просмотра вакансий) — вероятно, тот прогон либо прошёл через тот же креш иначе, либо файл был впоследствии удалён (например, командой `streamlit reset`). Актуально повторить этот шаг на новой машине или после `streamlit reset`.

## Прямой доступ к БД

```bash
sqlite3 data/jobs.db "SELECT org, title, status FROM postings WHERE status='new'"
```
Статусы: `new` → `reviewed`/`applied`/`rejected` (вручную) / `likely_closed` (авто, только если ещё `new`).

## Конфиги (правятся вручную, без кода)

- `orgs.yaml` — организации для ATS-коннекторов: `{org, tier, ats: lever|greenhouse|personio, slug}`.
- `searches.yaml` — поисковые запросы: `{id, source: himalayas|adzuna|jobspy_linkedin|jobspy_indeed, query/phrase, country/location, manual: true (опц.)}`.

Детали и живые уроки по каждому источнику — `docs/BACKLOG.md`, `docs/job-aggregator-landscape.md`.
