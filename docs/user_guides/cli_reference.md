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

## Веб-GUI на Vercel (`docs/tech_specs/vercel-web-gui/spec.md`)

Прод: https://ai-policy-jobs.vercel.app — статический фронтенд (`web/public/`) + Python Vercel Functions (`web/api/`), данные читаются/пишутся напрямую из Vercel Blob (`jobs.db`), без БД-сервера. Гейт — `SITE_PASSWORD` (cookie), не встроенная Vercel Password Protection (недоступна на Hobby-плане).

```bash
cd web && vercel deploy --prod   # выкатить текущий код web/ в прод (нужен vercel link один раз на новой машине)
vercel logs <url>                # логи функций (Python-трейсбеки, если что-то падает)
vercel curl <url>/api/postings   # прогнать запрос с обходом Vercel Deployment Protection (актуально для superview-URL, прод им не прикрыт)
```

**Живая находка: `vercel blob put`/`get` понимают `--allow-overwrite`/`--add-random-suffix` только как флаги-без-значения** — присутствие флага включает, отсутствие выключает; `--add-random-suffix false` включает суффикс, а не выключает его (CLI 58.5.1, проверено на реальном сторе, задокументировано в `docs.vercel.com/docs/cli/blob`, не совпадает с `--help`-текстом команды).

**Живая находка: GET-ответы для `jobs.db` из Vercel Blob приходят со слабым ETag (`W/"..."`).** Для условной записи (`If-Match`) нужен сильный валидатор (RFC 7232) — `web/api/_blob.py` срезает префикс `W/` перед использованием в заголовке записи; без этого каждая запись статуса падала 409/412.

**Живая находка: read-after-write в Vercel Blob не мгновенный** — GET сразу после успешного POST/status может ещё ~минуту отдавать старое значение (CDN-кэш). `web/public/app.js` больше не перезапрашивает состояние после успешной записи статуса — обновляет карточку из уже известного ответа.

Синхронизация данных — не через этот раздел, а через `scripts/blob_sync.py`, вызывается автоматически из `run.py __main__` (см. «Автозапуск» выше): скачивает `jobs.db` перед прогоном (подтягивает статусы, проставленные через веб-GUI), заливает обратно после.

## Прямой доступ к БД

```bash
sqlite3 data/jobs.db "SELECT org, title, status FROM postings WHERE status='new'"
```
Статусы: `new` → `reviewed`/`applied`/`rejected` (вручную) / `likely_closed` (авто, только если ещё `new`).

## Конфиги (правятся вручную, без кода)

- `config/orgs.yaml` — организации для ATS-коннекторов: `{org, tier, ats: lever|greenhouse|personio, slug}`.
- `config/searches.yaml` — поисковые запросы: `{id, source: himalayas|adzuna|jobspy_linkedin|jobspy_indeed, query/phrase, country/location, manual: true (опц.)}`.

Детали и живые уроки по каждому источнику — `docs/backlog/BACKLOG.md`, `docs/job-aggregator-landscape/notes.md`.
