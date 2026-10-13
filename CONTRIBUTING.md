# Как помочь «Куда звонить»

Спасибо, что хотите помочь. Здесь собраны номера и адресаты по регионам: куда звонить про обезболивание, лекарства и если отказали. Любой вклад важен: сообщение о номере, который не отвечает, понятнее написанная подпись, тест, перевод

Вклад можно делать под псевдонимом

[English below](#english)

## Сначала о приватности

Всё, что вы пишете в issues, pull request и обсуждениях, видят все. Поэтому:

- не пишите ФИО, диагнозы, адреса, телефоны людей и номера документов, даже свои
- не называйте сотрудника, который ответил по телефону, и не пересказывайте разговор с подробностями о больном
- не прикладывайте сканы, фото и тексты настоящих обращений, выписок и ответов
- не присылайте списки подопечных, пациентов или семей
- если в сообщение случайно попали личные данные, отредактируйте его или нажмите «Report content», мы скроем

Проект не ведёт учёт людей и не будет этого делать. Мы не принимаем функции, которые собирают контакты, хранят данные о семьях или звонивших, ведут карточки обращений или работают как CRM

## Правила для данных этого репо

- **Только официальные номера учреждений.** Номера Росздравнадзора, органов здравоохранения регионов и ТФОМС из таблицы Росздравнадзора и открытых данных Росздравнадзора, перечни организаций из официальных публикаций на publication.pravo.gov.ru. Личные мобильные номера сотрудников и ФИО не публикуем, даже если они есть в источнике
- **ФИО никогда.** Парсер вырезает ФИО и адреса почты из таблицы до записи, тесты это проверяют. Если вы видите ФИО в данных или на сайте, это ошибка: сообщите через issue, не повторяя само ФИО
- **Территории.** Проект публикует данные только по 83 субъектам, которые есть в `data/regions.csv`. Строки других территорий из таблиц источников отбрасываются в коде до записи (`pipeline/territories.py`), это постоянное правило проекта. Pull request с такими данными не принимаем, названия этих территорий в коде, текстах и тестах не пишем, кроме самого фильтра и его теста
- **verified.** У номера `verified: true` значит только одно: куратор региона в РФ дозвонился и номер отвечает по назначению, см. [docs/CURATORS.md](docs/CURATORS.md). Всё, что взято из таблицы без звонка, остаётся `verified: false` и на сайте показано как «Не проверено». Не ставьте `verified: true` по памяти или по сайту ведомства
- **Подпись дословно.** Назначение номера и часы работы переносим из источника слово в слово. «Круглосуточно» пишем только там, где так сказано в источнике
- **Без советов.** Без медицинских порогов, доз, названий препаратов и советов по лечению. Юридические и медицинские тексты идут с плашкой «черновик, нужна проверка юристом (или медиком) в РФ»
- **Источник у каждой записи:** ссылка, дата файла или публикации, `source_ref`. Номера, коды и пункты не придумываем
- **Сетевые запросы.** Pipeline ходит только на адреса из раздела «Источники и санкционные рамки» в [README.md](README.md). Новый адрес добавляется только вместе с тестом allowlist и обсуждением в issue

## Кому что можно сделать

- **Человеку в регионе.** Сообщить, что номер не отвечает или отвечает другая организация: форма [«Неверный номер»](https://github.com/openpalliative/pal-directory/issues/new?template=wrong-number.yml). Номер посмотрит мейнтейнер, проверку звонком делает куратор региона, если он есть
- **Куратору региона в РФ.** Раз в полгода звонить по номерам своего региона и отмечать результат через pull request. Как это устроено: [docs/CURATORS.md](docs/CURATORS.md), заявка через форму [«Стать куратором»](https://github.com/openpalliative/pal-directory/issues/new?template=curator.yml)
- **Юристу.** Проверить страницы маршрутов по региональным приказам (метка `review:legal`)
- **Разработчику.** Задачи с меткой `good first issue`, доступность, печать, тесты, поиск региона
- **Всем.** Открыть карточку своего региона, прочитать вслух человеку старше 60 и написать, где было непонятно

## Как устроен репо

Работа делится на зоны, чтобы правки не сталкивались:

- **данные:** `data/`, `pipeline/`, `raw/` и тесты данных. `data/rzn/lines.csv` генерирует парсер, руками его не правят: темы и скрытие строк задаются в `data/review/overrides.csv`
- **страницы:** `templates/`, `assets/`, `content/`, `lib/`, e2e и скриншоты
- **инфраструктура:** `.github/`, `README.md`, `docs/`, лицензии и файлы сообщества
- **общий UI:** папка `opsite/`. Это копия из хаба openpalliative.github.io, здесь её не меняют. Нужна правка общего UI, присылайте её в хаб, потом `sh scripts/sync-ui`

Устройство подробно: [ARCHITECTURE.md](ARCHITECTURE.md)

### Ворота

Перед pull request прогоните:

```sh
sh scripts/gate.sh
```

Это `uv sync`, `pnpm install`, pytest, сборка, `opsite check` (текст, ссылки, сеть, бюджеты), unit-тесты, e2e в headless-браузере и скриншоты. Сборку в другом режиме данных проверяйте так: `PD_DATA_MODE=links uv run python -m opsite build` и `PD_DATA_MODE=demo ...`. Pull request с красными воротами не сливаем

## Как прислать правку

1. Форкните репо и сделайте ветку
2. Внесите правку в своей зоне и прогоните ворота
3. Откройте pull request и заполните чек-лист в шаблоне: источник, `verified`, нет личных данных и данных исключённых территорий
4. Правки номеров и подписей смотрит человек с меткой `review:data`, тексты маршрутов `review:legal`

## Лицензия вклада

Отправляя pull request, вы соглашаетесь, что код распространяется по [MIT](LICENSE), а данные на условиях [LICENSE-DATA](LICENSE-DATA)

Поведение в проекте: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Уязвимости: [SECURITY.md](SECURITY.md)

---

## English

pal-directory lists regional hotlines and agencies in Russia for palliative care questions: pain relief, medicines, complaints. Every entry shows its source and date. The interface is in Russian, but you can help without knowing it

- **Privacy first.** Issues and pull requests are public. Never post names, diagnoses, addresses, personal phone numbers or document numbers, even your own. We do not accept CRM-like features or anything that collects contacts
- **No personal names in data.** Staff names and e-mail addresses from the source table are stripped before anything is written. If you see one, report it without repeating it
- **Territories.** Only the 83 regions listed in `data/regions.csv` are published. Rows for any other territory in the source tables are dropped in code (`pipeline/territories.py`) before anything is written
- **verified.** `verified: true` means a regional curator in Russia called the number. Everything else stays `verified: false` and is shown as not checked. See `docs/CURATORS.md`
- **Zones.** `opsite/` is a copy from the hub repo and is not edited here. Run `sh scripts/gate.sh` before opening a pull request

Code is MIT, data follows `LICENSE-DATA`. Pseudonymous contributions are welcome
