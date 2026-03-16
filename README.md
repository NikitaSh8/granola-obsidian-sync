# Granola Sync

Скрипт для автоматической синхронизации транскриптов из [Granola](https://www.granola.so) в [Obsidian](https://obsidian.md).

## Что делает

- Получает все встречи из Granola через API
- Сохраняет summary + полный транскрипт в Markdown-файлы
- Автоматически обновляет только изменившиеся файлы
- Удаляет дубликаты от облачной синхронизации (iCloud/Dropbox)
- Отслеживает переименования встреч в Granola

## Требования

- macOS
- Python 3.x
- Установленная и авторизованная [Granola](https://www.granola.so)
- Библиотека `requests`:
  ```bash
  pip3 install --user --break-system-packages requests
  ```

## Быстрая установка

```bash
./install.sh
```

## Ручная установка

### 1. Скопировать скрипт и конфигурацию

```bash
mkdir -p ~/.local/bin/granola-sync
cp granola_sync.py ~/.local/bin/granola-sync/
cp granola_sync_config.json ~/.local/bin/granola-sync/
```

### 2. Настроить конфигурацию

Отредактируйте `~/.local/bin/granola-sync/granola_sync_config.json`:

```json
{
  "obsidian_vault_path": "~/Documents/Obsidian Vault/YOUR_VAULT/06 Transcripts",
  "granola_credentials_path": "~/Library/Application Support/Granola/supabase.json",
  "granola_cache_path": "~/Library/Application Support/Granola/cache-v3.json"
}
```

### 3. Настроить автозапуск (каждые 5 минут)

```bash
# Отредактируйте пути в plist файле под вашу систему
cp com.granola.sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.granola.sync.plist
```

### 4. Создать macOS приложение (опционально)

```bash
mkdir -p ~/Applications/Granola\ Sync.app/Contents/MacOS
mkdir -p ~/Applications/Granola\ Sync.app/Contents/Resources
cp Info.plist ~/Applications/Granola\ Sync.app/Contents/
cp granola-sync.sh ~/Applications/Granola\ Sync.app/Contents/MacOS/granola-sync
chmod +x ~/Applications/Granola\ Sync.app/Contents/MacOS/granola-sync
```

## Использование

### Ручной запуск
```bash
python3 ~/.local/bin/granola-sync/granola_sync.py
```

### Через приложение
Двойной клик на `Granola Sync.app` в `~/Applications/`

### Автоматический запуск
Настроен через launchd, запускается каждые 5 минут.

```bash
# Проверить статус
launchctl list | grep granola

# Остановить
launchctl unload ~/Library/LaunchAgents/com.granola.sync.plist

# Запустить
launchctl load ~/Library/LaunchAgents/com.granola.sync.plist
```

## Логи

```bash
# Основной лог
tail -f ~/.local/bin/granola-sync/granola_sync.log

# Лог ошибок
tail -f ~/.local/bin/granola-sync/granola_sync_error.log
```

## Формат файлов

Каждый транскрипт сохраняется как `YYYY-MM-DD - Название встречи.md` и содержит:

- **Frontmatter** — granola_id, дата создания, теги
- **Summary** — саммари от Granola
- **Transcript** — полный транскрипт с временными метками

## Лицензия

MIT
