# Job Search — Emerging Tech / AI Policy Analyst

Независимый трек, изначально начат из ворктри `side-hustle-job` в другом репо (G2AI_ME), с 2026-07-24 живёт отдельно здесь. Не связан с G2AI по содержанию — но curriculum/бэкграунд куратора (AI-governance для малых государств, международное регулирование) напрямую релевантен искомым позициям.

## Что и зачем

Ищем позицию **Emerging Tech / AI Policy Analyst** (диапазон ролей analyst → director, опционально PM) в think tank'ах и исследовательских подразделениях международных организаций, сфокусированных на policy/governance/global security/strategic stability вокруг emerging tech и AI (НЕ техническая стандартизация).

Гео-приоритет: **Тир A** (remote / Черногория-Сербия) > **Тир B** (Западная Европа) > **Тир C** (США/Япония, только сильные попадания). Вне скоупа: Китай, Россия, Ближний Восток, Восточная Европа.

Гражданство куратора — РФ, эмигрант ~4 года без планов на возврат (открыто заявляется в заявках) — это накладывает дополнительный фильтр специально на Тир C (детали и методология — в `docs/BACKLOG.md`).

Занятость: full-time приоритетно, part-time тоже подходит. Языки: английский и русский свободно, другие не требуются.

## Где что лежать

- **`docs/BACKLOG.md`** — статус работ по тирам, методология фильтрации, план, история решений и отклонённых вариантов. Читать за деталями сюда, не в этот файл.
- **`docs/ats-aggregator-sweep.md`** — направление 1: сверка ATS-платформ (Lever/Greenhouse/Personio) для организаций шортлиста.
- **`docs/job-aggregator-landscape.md`** — обновление знаний по query-centric job-агрегаторам (JobSpy, RemoteOK, Himalayas, Adzuna) — курс на смену подхода org-centric → query-centric.
- **`think-tank-shortlist.html`** — канонический артефакт-шортлист организаций (также опубликован как Claude Artifact — при обновлении republish того же file_path, чтобы не плодить новые ссылки).
- **`docs/tech_specs/query-connectors/spec.md`** — спек и реализация query-centric коннекторов (Himalayas/Adzuna/JobSpy) — вторая, дополняющая семья к org-centric ATS.
- **`orgs.yaml`** (org-centric: known org → ATS) + **`searches.yaml`** (query-centric: search term → orgs/postings из данных) + **`scripts/`** — рабочий инструмент мониторинга вакансий → локальный SQLite (`data/jobs.db`, gitignored). Запуск: **`.venv/bin/python scripts/run.py [--linkedin]`** (НЕ bare `python3` — с добавлением `python-jobspy`/`pandas` системного python недостаточно).
- **`app.py`** — карточный веб-интерфейс просмотра вакансий (Streamlit, свой `.venv/`). Запуск: `.venv/bin/streamlit run app.py`.
- **`tests/`** — pytest, герметично (не трогает боевую `data/jobs.db`). Запуск: `.venv/bin/pytest`.
