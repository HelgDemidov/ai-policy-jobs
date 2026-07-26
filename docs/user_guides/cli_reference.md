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

## Автозапуск (systemd user timer, реализовано 2026-07-26)

`scripts/run.py` теперь запускается сам, раз в сутки, без участия куратора. Юниты — в `~/.config/systemd/user/`, **не в репозитории** (абсолютные пути конкретной машины) — при переносе на новую машину создать заново по тексту ниже, поправив пути.

`job-search-run.service`:
```ini
[Unit]
Description=Job Search Tracker — daily sync (scripts/run.py)

[Service]
Type=oneshot
WorkingDirectory=/home/fastcentrifuge/Рабочий стол/job-search
ExecStart="/home/fastcentrifuge/Рабочий стол/job-search/.venv/bin/python" "/home/fastcentrifuge/Рабочий стол/job-search/scripts/run.py"
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

## Прямой доступ к БД

```bash
sqlite3 data/jobs.db "SELECT org, title, status FROM postings WHERE status='new'"
```
Статусы: `new` → `reviewed`/`applied`/`rejected` (вручную) / `likely_closed` (авто, только если ещё `new`).

## Конфиги (правятся вручную, без кода)

- `orgs.yaml` — организации для ATS-коннекторов: `{org, tier, ats: lever|greenhouse|personio, slug}`.
- `searches.yaml` — поисковые запросы: `{id, source: himalayas|adzuna|jobspy_linkedin|jobspy_indeed, query/phrase, country/location, manual: true (опц.)}`.

Детали и живые уроки по каждому источнику — `docs/BACKLOG.md`, `docs/job-aggregator-landscape.md`.
