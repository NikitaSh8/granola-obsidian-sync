# Granola Sync

Скрипт для автоматической синхронизации транскриптов из [Granola](https://www.granola.so) в [Obsidian](https://obsidian.md) через **официальный Public API** (требуется платный тариф Granola).

## Что делает

- Получает все встречи workspace через `https://public-api.granola.ai/v1/`
- Сохраняет summary (markdown) + verbatim транскрипт в .md файлы
- Только дельта: пропускает заметки без изменений по `updated_at`
- Удаляет дубликаты от облачной синхронизации (iCloud/Dropbox)
- Авто-детект Obsidian vault'а по `.obsidian` маркеру

## Требования

- macOS (или Linux, без launchd-агента)
- Python 3.x
- Платный тариф Granola с API-ключом (`grn_...`)
- Библиотека `requests`:
  ```bash
  pip3 install --user --break-system-packages requests
  ```

## Где взять API-ключ

В аккаунте Granola: **Settings → API** (или раздел Developer/Integrations). Сгенерируй ключ в нужном workspace — API возвращает только заметки этого workspace.

Документация Granola: <https://docs.granola.ai/introduction>

## Быстрая установка

```bash
./install.sh
```

## Ручная установка

### 1. Скопировать скрипт и конфиг

```bash
mkdir -p ~/.local/bin/granola-sync
cp granola_sync.py ~/.local/bin/granola-sync/
cp granola_sync_config.example.json ~/.local/bin/granola-sync/granola_sync_config.json
chmod 600 ~/.local/bin/granola-sync/granola_sync_config.json
```

### 2. Настроить конфиг

Отредактируй `~/.local/bin/granola-sync/granola_sync_config.json`:

```json
{
  "obsidian_vault_path": "~/Obsidian/06 Transcripts",
  "transcripts_subfolder": "06 Transcripts",
  "granola_api_key": "grn_YOUR_KEY_HERE",
  "granola_api_base": "https://public-api.granola.ai/v1",
  "page_size": 30
}
```

Альтернатива — переменная окружения `GRANOLA_API_KEY` (имеет приоритет над конфигом).

`obsidian_vault_path` может не существовать — скрипт сам поищет vault с папкой `06 Transcripts`. Также можно переопределить через `OBSIDIAN_VAULT_PATH`.

### 3. Тестовый запуск

```bash
python3 ~/.local/bin/granola-sync/granola_sync.py
```

Должно появиться `Найдено заметок в Granola: N` и созданные файлы.

### 4. Автозапуск каждые 5 минут (macOS launchd)

Подправь пути в `com.granola.sync.plist` под себя, потом:

```bash
cp com.granola.sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.granola.sync.plist
```

## Логи

```bash
tail -f ~/.local/bin/granola-sync/granola_sync.log
tail -f ~/.local/bin/granola-sync/granola_sync_error.log
```

## Управление

```bash
launchctl list | grep granola      # статус
launchctl unload ~/Library/LaunchAgents/com.granola.sync.plist   # стоп
launchctl load ~/Library/LaunchAgents/com.granola.sync.plist     # старт
```

## Формат файлов

Каждая заметка сохраняется как `YYYY-MM-DD - Название.md`:

```markdown
---
granola_id: not_xxxxxxxxxxxxxx
created: 2026-05-08T09:23:47.776Z
updated: 2026-05-08T09:24:13.614Z
title: "Название встречи"
web_url: https://notes.granola.ai/d/...
tags:
  - meeting
  - granola
---


## Summary

(markdown summary)


---

## Transcript

**🎤 Вы** (09:24:04):
> текст
```

## Безопасность

- API-ключ хранится в `granola_sync_config.json` с правами `600` (только владелец)
- State-файл (`.granola_sync_state.json`) лежит **рядом со скриптом**, не в Obsidian vault — это снимает блокировки iCloud
- Скрипт не передаёт ключ никуда кроме `public-api.granola.ai`

---

## Архитектура

Раздел для случая «открыл репо через год и нужно понять что и почему».

### Поток данных за один тик

```
launchd (каждые 60 сек)
   └─> python3 granola_sync.py
         ├─> читает granola_sync_config.json     (или env GRANOLA_API_KEY)
         ├─> читает .granola_sync_state.json     (что уже синкнуто)
         │
         ├─> GET /v1/notes                        (список всех заметок workspace, с пагинацией)
         │       Authorization: Bearer grn_...
         │
         ├─> сравнивает updated_at каждой заметки со state
         │       Если все совпадают → выход (idle tick, ~30мс)
         │
         ├─> для изменившихся (или новых):
         │     ├─> сканирует папку Obsidian: строит индекс {granola_id → filepath}
         │     ├─> удаляет дубликаты iCloud (имена с " 2.md", " 3.md")
         │     ├─> для каждой заметки:
         │     │     ├─> GET /v1/notes/{id}?include=transcript
         │     │     ├─> форматирует markdown (frontmatter + summary + transcript)
         │     │     ├─> если такой granola_id уже в vault под другим именем → переименовать
         │     │     └─> записать файл (с retry на iCloud deadlock)
         │     └─> обновляет state
         │
         └─> пишет .granola_sync_state.json
```

### Структура файлов на диске

```
~/.local/bin/granola-sync/
├── granola_sync.py              ← исполняемый скрипт
├── granola_sync_config.json     ← конфиг с API-ключом (chmod 600)
├── .granola_sync_state.json     ← состояние синхронизации
├── granola_sync.log             ← stdout от launchd
└── granola_sync_error.log       ← stderr от launchd

~/Library/LaunchAgents/
└── com.granola.sync.plist       ← launchd конфигурация (StartInterval=60)

<obsidian_vault>/06 Transcripts/
├── 2026-05-08 - Название.md     ← синкнутые заметки
└── ...
```

State-файл лежит **рядом со скриптом**, а не в vault, специально — Obsidian vault часто синхронизируется через iCloud/Dropbox, и облако периодически блокирует файлы (`OSError: Resource deadlock avoided`). State-файл вне vault'а от этого избавлен.

### Что в state-файле

```json
{
  "synced_ids": {
    "not_PlJyY1hhIgp4mK": {
      "updated_at": "2026-05-08T09:24:13.614Z",
      "hash": "63685bcdb48ebcbe9bd3d1db22b3922d"
    }
  },
  "last_sync": "2026-05-08T12:32:01.234567"
}
```

- `synced_ids[id].updated_at` — версия заметки на момент последней успешной синхры (сравнивается с API для определения дельты)
- `synced_ids[id].hash` — md5 от итогового содержимого файла (если содержимое не поменялось, файл не перезаписывается)
- `last_sync` — для дебага, не используется в логике

Удаление state-файла = полный пересинк (все заметки будут перезаписаны на следующем тике).

### Логика дедупа

Два механизма работают вместе:

1. **По `granola_id` в frontmatter.** При каждом проходе с реальной работой строится индекс `{granola_id → filepath}` из всех `.md` в папке. Если API вернул заметку, чей `granola_id` уже привязан к файлу с другим именем (потому что пользователь переименовал встречу в Granola) — скрипт переименовывает файл, не создаёт новый.

2. **По имени файла с суффиксом `" 2"`, `" 3"`.** Когда iCloud видит две версии одного файла на разных машинах, он создаёт `Файл 2.md`. Скрипт находит такие пары (одинаковый `granola_id`, имена `X.md` и `X 2.md`) и удаляет дубликаты с суффиксом, оставляя оригинал.

### API: что нужно знать

**Базовые ограничения (на 2026-05):**
- `page_size` максимум **30** — больше нельзя
- Cursor-based пагинация (поле `cursor` в ответе → передавай в следующий запрос)
- Возвращаются **только заметки workspace, в котором сгенерирован ключ**. Личные заметки из других workspace невидимы.
- Нет webhook'ов / push-уведомлений → polling (отсюда тикающий launchd)

**Endpoints:**
- `GET /v1/notes?page_size=30&cursor=...&updated_after=...` — список (только metadata: id, title, owner, created_at, updated_at)
- `GET /v1/notes/{id}?include=transcript` — полная заметка с verbatim'ом транскрипта и markdown саммари

**Поля в полной заметке (`NoteDetail`):**
- `transcript` — массив `{speaker: {source, diarization_label}, text, start_time, end_time}`
  - `source`: `microphone` (вы) / `system` (другой динамик) / `assemblyai` и т.д.
  - `diarization_label`: `Speaker A`, `Speaker B`, ...
- `summary_markdown` / `summary_text` — авто-саммари от Granola
- `web_url` — ссылка на встречу в `notes.granola.ai`
- `attendees`, `calendar_event`, `folder_membership` — пока не используем

Полный OpenAPI: <https://docs.granola.ai/api-reference/openapi.json>

### Failure modes и что с ними делать

| Симптом | Причина | Как чинить |
|---|---|---|
| `HTTP ошибка: 401` | Ключ невалиден / пересгенерён | Обнови `granola_api_key` в конфиге |
| `HTTP ошибка: 400 Number must be less than or equal to 30` | `page_size` > 30 в конфиге | Поставь 30 (или меньше) |
| `Сетевая ошибка: ... Failed to resolve` | Нет интернета на момент тика | Игнорировать, следующий тик через 60 сек |
| Файлы не появляются, но скрипт молчит | Ключ из другого workspace, чем где встречи | Сгенерируй ключ в правильном workspace |
| Дубликаты с " 2.md" не удаляются | iCloud очень настойчивый | Пройдёт само на следующем не-idle тике (когда есть новые заметки) |
| `OSError: Resource deadlock avoided` | iCloud блокирует файл | retry уже встроен (3 попытки × 1 сек), почти всегда проходит |
| State полностью побит | Невалидный JSON в state-файле | Удалить файл, скрипт пересоздаст и сделает полный пересинк |

### Где менять что

- **Интервал sync** → `com.granola.sync.plist` поле `<key>StartInterval</key>` (секунды). После правки: `launchctl unload && launchctl load`
- **Формат итогового .md** → функция `sync()` в `granola_sync.py`, секция «Frontmatter» и сборка `parts`
- **Форматирование транскрипта** (имена спикеров, эмодзи) → `format_transcript()`
- **Санитайз имён файлов** → `sanitize_filename()` (по умолчанию: вырезает `<>:"/\|?*`, обрезает до 100 символов по последнему пробелу)
- **Логика дедупа** → `cleanup_duplicates()` и `build_existing_index()`
- **Где искать vault'ы автоматически** → `find_obsidian_vaults()`

### Что НЕ делает (умышленно)

- Не удаляет файлы из Obsidian, если заметка удалена в Granola (только добавляет/обновляет/переименовывает)
- Не читает `attendees`, `calendar_event`, `folder_membership` из API ответа (можно дописать)
- Не работает с несколькими workspace одновременно (один скрипт = один ключ = один workspace)
- Не делает push-уведомлений и не интегрируется с другими сервисами

## История

- **v4.1**: интервал 60 сек, idle-тики ничего не делают если в API нет изменений
- **v4**: переход на официальный Public API (Bearer-токен, требует платный тариф). Без зависимости от Granola.app
- **v3**: фикс iCloud deadlock'ов, retry на файловые операции
- **v2**: дедуп дубликатов, инсталлятор, .app
- **v1**: первый релиз через неофициальные `/v2/get-documents` endpoints (больше не работает — сервер требует именно Granola.app в User-Agent)

## Лицензия

MIT
