#!/bin/bash

# Granola Sync - запуск синхронизации

SCRIPT_PATH="$HOME/.local/bin/granola-sync/granola_sync.py"

# Запускаем Terminal с синхронизацией
osascript <<'EOF'
tell application "Terminal"
    -- Создаем новое окно с командой
    set newWindow to do script "clear && printf '\\033[1;36m' && echo '╔════════════════════════════════════════════╗' && echo '║     🔄  Granola → Obsidian Sync  🔄        ║' && echo '╚════════════════════════════════════════════╝' && printf '\\033[0m' && echo '' && export PYTHONPATH=\"$HOME/Library/Python/3.14/lib/python/site-packages:$PYTHONPATH\" && /opt/homebrew/bin/python3 \"$HOME/.local/bin/granola-sync/granola_sync.py\" 2>&1 && echo '' && printf '\\033[1;32m' && echo '✅ Синхронизация завершена!' && printf '\\033[0m' && echo '' && echo 'Нажмите любую клавишу для выхода...' && read -n 1 -s && exit"

    -- Активируем Terminal
    activate

    -- Устанавливаем заголовок окна
    set custom title of newWindow to "Granola Sync"

    -- Устанавливаем размер окна
    tell window 1
        set bounds to {100, 100, 900, 600}
    end tell
end tell
EOF
