# pal-directory: как выпустить

Раздел для общего `RELEASE.md`. pal-directory пушится **третьим**, после pal-norms и pal-devices-data. Из его `data/v1/` берут регионы, ведомства и номера obrashchenie-kit, home-care-kit и хаб, поэтому до их `sync-data` у pal-directory должен быть зелёный `pages`

## 1. До первого пуша

1. Включить Pages из Actions, иначе первый `pages.yml` упадёт на `deploy-pages`:

   ```sh
   gh api -X POST repos/openpalliative/pal-directory/pages -f build_type=workflow
   ```

   Если Pages уже включены из ветки: `gh api -X PUT repos/openpalliative/pal-directory/pages -f build_type=workflow`

2. Разрешить Actions создавать PR. Без этого наблюдатель не пришлёт новую таблицу (`create-pull-request` падает с ошибкой прав). В org и в репо: Settings > Actions > General > Workflow permissions > «Allow GitHub Actions to create and approve pull requests». Права по умолчанию оставить «Read repository contents»: нужные права выданы в каждом workflow

   ```sh
   gh api -X PUT orgs/openpalliative/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
   gh api -X PUT repos/openpalliative/pal-directory/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
   ```

3. Метки. Формы issue и наблюдатель ставят `report:number`, `review:data`, `watch:unreachable`, `watch:format`, `watch:old-source`, `watch:freeze`. Наблюдатель создаёт свою метку сам, если её нет, а формы issue без метки теряют её молча. Полный список ставит `scripts/labels` хаба. Если он ещё не запущен, нужные метки этого репо:

   ```sh
   gh label create report:number --color E99695 --description "Сообщение о неверном номере телефона" --repo openpalliative/pal-directory --force
   gh label create review:data --color FBCA04 --description "Данные изменились, нужна сверка человеком перед слиянием" --repo openpalliative/pal-directory --force
   for l in watch:unreachable watch:format watch:old-source watch:freeze; do
     gh label create "$l" --color FEF2C0 --repo openpalliative/pal-directory --force
   done
   ```

4. Security: private vulnerability reporting (на него ссылаются `SECURITY.md`, `CODE_OF_CONDUCT.md` и `config.yml` форм issue), secret scanning, push protection, Dependabot alerts:

   ```sh
   gh api -X PUT repos/openpalliative/pal-directory/private-vulnerability-reporting
   ```

## 2. Переменные репо

Все три это `vars`, не `secrets`. Пустая переменная значит безопасное поведение по умолчанию

| Переменная | По умолчанию | Что делает |
|---|---|---|
| `PD_DATA_MODE` | `links` | режим данных в `pages.yml` и `release.yml`: `links` без номеров регионов, `real` номера из таблицы Росздравнадзора. `demo` на Pages не ставить |
| `WATCH_ENABLED` | выключено | `true` включает расписание `watch.yml` (понедельник, 04:17 UTC). Ручной запуск работает всегда |
| `WATCH_RUNNER` | `"ubuntu-24.04"` | JSON-строка для `runs-on`, если нужен свой раннер |

Решения мейнтейнера от 11.10.2026: на Pages реальные номера, таблицу и страницу горячих линий Росздравнадзора считаем открытыми данными, расписание наблюдателя включено, `WATCH_RUNNER` не задаём. Чтобы их исполнить, после первого зелёного `pages`:

```sh
gh variable set PD_DATA_MODE --repo openpalliative/pal-directory --body real
gh variable set WATCH_ENABLED --repo openpalliative/pal-directory --body true
gh workflow run pages.yml --repo openpalliative/pal-directory
```

Откатить: `gh variable delete PD_DATA_MODE --repo openpalliative/pal-directory` (вернётся `links`) и `gh variable delete WATCH_ENABLED ...` (останется ручной запуск). После смены `PD_DATA_MODE` пересобрать Pages, а потребителям запустить `sync-data`

### WATCH_RUNNER

Если roszdravnadzor.gov.ru не пускает раннеры GitHub:

- **по умолчанию:** мейнтейнер запускает наблюдателя у себя: `uv run python -m pipeline.watch`, потом коммитит `data/snapshots` и `data/meta.yaml` или открывает PR с новой таблицей сам
- **свой раннер:** `gh variable set WATCH_RUNNER --repo openpalliative/pal-directory --body '["self-hosted","linux","ru"]'`. Раннеру нужны git, gh и uv. Только на уровне этого репо, ephemeral, в репо нет workflow на `pull_request_target`, в настройках «Require approval for all outside collaborators». Включать только по решению мейнтейнера. Раннер в России ставит и обслуживает мейнтейнер в России

## 3. Пуш и первая проверка

1. Запушить main. Сработают `checks.yml` (actionlint и ворота: сборка в трёх режимах, e2e в трёх браузерах, скриншоты) и `pages.yml`
2. Дождаться зелёного `pages` и проверить живой сайт:
   - https://openpalliative.github.io/pal-directory/ открывается, в подвале версия и дата данных
   - https://openpalliative.github.io/pal-directory/data/v1/index.json отдаёт наборы `regions`, `region-lines`, `addressees`, `federal-lines`, `routers`, `routes`, `entrypoints` и остальные, что есть в сборке
   - в режиме `links` в `region-lines.json` пустой `items`, на карточке `regions/ru-kgd/` названия ведомств, адрес и ссылка на таблицу Росздравнадзора с датой файла, ни одного `tel:` кроме 112, 103, 8-800-700-84-36 и федеральных
   - в режиме `real` на той же карточке номера со статусом «Не проверено»
   - на «Откуда данные» ссылка «Стать куратором региона» ведёт на `docs/CURATORS.md`
   - несуществующий адрес внутри `/pal-directory/` отдаёт свою 404
