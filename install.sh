#!/bin/bash

# Granola Sync — установочный скрипт для macOS

set -e

echo "╔════════════════════════════════════════════╗"
echo "║     Granola Sync — Установка               ║"
echo "╚════════════════════════════════════════════╝"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/.local/bin/granola-sync"
LAUNCHAGENT_DIR="$HOME/Library/LaunchAgents"

# 1. Python
echo "→ Python..."
if command -v /opt/homebrew/bin/python3 &>/dev/null; then
    PYTHON="/opt/homebrew/bin/python3"
elif command -v python3 &>/dev/null; then
    PYTHON="$(which python3)"
else
    echo "  Python3 не найден. brew install python3"
    exit 1
fi
echo "  $PYTHON ($($PYTHON --version))"

# 2. requests
echo "→ requests..."
if ! $PYTHON -c "import requests" 2>/dev/null; then
    $PYTHON -m pip install --user --break-system-packages requests
fi
echo "  ok"

# 3. Файлы
echo "→ Копирую файлы в $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/granola_sync.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/granola_sync.py"

CONFIG_FILE="$INSTALL_DIR/granola_sync_config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    cp "$SCRIPT_DIR/granola_sync_config.example.json" "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
    echo "  Создан $CONFIG_FILE"
else
    echo "  Конфиг уже есть, не перезаписываю"
fi

# 4. Проверяем API-ключ
echo ""
KEY=$($PYTHON -c "import json; print(json.load(open('$CONFIG_FILE')).get('granola_api_key',''))")
if [[ -z "$KEY" || "$KEY" == "grn_YOUR_API_KEY_HERE" ]]; then
    echo "⚠  API-ключ не задан."
    echo "   1. Возьми ключ в Granola: Settings → API"
    echo "   2. Открой $CONFIG_FILE"
    echo "   3. Замени значение granola_api_key на свой grn_..."
    echo "   4. Запусти install.sh ещё раз"
    exit 0
fi

# 5. Тестовый запуск
echo "→ Тест запуска..."
$PYTHON "$INSTALL_DIR/granola_sync.py" || {
    echo "  Тест упал. Проверь ключ и obsidian_vault_path."
    exit 1
}

# 6. launchd
echo ""
echo "→ launchd (каждые 5 минут)..."
PLIST_FILE="$LAUNCHAGENT_DIR/com.granola.sync.plist"
mkdir -p "$LAUNCHAGENT_DIR"

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
echo "  ok"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Установка готова."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Логи:    $INSTALL_DIR/granola_sync.log"
echo "  Конфиг:  $CONFIG_FILE"
echo "  launchd: launchctl list | grep granola.sync"
echo ""
