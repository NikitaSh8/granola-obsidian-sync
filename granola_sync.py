#!/usr/bin/env python3
"""
Granola to Obsidian Sync Script
Автоматически экспортирует транскрипты встреч из Granola в Obsidian.
Включает саммари И полный транскрипт.

Конфигурация: granola_sync_config.json (рядом со скриптом)
"""

import json
import os
import re
import hashlib
import unicodedata
from pathlib import Path
from datetime import datetime
import requests
from html.parser import HTMLParser

# Загрузка конфигурации
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "granola_sync_config.json"

def load_config() -> dict:
    """Загружает конфигурацию из JSON файла."""
    default_config = {
        "obsidian_vault_path": "~/Documents/Obsidian Vault/Transcripts",
        "granola_credentials_path": "~/Library/Application Support/Granola/supabase.json",
        "granola_cache_path": "~/Library/Application Support/Granola/cache-v3.json",
    }

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                user_config = json.load(f)
            default_config.update(user_config)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Ошибка чтения конфига {CONFIG_PATH}: {e}")
            print("Используются настройки по умолчанию.")

    return default_config

CONFIG = load_config()

# Конфигурация путей (из конфиг-файла)
GRANOLA_CREDENTIALS_PATH = os.path.expanduser(CONFIG["granola_credentials_path"])
GRANOLA_CACHE_PATH = os.path.expanduser(CONFIG["granola_cache_path"])
OBSIDIAN_VAULT_PATH = os.path.expanduser(CONFIG["obsidian_vault_path"])
MEETINGS_FOLDER = ""  # Сохраняем в корень указанной папки
# State-файл хранится рядом со скриптом, а не в Obsidian Vault,
# чтобы избежать блокировок iCloud
SYNC_STATE_FILE = str(SCRIPT_DIR / ".granola_sync_state.json")
# Миграция: если state-файл остался в старом месте, переносим
_old_state = os.path.join(OBSIDIAN_VAULT_PATH, ".granola_sync_state.json")
if os.path.exists(_old_state) and not os.path.exists(SYNC_STATE_FILE):
    import shutil
    shutil.move(_old_state, SYNC_STATE_FILE)

# API
GRANOLA_API_URL = "https://api.granola.ai/v2/get-documents"
GRANOLA_TRANSCRIPT_API_URL = "https://api.granola.ai/v1/get-document-transcript"
USER_AGENT = "Granola/5.354.0"


class HTMLToMarkdown(HTMLParser):
    """Простой конвертер HTML в Markdown."""

    def __init__(self):
        super().__init__()
        self.result = []
        self.list_stack = []  # Stack for nested lists
        self.current_list_item = []

    def handle_starttag(self, tag, attrs):
        if tag == 'h1':
            self.result.append('\n# ')
        elif tag == 'h2':
            self.result.append('\n## ')
        elif tag == 'h3':
            self.result.append('\n### ')
        elif tag == 'h4':
            self.result.append('\n#### ')
        elif tag == 'ul':
            self.list_stack.append('ul')
        elif tag == 'ol':
            self.list_stack.append('ol')
        elif tag == 'li':
            indent = '  ' * (len(self.list_stack) - 1)
            if self.list_stack and self.list_stack[-1] == 'ol':
                self.result.append(f'\n{indent}1. ')
            else:
                self.result.append(f'\n{indent}- ')
        elif tag == 'p':
            self.result.append('\n')
        elif tag == 'br':
            self.result.append('\n')
        elif tag == 'strong' or tag == 'b':
            self.result.append('**')
        elif tag == 'em' or tag == 'i':
            self.result.append('*')
        elif tag == 'code':
            self.result.append('`')
        elif tag == 'a':
            href = dict(attrs).get('href', '')
            self.result.append('[')
            self._pending_href = href

    def handle_endtag(self, tag):
        if tag in ('h1', 'h2', 'h3', 'h4'):
            self.result.append('\n')
        elif tag == 'ul' or tag == 'ol':
            if self.list_stack:
                self.list_stack.pop()
            if not self.list_stack:
                self.result.append('\n')
        elif tag == 'p':
            self.result.append('\n')
        elif tag == 'strong' or tag == 'b':
            self.result.append('**')
        elif tag == 'em' or tag == 'i':
            self.result.append('*')
        elif tag == 'code':
            self.result.append('`')
        elif tag == 'a':
            href = getattr(self, '_pending_href', '')
            self.result.append(f']({href})')
            self._pending_href = ''

    def handle_data(self, data):
        self.result.append(data)

    def get_markdown(self):
        text = ''.join(self.result)
        # Cleanup multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def html_to_markdown(html: str) -> str:
    """Конвертирует HTML в Markdown."""
    parser = HTMLToMarkdown()
    parser.feed(html)
    return parser.get_markdown()


