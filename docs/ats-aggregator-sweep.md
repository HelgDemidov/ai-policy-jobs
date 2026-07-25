# Направление 1: ATS-агрегаторы — сверка шортлиста

Дата: 2026-07-25. Задача: для организаций Tier A/B уже в `think-tank-shortlist.html` найти, на каком ATS (applicant tracking system) у них живёт карьерная страница — чтобы подключить их к `scripts/run.py` тем же способом, что и первые 4 организации (Epoch AI, Apollo Research, Future of Life Institute, Center for AI Safety — все на Lever).

## Методология

Для каждой организации: WebSearch на упоминание известных ATS-доменов (`jobs.lever.co`, `boards.greenhouse.io`, `jobs.ashbyhq.com`, позже добавлен `jobs.personio.com`) + там, где WebSearch не дал прямого URL — WebFetch/curl на саму карьерную страницу в поисках ссылки на внешний ATS. Любой найденный `200`-ответ проверялся по содержимому, а не только по коду ответа — см. урок ниже.

**Живой урок методологии:** короткий/обобщённый ATS-слаг может случайно совпасть с чужой, никак не связанной компанией. При проверке `boards-api.greenhouse.io/v1/boards/iai/jobs` получили `200` с валидным JSON — но при чтении содержимого оказалось, что это британская tech-компания (вакансии вроде «Applied AI Engineer», локации London/Bristol/Manchester), а не Istituto Affari Internazionali. Из этого — жёсткое правило: код ответа `200` — не доказательство совпадения организации, всегда читать контент.

## Результат — организация → платформа

| Организация | Тир | ATS |
|---|---|---|
| ECFR (European Council on Foreign Relations) | B | **Personio** ✅ подключено |
| IAPS | A | custom (Rails/Webpacker на careers.rethinkpriorities.org) |
| Rethink Priorities | A | custom (тот же Rails-сайт) |
| Convergence Analysis | A | не найдено |
| GovAI | B | custom (governance.ai) + Airtable-форма для expression of interest |
| Chatham House | B | custom (careers.chathamhouse.org) |
| IISS | B | custom (iiss.org/careers) |
| RAND Europe | B | custom (rand.org/randeurope) |
| CLTR | B | custom (longtermresilience.org) |
| Ada Lovelace Institute | B | custom (adalovelaceinstitute.org) |
| CSER | B | custom (cser.ac.uk) |
| The Future Society | B | не найдено |
| Egmont Institute | B | custom (egmontinstitute.be) |
| Bruegel | B | custom |
| EUISS | B | custom (iss.europa.eu) |
| DGAP | B | custom (dgap.org) |
| Bertelsmann Stiftung | B | custom |
| Clingendael Institute | B | custom (careers.clingendael.org) |
| St. Gallen Endowment | B | custom (упоминается join.com — не проверено детально) |
| UNIDIR | B | не найдено (вероятно UN-система, отдельный кейс) |
| IAI (Istituto Affari Internazionali) | B | custom (lavoro.iai.it — **не путать** с чужой Greenhouse-компанией «iai», см. урок выше) |
| interface (ex-SNV) | B | не найдено |
| LawAI (UK hub) | B | custom (law-ai.org/career/) |
| Belgrade Centre for Security Policy | A | не найдено |
| Institute Alternative | A | не найдено |

**Счёт: 1 подтверждённое совпадение из ~24 проверенных организаций.**

## Находка: ECFR на Personio

Живой публичный XML-фид, без авторизации: `https://ecfr.jobs.personio.com/xml`.

Схема одной позиции (`<position>`): `id`, `name`, `office`, `department`, `schedule`, `employmentType`, `seniority`, `createdAt` (ISO datetime) + вложенный `jobDescriptions` — список `{name, value}`, `value` содержит HTML. Прямого URL вакансии в фиде нет, но он конструируется предсказуемо: `https://{slug}.jobs.personio.com/job/{id}` (подтверждено живым запросом — `200`).

Реализован третий коннектор `scripts/personio.py` (тот же контракт `fetch(slug) -> list[dict]`, что у `lever.py`/`greenhouse.py`), зарегистрирован в `run.py::CONNECTORS`, 3 теста в `tests/test_personio.py`. ECFR добавлен в `orgs.yaml` (tier B). Живой прогон: 2 реальные вакансии (Sofia, Berlin) — база выросла с 28 до 30 записей.

## Вывод

Для think tank'ов/policy-организаций (в отличие от EA-adjacent AI-safety стартапов вроде Epoch AI/Apollo Research/FLI/CAIS, которые почти поголовно на Lever) угадывание/поиск публичного ATS-слага — метод с низкой отдачей: 1 хит из ~24. Подавляющее большинство держит кастомные/самописные карьерные страницы. Дальнейший рост охвата по ЭТИМ конкретным организациям реалистичен через HTML-скрейп-коннектор, а не продолжение перебора ATS вручную.

Отдельный, более общий вывод — см. `job-aggregator-landscape.md`: сам подход «знаем организацию → ищем её ATS» может быть не оптимальным по сравнению с query-centric поиском вакансий через агрегаторы (Google Jobs / JobSpy / RemoteOK и т.п.), который находит организации И вакансии одновременно, по ключевому слову, а не по заранее известному имени.
