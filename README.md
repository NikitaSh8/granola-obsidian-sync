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

## История

- **v4** (текущая): переход на официальный Public API. Bearer-токен, без зависимости от Granola.app
- **v3**: фикс iCloud deadlock'ов, retry на файловые операции
- **v2**: дедуп дубликатов, инсталлятор, .app
- **v1**: первый релиз через неофициальные `/v2/get-documents` endpoints (больше не работает)

## Лицензия

MIT