def get_access_token() -> str:
    """Читает access token из файла credentials Granola."""
    with open(GRANOLA_CREDENTIALS_PATH, "r") as f:
        data = json.load(f)

    workos_tokens = json.loads(data["workos_tokens"])
    return workos_tokens["access_token"]


def load_granola_cache() -> dict:
    """Загружает локальный кэш Granola с транскриптами."""
    try:
        with open(GRANOLA_CACHE_PATH, "r") as f:
            data = json.load(f)
        cache = json.loads(data["cache"])
        return cache.get("state", {})
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {}


def get_api_headers(token: str) -> dict:
    """Возвращает заголовки для API запросов."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": USER_AGENT,
        "X-Client-Version": "5.354.0",
    }


def fetch_documents(token: str, limit: int = 100, offset: int = 0) -> list:
    """Получает документы из Granola API."""
    headers = get_api_headers(token)

    payload = {
        "limit": limit,
        "offset": offset,
        "include_last_viewed_panel": True,
    }

    response = requests.post(GRANOLA_API_URL, headers=headers, json=payload)
    response.raise_for_status()

    return response.json().get("docs", [])


def fetch_transcript_from_api(token: str, doc_id: str) -> list:
    """Получает транскрипт документа через API."""
    headers = get_api_headers(token)

    try:
        response = requests.post(
            GRANOLA_TRANSCRIPT_API_URL,
            headers=headers,
            json={"document_id": doc_id},
            timeout=15
        )
        if response.status_code == 200:
            return response.json()
    except (requests.exceptions.RequestException, json.JSONDecodeError):
        pass

    return []


def prosemirror_to_markdown(node: dict, depth: int = 0) -> str:
    """Конвертирует ProseMirror JSON в Markdown."""
    if not node:
        return ""

    node_type = node.get("type", "")
    content = node.get("content", [])
    text = node.get("text", "")
    marks = node.get("marks", [])
    attrs = node.get("attrs", {})

    # Обработка текста с форматированием
    if node_type == "text":
        result = text
        for mark in marks:
            mark_type = mark.get("type", "")
            if mark_type == "bold":
                result = f"**{result}**"
            elif mark_type == "italic":
                result = f"*{result}*"
            elif mark_type == "code":
                result = f"`{result}`"
            elif mark_type == "link":
                href = mark.get("attrs", {}).get("href", "")
                result = f"[{result}]({href})"
        return result

    # Обработка блочных элементов
    if node_type == "doc":
        return "".join(prosemirror_to_markdown(child, depth) for child in content)

    if node_type == "paragraph":
        para_content = "".join(prosemirror_to_markdown(child, depth) for child in content)
        return f"{para_content}\n\n"

    if node_type == "heading":
        level = attrs.get("level", 1)
        heading_content = "".join(prosemirror_to_markdown(child, depth) for child in content)
        return f"{'#' * level} {heading_content}\n\n"

    if node_type == "bulletList":
        items = "".join(prosemirror_to_markdown(child, depth) for child in content)
        return items

    if node_type == "orderedList":
        result = ""
        for i, child in enumerate(content, 1):
            item_content = "".join(
                prosemirror_to_markdown(c, depth) for c in child.get("content", [])
            )
            # Убираем лишние переносы и добавляем нумерацию
            item_text = item_content.strip().replace("\n\n", "\n")
            result += f"{i}. {item_text}\n"
        return result + "\n"

    if node_type == "listItem":
        item_content = "".join(prosemirror_to_markdown(child, depth + 1) for child in content)
        # Убираем лишние переносы строк внутри элемента списка
        item_text = item_content.strip().replace("\n\n", "\n")
        indent = "  " * depth
        return f"{indent}- {item_text}\n"

    if node_type == "blockquote":
        quote_content = "".join(prosemirror_to_markdown(child, depth) for child in content)
        lines = quote_content.strip().split("\n")
        return "\n".join(f"> {line}" for line in lines) + "\n\n"

    if node_type == "codeBlock":
        code_content = "".join(prosemirror_to_markdown(child, depth) for child in content)
        lang = attrs.get("language", "")
        return f"```{lang}\n{code_content.strip()}\n```\n\n"

    if node_type == "horizontalRule":
        return "---\n\n"

    if node_type == "hardBreak":
        return "\n"

    # Для неизвестных типов просто обрабатываем содержимое
    return "".join(prosemirror_to_markdown(child, depth) for child in content)


def extract_summary(doc: dict) -> str:
    """Извлекает саммари из документа Granola."""
    # Проверяем last_viewed_panel для саммари
    last_viewed_panel = doc.get("last_viewed_panel", {})

    if last_viewed_panel:
        content = last_viewed_panel.get("content")
        if content:
            # Если HTML, конвертируем в Markdown
            if isinstance(content, str) and content.strip().startswith("<"):
                return html_to_markdown(content)
            # Если dict (ProseMirror), конвертируем
            if isinstance(content, dict):
                return prosemirror_to_markdown(content)
            # Если строка JSON
            if isinstance(content, str) and content.strip().startswith("{"):
                try:
                    parsed = json.loads(content)
                    return prosemirror_to_markdown(parsed)
                except json.JSONDecodeError:
                    pass
            return content

    # Альтернативные поля
    for field in ["notes", "content"]:
        if field in doc and doc[field]:
            value = doc[field]
            if isinstance(value, dict):
                return prosemirror_to_markdown(value)
            if isinstance(value, str) and value.strip():
                if value.strip().startswith("<"):
                    return html_to_markdown(value)
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        return prosemirror_to_markdown(parsed)
                except json.JSONDecodeError:
                    pass
                return value

    return ""


def format_transcript(segments: list) -> str:
    """Форматирует сегменты транскрипта в читаемый Markdown."""
    if not segments:
        return ""

    lines = []
    current_speaker = None

    for segment in segments:
        text = segment.get("text", "").strip()
        if not text:
            continue

        source = segment.get("source", "unknown")
        timestamp = segment.get("start_timestamp", "")

        # Форматируем время
        time_str = ""
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M:%S")
            except:
                pass

        # Проверяем, есть ли метка спикера в тексте (формат "Speaker A: текст")
        speaker_match = re.match(r'^(Speaker [A-Z]):\s*(.+)$', text, re.DOTALL)
        if speaker_match:
            speaker = speaker_match.group(1)
            text = speaker_match.group(2).strip()
        else:
            # Определяем спикера по source
            if source == "microphone":
                speaker = "🎤 Вы"
            elif source == "system":
                speaker = "🔊 Система"
            elif source == "assemblyai":
                speaker = "👤 Участник"
            else:
                speaker = f"👤 {source.title()}"

        # Добавляем разделитель при смене спикера
        if speaker != current_speaker:
            current_speaker = speaker
            if time_str:
                lines.append(f"\n**{speaker}** ({time_str}):")
            else:
                lines.append(f"\n**{speaker}**:")

        lines.append(f"> {text}")

    return "\n".join(lines)


def sanitize_filename(name) -> str:
    """Очищает строку для использования в имени файла."""
    if not name or not isinstance(name, str):
        name = "Без названия"
    # Заменяем недопустимые символы
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    # Убираем лишние пробелы и тире
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'-+', '-', name)
    # Ограничиваем длину
    if len(name) > 100:
        name = name[:100].rsplit(' ', 1)[0]
    return name


def format_date(date_str: str) -> str:
    """Форматирует дату из ISO формата."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return datetime.now().strftime("%Y-%m-%d")


