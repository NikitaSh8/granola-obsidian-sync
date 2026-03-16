#!/bin/bash

# Granola Sync — установочный скрипт для macOS

set -e

echo "╔════════════════════════════════════════════╗"
echo "║     🔄  Granola Sync — Установка          ║"
echo "╚════════════════════════════════════════════╝"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/.local/bin/granola-sync"
LAUNCHAGENT_DIR="$HOME/Library/LaunchAgents"
APP_DIR="$HOME/Applications/Granola Sync.app"

# 1. Проверяем Python
echo "🔍 Проверяю Python..."
if command -v /opt/homebrew/bin/python3 &>/dev/null; then
    PYTHON="/opt/homebrew/bin/python3"
elif command -v python3 &>/dev/null; then
    PYTHON="$(which python3)"
else
    echo "❌ Python3 не найден. Установите: brew install python3"
    exit 1
fi
echo "   ✅ Python: $PYTHON ($($PYTHON --version))"

# 2. Проверяем requests
echo "🔍 Проверяю библиотеку requests..."
if $PYTHON -c "import requests" 2>/dev/null; then
    echo "   ✅ requests установлен"
else
    echo "   📦 Устанавливаю requests..."
    $PYTHON -m pip install --user --break-system-packages requests
fi

# 3. Проверяем Granola
echo "🔍 Проверяю Granola..."
GRANOLA_CREDS="$HOME/Library/Application Support/Granola/supabase.json"
if [ -f "$GRANOLA_CREDS" ]; then
    echo "   ✅ Granola авторизована"
else
    echo "   ⚠️  Granola credentials не найдены."
    echo "      Убедитесь что Granola установлена и вы вошли в аккаунт."
fi

# 4. Копируем скрипт
echo ""
echo "📁 Устанавливаю скрипт..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/granola_sync.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/granola_sync_config.json" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/granola_sync.py"
echo "   ✅ Скрипт: $INSTALL_DIR/granola_sync.py"

# 5. Настраиваем конфигурацию
echo ""
echo "⚙️  Проверяю конфигурацию..."
echo "   Текущий путь к Obsidian Vault:"
VAULT_PATH=$($PYTHON -c "import json; print(json.load(open('$INSTALL_DIR/granola_sync_config.json'))['obsidian_vault_path'])")
echo "   $VAULT_PATH"
EXPANDED_PATH="${VAULT_PATH/#\~/$HOME}"
if [ -d "$EXPANDED_PATH" ]; then
    echo "   ✅ Папка существует"
else
    echo "   ⚠️  Папка не найдена! Отредактируйте:"
    echo "      $INSTALL_DIR/granola_sync_config.json"
fi

# 6. Настраиваем launchd
echo ""
echo "⏰ Настраиваю автозапуск (каждые 5 минут)..."

# Обновляем пути в plist
PLIST_FILE="$LAUNCHAGENT_DIR/com.granola.sync.plist"
mkdir -p "$LAUNCHAGENT_DIR"

# Создаём plist с правильными путями
cat > "$PLIST_FILE" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.granola.sync</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$INSTALL_DIR/granola_sync.py</string>
    </array>

    <key>StartInterval</key>
    <integer>300</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/granola_sync.log</string>

    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/granola_sync_error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
PLISTEOF

launchctl unload "$PLIST_FILE" 2>/dev/null || true
launchctl load "$PLIST_FILE"
echo "   ✅ Автозапуск настроен"

# 7. Создаём macOS приложение
echo ""
echo "📱 Создаю macOS приложение..."
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"
cp "$SCRIPT_DIR/Info.plist" "$APP_DIR/Contents/"

cat > "$APP_DIR/Contents/MacOS/granola-sync" << 'APPEOF'
#!/bin/bash
osascript <<'EOF'
tell application "Terminal"
    set newWindow to do script "clear && printf '\\033[1;36m' && echo '╔════════════════════════════════════════════╗' && echo '║     🔄  Granola → Obsidian Sync  🔄        ║' && echo '╚════════════════════════════════════════════╝' && printf '\\033[0m' && echo '' && /opt/homebrew/bin/python3 \"$HOME/.local/bin/granola-sync/granola_sync.py\" 2>&1 && echo '' && printf '\\033[1;32m' && echo '✅ Синхронизация завершена!' && printf '\\033[0m' && echo '' && echo 'Нажмите любую клавишу для выхода...' && read -n 1 -s && exit"
    activate
    set custom title of newWindow to "Granola Sync"
    tell window 1
        set bounds to {100, 100, 900, 600}
    end tell
end tell
EOF
APPEOF

chmod +x "$APP_DIR/Contents/MacOS/granola-sync"
xattr -cr "$APP_DIR" 2>/dev/null || true
echo "   ✅ Приложение: $APP_DIR"

# 8. Тест
echo ""
echo "🧪 Тестирую синхронизацию..."
$PYTHON "$INSTALL_DIR/granola_sync.py"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   ✅ Установка завершена!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   📱 Приложение:  ~/Applications/Granola Sync.app"
echo "   ⏰ Автозапуск:  каждые 5 минут"
echo "   📝 Логи:        ~/.local/bin/granola-sync/granola_sync.log"
echo "   ⚙️  Конфигурация: ~/.local/bin/granola-sync/granola_sync_config.json"
echo ""
