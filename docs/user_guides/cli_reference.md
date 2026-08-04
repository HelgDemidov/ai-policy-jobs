# Job Search — CLI reference

## Технический раздел

### Подключение (новая сессия Claude CLI)

```bash
cd ~/Рабочий\ стол/Projects/Dev/job-search && claude
```
Полный путь: `/home/fastcentrifuge/Рабочий стол/Projects/Dev/job-search`. Отдельный, независимый git-репозиторий; свежая сессия сразу подхватит `CLAUDE.md` этой папки.

**Streamlit UI:** http://localhost:8501 (после запуска ниже; порт по умолчанию, если свободен). **Веб-GUI на Vercel:** https://ai-policy-jobs.vercel.app (постоянно доступен, пароль — `SITE_PASSWORD`, см. ниже раздел «Веб-GUI»). ATS/агрегаторы вызываются исходящими HTTP-запросами, входящих портов локальный инструмент не открывает. Ключи Adzuna — `.env` в корне (не в git).

## Окружение (venv, зависимости)

`.venv` создаётся через `uv` (уже стоит в системе, `~/.local/bin/uv`), не bare `python3 -m venv` — живой урок из `postings-schema-hardening`: venv, пересозданный вручную, тащит зашитые абсолютные пути от переезда репозитория, `uv venv` этого не делает.

```bash
uv venv                                                     # создать/пересоздать .venv
uv pip install -r requirements.txt -r requirements-dev.txt  # Python-зависимости + ruff/mypy/pytest
npm install                                                  # eslint (для web/public/**/*.js)
```

## Запуск

```bash
.venv/bin/python scripts/run.py            # синхронизация: все ATS + все search-источники, включая LinkedIn
.venv/bin/python scripts/run.py --linkedin  # то же (флаг включает спеки с manual: true — сейчас таких нет)
.venv/bin/streamlit run app/app.py          # UI на localhost:8501
.venv/bin/pytest                            # тесты (104+, герметично)
.venv/bin/ruff check .                      # линт Python (чисто)
.venv/bin/mypy scripts app web              # типы Python (чисто)
npx eslint .                                # линт JS (web/public/**/*.js)
```

⚠ Не bare `python3` — `python-jobspy`/`pandas` есть только в `.venv`.

**Живой урок: активационный email-prompt Streamlit при первом запуске.** Перед стартом любого `streamlit run` пакет безусловно проверяет наличие `~/.streamlit/credentials.toml` (`runtime/credentials.py`, без исключений для headless/non-tty окружений); если файла нет — печатает приветствие «Welcome to Streamlit!» и ждёт email через интерактивный `click.prompt`. В обычном терминале достаточно нажать Enter (пустой email допустим). Но при запуске из неинтерактивной оболочки без stdin (например, фоновым процессом) `click.prompt` получает EOF и падает с ошибкой вместо вопроса. Обход — заранее создать файл с пустым email, тогда проверка проходит молча и вопрос больше не появляется:
```bash
mkdir -p ~/.streamlit && printf '[general]\nemail = ""\n' > ~/.streamlit/credentials.toml
```
Уже сделано на этой машине 2026-07-25 — при живом воспроизведении обнаружилось, что файл до этого момента не существовал, хотя приложение уже запускалось и проверялось ранее (см. `docs/backlog/BACKLOG.md`, раздел про интерфейс просмотра вакансий) — вероятно, тот прогон либо прошёл через тот же креш иначе, либо файл был впоследствии удалён (например, командой `streamlit reset`). Актуально повторить этот шаг на новой машине или после `streamlit reset`.

## Автозапуск (systemd user timer, реализовано 2026-07-26)

`scripts/run.py` теперь запускается сам, раз в сутки, без участия куратора. Юниты — в `~/.config/systemd/user/`, **не в репозитории** (абсолютные пути конкретной машины) — при переносе на новую машину создать заново по тексту ниже, поправив пути.

`job-search-run.service`:
```ini
[Unit]
Description=Job Search Tracker — daily sync (scripts/run.py)

[Service]
Type=oneshot
WorkingDirectory=/home/fastcentrifuge/Рабочий стол/Projects/Dev/job-search
ExecStart="/home/fastcentrifuge/Рабочий стол/Projects/Dev/job-search/.venv/bin/python" "/home/fastcentrifuge/Рабочий стол/Projects/Dev/job-search/scripts/run.py"
```

`job-search-run.timer`:
```ini
[Unit]
Description=Daily timer for Job Search Tracker sync (00:00 UTC)

[Timer]
OnCalendar=*-*-* 00:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

**Почему именно так:**
- `ExecStart` — в кавычках на каждый аргумент: путь содержит пробел и кириллицу, без кавычек systemd падает на парсинге командной строки (проверено `systemd-analyze --user verify` на systemd 255). `WorkingDirectory`, наоборот, кавычек не терпит — это не командная строка, а простое присваивание; в кавычках systemd решает, что путь «не абсолютный» (в кавычке первый символ — `"`, не `/`) и юнит не стартует. Обе ошибки живьём пойманы при первом заходе.
- `OnCalendar=... UTC` — явный суффикс обязателен: локальный часовой пояс машины — Europe/Podgorica (UTC+1/+2), без `UTC` таймер бы бил в полночь по Подгорице, а не по Гринвичу. Проверено живьём: после `enable --now` следующий запуск показан как `02:00 CEST` — это и есть `00:00 UTC` летом.
- `Persistent=true` — обязателен именно из-за полуночи: ноутбук куратора вечером обычно выключен/спит, и без этого флага пропущенный ровно на 00:00 UTC запуск не наверстался бы. Раз в сутки машина всё равно включается — Persistent-запуск при следующем входе в сессию закрывает разрыв. `loginctl enable-linger` не нужен по той же причине.
- Без `RandomizedDelaySec` — куратор явно попросил триггер ровно в полночь по Гринвичу; исходный спек предлагал джиттер (вежливость к бесплатным API при глобальном стечении таймеров на 00:00), но это осознанно опущено ради точности момента запуска. Добавить `RandomizedDelaySec=30m` в `[Timer]`, если захочется вернуть.
- Один `ExecStart` (только `run.py`) — LLM-триаж (`scripts/triage.py`) из исходного спека `triage-and-autonomy` не реализован, в автозапуск включать нечего; когда появится, второй `ExecStart=` добавляется той же строкой ниже первого.