def _retry_file_op(func, retries=3, delay=1):
    """Повторяет файловую операцию при блокировке iCloud."""
    import time
    for attempt in range(retries):
        try:
            return func()
        except OSError as e:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


def load_sync_state() -> dict:
    """Загружает состояние синхронизации."""
    if os.path.exists(SYNC_STATE_FILE):
        def _read():
            with open(SYNC_STATE_FILE, "r") as f:
                return json.load(f)
        try:
            return _retry_file_op(_read)
        except (OSError, json.JSONDecodeError):
            return {"synced_ids": {}}
    return {"synced_ids": {}}


def save_sync_state(state: dict):
    """Сохраняет состояние синхронизации."""
    def _write():
        with open(SYNC_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    _retry_file_op(_write)


def get_content_hash(content: str) -> str:
    """Вычисляет хеш контента для отслеживания изменений."""
    return hashlib.md5(content.encode()).hexdigest()


def build_granola_id_index(meetings_path: Path) -> dict:
    """Строит индекс granola_id -> filepath по существующим файлам."""
    index = {}
    for md_file in meetings_path.glob("*.md"):
        try:
            def _read_id(f=md_file):
                with open(f, "r", encoding="utf-8") as fh:
                    in_frontmatter = False
                    for i, line in enumerate(fh):
                        if i == 0 and line.strip() == "---":
                            in_frontmatter = True
                            continue
                        if in_frontmatter and line.strip() == "---":
                            return None
                        if in_frontmatter and line.startswith("granola_id:"):
                            return line.split(":", 1)[1].strip()
                        if i > 15:
                            return None
                return None
            gid = _retry_file_op(_read_id)
            if gid:
                index.setdefault(gid, []).append(md_file)
        except (IOError, UnicodeDecodeError, OSError):
            pass
    return index


def cleanup_duplicates(meetings_path: Path):
    """Удаляет дубликаты файлов (суффикс ' 2', ' 3' и т.д. от облачной синхронизации)."""
    id_index = build_granola_id_index(meetings_path)
    removed = 0
    for gid, files in id_index.items():
        if len(files) <= 1:
            continue
        # Сортируем: файл без суффикса " N" — основной
        def has_dupe_suffix(f):
            stem = f.stem
            # Проверяем суффикс типа " 2", " 3"
            return bool(re.search(r' \d+$', stem))

        originals = [f for f in files if not has_dupe_suffix(f)]
        dupes = [f for f in files if has_dupe_suffix(f)]

        if not originals:
            # Все с суффиксами — оставляем первый
            originals = [sorted(dupes)[0]]
            dupes = sorted(dupes)[1:]

        for dupe in dupes:
            print(f"Удаляю дубликат: {dupe.name}")
            dupe.unlink()
            removed += 1

    if removed:
        print(f"Удалено {removed} дубликатов\n")
    return removed


def sync_documents():
    """Основная функция синхронизации."""
    print("Начинаю синхронизацию Granola -> Obsidian...")

    # Создаем папку для встреч если не существует
    meetings_path = Path(OBSIDIAN_VAULT_PATH) / MEETINGS_FOLDER
    meetings_path.mkdir(parents=True, exist_ok=True)

    # Удаляем дубликаты от облачной синхронизации
    cleanup_duplicates(meetings_path)

    # Получаем токен и документы
    try:
        token = get_access_token()
    except FileNotFoundError:
        print(f"Ошибка: файл credentials не найден: {GRANOLA_CREDENTIALS_PATH}")
        print("Убедитесь, что Granola установлена и вы вошли в аккаунт.")
        return
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Ошибка чтения credentials: {e}")
        return

    try:
        documents = fetch_documents(token)
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к API Granola: {e}")
        return

    print(f"Найдено {len(documents)} документов в Granola")

    # Загружаем локальный кэш с транскриптами
    cache = load_granola_cache()
    cached_transcripts = cache.get("transcripts", {})
    print(f"Найдено {len(cached_transcripts)} транскриптов в локальном кэше")

    # Загружаем состояние синхронизации
    state = load_sync_state()
    synced_ids = state.get("synced_ids", {})

    # Строим индекс granola_id -> файлы для поиска переименованных
    id_index = build_granola_id_index(meetings_path)

    new_count = 0
    updated_count = 0
    api_transcript_count = 0

    for doc in documents:
        doc_id = doc.get("id")
        title = doc.get("title") or "Без названия"
        created_at = doc.get("created_at", "")
        updated_at = doc.get("updated_at", created_at)

        # Форматируем имя файла: YYYY-MM-DD - Название.md
        date_str = format_date(created_at)
        safe_title = sanitize_filename(title)
        filename = f"{date_str} - {safe_title}.md"
        filepath = meetings_path / filename

        # Если файл с таким granola_id уже существует под другим именем — удаляем старый
        if doc_id in id_index:
            for old_file in id_index[doc_id]:
                # Сравниваем имена с учётом Unicode нормализации (macOS использует NFD)
                old_name_normalized = unicodedata.normalize("NFC", old_file.name)
                new_name_normalized = unicodedata.normalize("NFC", filename)
                if old_name_normalized != new_name_normalized and old_file.exists():
                    print(f"Переименовано в Granola: {old_file.name} -> {filename}")
                    old_file.unlink()

        # Извлекаем саммари
        summary = extract_summary(doc)

        # Пробуем получить транскрипт: сначала из кэша, потом через API
        transcript_segments = cached_transcripts.get(doc_id, [])

        if not transcript_segments:
            # Если в кэше нет, пробуем получить через API
            transcript_segments = fetch_transcript_from_api(token, doc_id)
            if transcript_segments:
                api_transcript_count += 1

        transcript_text = format_transcript(transcript_segments)

        # Создаем frontmatter
        escaped_title = title.replace('"', '\\"')
        frontmatter = f"""---
granola_id: {doc_id}
created: {created_at}
updated: {updated_at}
title: "{escaped_title}"
tags:
  - meeting
  - granola
---

"""

        # Собираем полный контент: саммари + транскрипт
        content_parts = [frontmatter]

        if summary:
            content_parts.append("## Summary\n\n")
            content_parts.append(summary)
            content_parts.append("\n\n")

        if transcript_text:
            content_parts.append("---\n\n## Transcript\n")
            content_parts.append(transcript_text)
            content_parts.append("\n")

        full_content = "".join(content_parts)
        content_hash = get_content_hash(full_content)

        # Проверяем, нужно ли обновлять
        if doc_id in synced_ids:
            if synced_ids[doc_id] == content_hash:
                continue  # Контент не изменился
            updated_count += 1
            print(f"Обновляю: {filename}")
        else:
            new_count += 1
            print(f"Новый: {filename}")

        # Записываем файл (с retry при блокировке iCloud/Obsidian)
        def _write_file():
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(full_content)
        try:
            _retry_file_op(_write_file)
        except OSError as e:
            print(f"  ⚠️ Не удалось записать {filename}: {e}")
            continue

        # Обновляем состояние
        synced_ids[doc_id] = content_hash

    # Сохраняем состояние
    state["synced_ids"] = synced_ids
    state["last_sync"] = datetime.now().isoformat()
    save_sync_state(state)

    print(f"\nСинхронизация завершена!")
    print(f"  Новых: {new_count}")
    print(f"  Обновлено: {updated_count}")
    print(f"  Транскриптов через API: {api_transcript_count}")
    print(f"  Всего в Granola: {len(documents)}")


if __name__ == "__main__":
    sync_documents()
