#!/usr/bin/env python3
"""
Granola Public API → Obsidian Sync
Тянет встречи и транскрипты через https://public-api.granola.ai/v1/
Авторизация: Bearer токен из конфига или env GRANOLA_API_KEY.

Конфигурация: granola_sync_config.json (рядом со скриптом)
"""

import json
import os
import re
import time
import hashlib
import unicodedata
from pathlib import Path
from datetime import datetime
import requests

# ── Конфиг ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "granola_sync_config.json"


def load_config() -> dict:
    default = {
        "obsidian_vault_path": "~/Documents/Obsidian Vault/Transcripts",
        "transcripts_subfolder": "06 Transcripts",
        "granola_api_key": "",
        "granola_api_base": "https://public-api.granola.ai/v1",
        "page_size": 100,
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                default.update(json.load(f))
        except (json.JSONDecodeError, IOError) as e:
            print(f"Ошибка чтения конфига {CONFIG_PATH}: {e}")
    return default


def find_obsidian_vaults() -> list:
    roots = [
        Path.home(),
        Path.home() / "Documents",
        Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
    ]
    vaults, seen = [], set()
    for root in roots:
        if not root.exists():
            continue
        try:
            for marker in list(root.glob("*/.obsidian")) + list(root.glob("*/*/.obsidian")):
                v = marker.parent.resolve()
                if v not in seen:
                    seen.add(v)
                    vaults.append(v)
        except (PermissionError, OSError):
            continue
    return vaults


def resolve_vault_path(cfg: dict) -> str:
    env = os.environ.get("OBSIDIAN_VAULT_PATH")
    if env:
        return os.path.expanduser(env)
    configured = os.path.expanduser(cfg["obsidian_vault_path"])
    if os.path.isdir(configured):
        return configured
    sub = cfg.get("transcripts_subfolder", "06 Transcripts")
    for vault in find_obsidian_vaults():
        cand = vault / sub
        if cand.is_dir():
            print(f"Авто-детект: {cand}")
            return str(cand)
    return configured


CONFIG = load_config()
OBSIDIAN_VAULT_PATH = resolve_vault_path(CONFIG)
API_KEY = os.environ.get("GRANOLA_API_KEY") or CONFIG.get("granola_api_key", "")
API_BASE = CONFIG["granola_api_base"].rstrip("/")
PAGE_SIZE = int(CONFIG.get("page_size", 100))

SYNC_STATE_FILE = str(SCRIPT_DIR / ".granola_sync_state.json")
# Миграция: старый state в vault → перенести
_old_state = os.path.join(OBSIDIAN_VAULT_PATH, ".granola_sync_state.json")
if os.path.exists(_old_state) and not os.path.exists(SYNC_STATE_FILE):
    import shutil
    shutil.move(_old_state, SYNC_STATE_FILE)


# ── Retry-обёртка для файловых операций (iCloud deadlock) ─────────────────────

def _retry_file_op(op, *args, max_attempts=3, **kwargs):
    last_err = None
    for attempt in range(max_attempts):
        try:
            return op(*args, **kwargs)
        except OSError as e:
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(1)
    raise last_err


# ── HTTP клиент ────────────────────────────────────────────────────────────────

def api_get(path: str, params: dict = None) -> dict:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
    }
    url = f"{API_BASE}{path}"
    r = requests.get(url, headers=headers, params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def list_all_notes(updated_after: str = None) -> list:
    """Все встречи (с пагинацией)."""
    notes = []
    cursor = None
    params_base = {"page_size": PAGE_SIZE}
    if updated_after:
        params_base["updated_after"] = updated_after
    while True:
        params = dict(params_base)
        if cursor:
            params["cursor"] = cursor
        data = api_get("/notes", params)
        notes.extend(data.get("notes", []))
        if not data.get("hasMore"):
            break
        cursor = data.get("cursor")
        if not cursor:
            break
    return notes


def get_note_with_transcript(note_id: str) -> dict:
    return api_get(f"/notes/{note_id}", {"include": "transcript"})


# ── Форматирование ────────────────────────────────────────────────────────────

def format_transcript(segments: list) -> str:
    if not segments:
        return ""
    lines = []
    current_speaker = None
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        sp = seg.get("speaker") or {}
        source = sp.get("source") or "unknown"
        label = sp.get("diarization_label") or ""

        if source == "microphone":
            speaker = "🎤 Вы"
        elif source == "system":
            speaker = "🔊 Система"
        else:
            speaker = f"👤 {label}" if label else f"👤 {source}"

        ts = seg.get("start_time", "")
        time_str = ""
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M:%S")
            except (ValueError, AttributeError):
                pass

        if speaker != current_speaker:
            current_speaker = speaker
            lines.append(f"\n**{speaker}** ({time_str}):" if time_str else f"\n**{speaker}**:")
        lines.append(f"> {text}")
    return "\n".join(lines)


def sanitize_filename(name) -> str:
    if not name or not isinstance(name, str):
        name = "Без названия"
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"-+", "-", name)
    if len(name) > 100:
        name = name[:100].rsplit(" ", 1)[0]
    return name or "Без названия"