3. Только после этого пушить obrashchenie-kit и home-care-kit и запускать у них `sync-data`

## 4. Наблюдатель

`watch.yml` по расписанию работает только при `WATCH_ENABLED=true`. Вручную:

```sh
gh workflow run watch.yml --repo openpalliative/pal-directory
gh run list --workflow watch.yml --repo openpalliative/pal-directory --limit 1
```

1. **Первый запуск вручную**, сразу после пуша. Записать в общий отчёт, отвечает ли roszdravnadzor.gov.ru раннерам GitHub: в логе шага `watch` строка «Проверка <дата>: режим facts» и в отчёте `_reports/watch.json` факт «файл не изменился» значат, что отвечает. «источник недоступен» значит, что нет
2. Посмотреть, что наблюдатель сделает, ничего не меняя в репо: запустить его локально и не коммитить результат. Для issue есть сухой прогон, он только печатает команды `gh`:

   ```sh
   uv run python -m pipeline.watch
   uv run python -m pipeline.watch --open-issues _reports/watch.json --dry-run
   git checkout -- data/snapshots data/meta.yaml
   ```

3. Файл тот же: коммит `data: снимок Росздравнадзора <дата>` прямо в main, после него `watch.yml` сам запускает `pages.yml` (коммит от `GITHUB_TOKEN` пересборку не запускает). Перед коммитом прогоняются pytest, сборка и `opsite check`
4. Если `main` защищён и требует PR, прямой коммит снимка не пройдёт. Варианты: в ruleset main добавить в обход GitHub Actions только для этого репо, или раз в месяц запускать наблюдателя локально (п. 2 без отката) и коммитить снимок самому. Работает ли обход для `GITHUB_TOKEN` в этой организации, не проверено
5. Файл новый: PR из ветки `watch/<дата>` с меткой `review:data` и таблицей «было / стало». PR от бота сам проверки не запускает, поэтому `watch.yml` запускает `checks.yml` на ветке PR. Pytest до PR не гоняется специально: если новая таблица ломает тесты, это видно в самом PR. Сливать только после сверки по таблице
6. Источник недоступен три недели подряд, формат сломался, файлу больше года: issue `[...]` с меткой `watch:*`. Дубли отсекаются по ключу в заголовке
7. GitHub выключает расписание в публичных репо после 60 дней без активности. Последний шаг `watch.yml` с `if: always()` включает workflow обратно (`PUT .../actions/workflows/watch.yml/enable`). Раз в месяц всё равно открыть вкладку Actions и проверить, что `watch` не выключен

Открытые данные Росздравнадзора (набор `7710537160-lta`) и индекс актов pravo.gov.ru Actions не опрашивают, их обновляет мейнтейнер вручную пайплайном данных

## 5. Защита main

Ruleset на main: изменения через PR, обязательные проверки `gate` и `actionlint` из `checks.yml`, без обязательного ревью CODEOWNERS, пока мейнтейнер один. Для снимка наблюдателя см. п. 4.4

## 6. Релиз

Тег `v<версия данных>`, например `v2026.10.11`:

```sh
git tag v2026.10.11 && git push origin v2026.10.11
```

`release.yml` собирает сайт так же, как Pages, с тем же `PD_DATA_MODE`, прогоняет pytest и `opsite check`, и кладёт в релиз:

- `pal-directory-<тег>-site.zip`: весь сайт для зеркала
- `pal-directory-<тег>-data.zip`: `data/v1/` со схемами, CSV и `index.json`
- `SHA256SUMS`

В заметках релиза строка «Режим данных: links» или «real». Проверить скачанное: `sha256sum -c SHA256SUMS`

## 7. Оформление репо

```sh
gh repo edit openpalliative/pal-directory \
  --description "Куда звонить в регионе по паллиативной помощи: ведомства, номера из таблицы Росздравнадзора, источник и дата у каждой записи" \
  --homepage https://openpalliative.github.io/pal-directory/ \
  --add-topic palliative-care --add-topic open-data --add-topic russia --add-topic hotlines --add-topic static-site
```

Social preview вручную: Settings > General > Social preview, файл `docs/social-preview.png` (1280 x 640)

## 8. Проверено локально

- actionlint 1.7.12 с shellcheck 0.10.0 по 4 workflow: 0 замечаний
- zizmor `--offline`: 0 замечаний
- пины действий сверены `git ls-remote` 12.10.2026: checkout v7.0.1, setup-uv v10.3.0, pnpm/action-setup v6.1.0, setup-node v7.1.0, upload-artifact v7.0.2, upload-pages-artifact v5.0.0, deploy-pages v5.0.1, create-pull-request v8.1.1
- формы issue, `config.yml` и `dependabot.yml` проходят схемы SchemaStore