**Управление:**
```bash
systemctl --user status job-search-run.timer      # активен ли, когда следующий запуск
systemctl --user list-timers job-search-run.timer # то же компактно
journalctl --user -u job-search-run.service        # логи прошедших прогонов (без отдельного лог-файла/ротации)
systemctl --user start job-search-run.service       # прогнать вручную прямо сейчас, не дожидаясь таймера
systemctl --user disable --now job-search-run.timer # выключить автозапуск совсем
```

Признак сбоя всего прогона — ненулевой exit code `run.py` (реализовано вместе с таймером): если абсолютно все источники за прогон отвалились, `journalctl` покажет `job-search-run.service: Main process exited, code=exited, status=1`; частичный отказ или пустой конфиг по-прежнему завершаются кодом `0` — под таймером иначе нельзя было бы отличить «всё сломалось» от «просто нет свежих вакансий».

## Веб-GUI на Vercel (`docs/tech_specs/vercel-web-gui/spec.md`, хранилище — `docs/tech_specs/web-postgres-migration/spec.md`)

Прод: https://ai-policy-jobs.vercel.app — статический фронтенд (`web/public/`) + Python Vercel Functions (`web/api/`), данные — Neon Postgres (проект `quiet-sea-26110140`, регион `aws-us-west-2` — не идеально, см. спек §2/«Что разошлось с планом»; `DATABASE_URL` в Vercel env + локальном `.env`). Гейт — `SITE_PASSWORD` (cookie), не встроенная Vercel Password Protection (недоступна на Hobby-плане).

```bash
cd web && vercel deploy --prod   # выкатить текущий код web/ в прод (нужен vercel link один раз на новой машине)
vercel logs <url>                # логи функций (Python-трейсбеки, если что-то падает)
vercel curl <url>/api/postings   # прогнать запрос с обходом Vercel Deployment Protection (актуально для superview-URL, прод им не прикрыт)
```

**Миграции схемы (Alembic, репо-корень `alembic/`):**
```bash
DATABASE_URL=<connection string> .venv/bin/alembic upgrade head    # применить миграции к Postgres вручную
DATABASE_URL=<connection string> .venv/bin/alembic check           # сверить схему БД с web/api/_schema.py (дрейф-чек)
```
На практике `alembic upgrade head` вызывается программно из `scripts/postgres_sync.py` при каждом прогоне `run.py` (идемпотентно) — ручной вызов нужен только для отладки/первого разворачивания на новом Neon-проекте.

**Синхронизация данных** — `scripts/postgres_sync.py`, вызывается автоматически из `run.py __main__` (см. «Автозапуск» выше): перед прогоном коннекторов подтягивает `status` из Postgres в локальный SQLite (не теряет правки, сделанные через веб-GUI); после прогона зеркалирует `organizations`/`searches`/`postings` обратно в Postgres одной транзакцией.

**Живая находка: `dict(conn.execute(select(a, b)))` в SQLAlchemy не работает напрямую** — у `CursorResult` есть собственный `.keys()` (имена колонок), из-за чего `dict()` ошибочно трактует результат как уже словарь-подобный. Нужен `.all()` перед `dict()`.

**Живая находка: полнотекстовый поиск (`websearch_to_tsquery`/`ts_rank`) — Postgres-специфика без аналога в SQLite.** `web/api/_repo.py`'s `_build_where` — единственное место в слое доступа к данным, где поведение зависит от диалекта (`engine.dialect.name`); тесты гоняют fallback-ветку (`LIKE`) через SQLite, реальное ранжирование проверяется только живьём против настоящего Neon или в CI-джобе `test-integration`.

**Живая находка: два независимо захардкоженных «достаточно большое число» в разных языках расходятся.** `app.js` запрашивал `size=2000` для списка организаций-фильтров, `postings.py` резал `size` потолком `200` — часть организаций молча пропадала из фильтров. Правильный фикс — не увеличить число, а убрать зависимость от потолка вообще: отдельный эндпойнт `/api/facets` на `SELECT DISTINCT`, не имеющий ограничения по количеству строк в принципе.

## Прямой доступ к БД

```bash
sqlite3 data/jobs.db "SELECT org, title, status FROM postings WHERE status='new'"
```
Статусы: `new` → `reviewed`/`applied`/`rejected` (вручную) / `likely_closed` (авто, только если ещё `new`).

## Конфиги (правятся вручную, без кода)

- `config/orgs.yaml` — организации для ATS-коннекторов: `{org, tier, ats: lever|greenhouse|personio, slug}`.
- `config/searches.yaml` — поисковые запросы: `{id, source: himalayas|adzuna|jobspy_linkedin|jobspy_indeed, query/phrase, country/location, manual: true (опц.)}`.

Детали и живые уроки по каждому источнику — `docs/backlog/BACKLOG.md`, `docs/job-aggregator-landscape/notes.md`.