def format_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return datetime.now().strftime("%Y-%m-%d")


def normalize_unicode(s: str) -> str:
    return unicodedata.normalize("NFC", s) if s else s


# ── State ─────────────────────────────────────────────────────────────────────

def load_sync_state() -> dict:
    def _read():
        if os.path.exists(SYNC_STATE_FILE):
            with open(SYNC_STATE_FILE, "r") as f:
                return json.load(f)
        return {"synced_ids": {}}
    try:
        return _retry_file_op(_read)
    except (json.JSONDecodeError, OSError):
        return {"synced_ids": {}}


def save_sync_state(state: dict):
    def _write():
        with open(SYNC_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    _retry_file_op(_write)


def content_hash(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


# ── Дедуп: индекс existing files by granola_id ────────────────────────────────

def build_existing_index(meetings_path: Path) -> dict:
    """Возвращает {granola_id: filepath} из всех файлов в папке."""
    index = {}
    for fp in meetings_path.glob("*.md"):
        try:
            content = _retry_file_op(fp.read_text, encoding="utf-8", errors="ignore")[:1500]
        except OSError:
            continue
        m = re.search(r"^granola_id:\s*([^\s\n]+)", content, re.MULTILINE)
        if m:
            index[m.group(1).strip()] = fp
    return index


def cleanup_duplicates(meetings_path: Path, index: dict) -> int:
    """Удаляет файлы с суффиксом ' 2', ' 3' если есть оригинал с тем же granola_id."""
    removed = 0
    by_id = {}
    for fp in meetings_path.glob("*.md"):
        try:
            content = _retry_file_op(fp.read_text, encoding="utf-8", errors="ignore")[:1500]
        except OSError:
            continue
        m = re.search(r"^granola_id:\s*([^\s\n]+)", content, re.MULTILINE)
        if not m:
            continue
        gid = m.group(1).strip()
        by_id.setdefault(gid, []).append(fp)
    for gid, files in by_id.items():
        if len(files) < 2:
            continue
        files.sort(key=lambda p: (re.search(r" \d+\.md$", p.name) is not None, p.name))
        # files[0] — оригинал, остальные — дубликаты
        for dup in files[1:]:
            if re.search(r" \d+\.md$", dup.name):
                try:
                    dup.unlink()
                    removed += 1
                    print(f"Удалён дубликат: {dup.name}")
                except OSError as e:
                    print(f"Не смог удалить {dup.name}: {e}")
    return removed


# ── Основная функция ─────────────────────────────────────────────────────────

def sync():
    if not API_KEY:
        print("ОШИБКА: API ключ не задан. Положи 'granola_api_key' в "
              f"{CONFIG_PATH} или экспортни GRANOLA_API_KEY.")
        return

    meetings_path = Path(OBSIDIAN_VAULT_PATH)
    meetings_path.mkdir(parents=True, exist_ok=True)

    state = load_sync_state()
    synced_ids = state.get("synced_ids", {})

    # Список встреч
    try:
        notes = list_all_notes()
    except requests.exceptions.HTTPError as e:
        print(f"HTTP ошибка: {e.response.status_code} {e.response.text[:200]}")
        return
    except requests.exceptions.RequestException as e:
        print(f"Сетевая ошибка: {e}")
        return

    # Быстрая проверка: какие заметки требуют обработки (изменились)?
    todo = []
    for note in notes:
        prev = synced_ids.get(note.get("id"), {})
        if not isinstance(prev, dict) or prev.get("updated_at") != note.get("updated_at"):
            todo.append(note)

    # Если ничего не поменялось — выходим без чтения файлов и без cleanup
    if not todo:
        state["last_sync"] = datetime.now().isoformat()
        save_sync_state(state)
        return

    print(f"Granola → Obsidian sync: {len(todo)} из {len(notes)} требуют обработки")

    # Тяжёлые операции — только когда есть реальная работа
    cleanup_duplicates(meetings_path, {})
    existing = build_existing_index(meetings_path)

    new_count = 0
    updated_count = 0

    for note in todo:
        note_id = note.get("id")
        title = note.get("title") or "Без названия"
        created_at = note.get("created_at", "")
        updated_at = note.get("updated_at", created_at)

        # Целевое имя файла
        date_str = format_date(created_at)
        safe_title = sanitize_filename(title)
        filename = f"{date_str} - {safe_title}.md"
        target_fp = meetings_path / filename

        # Если в vault уже есть файл с этим granola_id под другим именем — переименуем
        existing_fp = existing.get(note_id)
        if existing_fp and normalize_unicode(existing_fp.name) != normalize_unicode(filename):
            try:
                existing_fp.rename(target_fp)
                print(f"Переименован: {existing_fp.name} -> {filename}")
            except OSError as e:
                print(f"Не смог переименовать {existing_fp.name}: {e}")
                target_fp = existing_fp

        # Полные данные с транскриптом
        try:
            full = get_note_with_transcript(note_id)
        except requests.exceptions.RequestException as e:
            print(f"Не удалось получить {note_id} ({title}): {e}")
            continue

        transcript = format_transcript(full.get("transcript") or [])
        summary = full.get("summary_markdown") or full.get("summary_text") or ""
        web_url = full.get("web_url", "")

        # Frontmatter
        escaped_title = title.replace('"', '\\"')
        fm_lines = [
            "---",
            f"granola_id: {note_id}",
            f"created: {created_at}",
            f"updated: {updated_at}",
            f'title: "{escaped_title}"',
        ]
        if web_url:
            fm_lines.append(f"web_url: {web_url}")
        fm_lines += ["tags:", "  - meeting", "  - granola", "---", ""]
        frontmatter = "\n".join(fm_lines)

        parts = [frontmatter]
        if summary:
            parts += ["", "## Summary", "", summary, ""]
        if transcript:
            parts += ["", "---", "", "## Transcript", transcript, ""]
        full_content = "\n".join(parts)

        ch = content_hash(full_content)
        prev = synced_ids.get(note_id, {})
        if isinstance(prev, dict) and prev.get("hash") == ch:
            # updated_at поменялся, но содержимое идентичное — обновляем state и пропускаем запись
            synced_ids[note_id] = {"updated_at": updated_at, "hash": ch}
            continue

        is_new = note_id not in synced_ids
        try:
            def _write():
                with open(target_fp, "w", encoding="utf-8") as f:
                    f.write(full_content)
            _retry_file_op(_write)
        except OSError as e:
            print(f"Не смог записать {filename}: {e}")
            continue

        if is_new:
            new_count += 1
            print(f"Новый: {filename}")
        else:
            updated_count += 1
            print(f"Обновлён: {filename}")

        synced_ids[note_id] = {"updated_at": updated_at, "hash": ch}

    state["synced_ids"] = synced_ids
    state["last_sync"] = datetime.now().isoformat()
    save_sync_state(state)

    print(f"Готово: новых={new_count}, обновлено={updated_count}, всего в API={len(notes)}")


if __name__ == "__main__":
    sync()
