#!/usr/bin/env python3
"""
Granola to Obsidian Sync Script
Automatically exports meeting transcripts from Granola AI to Obsidian vault.
Includes both summary AND full transcript.

Configuration: granola_sync_config.json (next to this script)
"""

import json
import os
import re
import hashlib
from pathlib import Path
from datetime import datetime
import requests
from html.parser import HTMLParser

# Load configuration
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "granola_sync_config.json"


def load_config() -> dict:
    """Loads configuration from JSON file."""
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
            print(f"Error reading config {CONFIG_PATH}: {e}")
            print("Using default settings.")

    return default_config


CONFIG = load_config()

# Path configuration (from config file)
GRANOLA_CREDENTIALS_PATH = os.path.expanduser(CONFIG["granola_credentials_path"])
GRANOLA_CACHE_PATH = os.path.expanduser(CONFIG["granola_cache_path"])
OBSIDIAN_VAULT_PATH = os.path.expanduser(CONFIG["obsidian_vault_path"])
MEETINGS_FOLDER = ""  # Save to root of specified folder
SYNC_STATE_FILE = os.path.join(OBSIDIAN_VAULT_PATH, ".granola_sync_state.json")

# API
GRANOLA_API_URL = "https://api.granola.ai/v2/get-documents"
GRANOLA_TRANSCRIPT_API_URL = "https://api.granola.ai/v1/get-document-transcript"
USER_AGENT = "Granola/5.354.0"


class HTMLToMarkdown(HTMLParser):
    """Simple HTML to Markdown converter."""

    def __init__(self):
        super().__init__()
        self.result = []
        self.list_stack = []
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
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def html_to_markdown(html: str) -> str:
    """Converts HTML to Markdown."""
    parser = HTMLToMarkdown()
    parser.feed(html)
    return parser.get_markdown()


def get_access_token() -> str:
    """Reads access token from Granola credentials file."""
    with open(GRANOLA_CREDENTIALS_PATH, "r") as f:
        data = json.load(f)

    workos_tokens = json.loads(data["workos_tokens"])
    return workos_tokens["access_token"]


def load_granola_cache() -> dict:
    """Loads local Granola cache with transcripts."""
    try:
        with open(GRANOLA_CACHE_PATH, "r") as f:
            data = json.load(f)
        cache = json.loads(data["cache"])
        return cache.get("state", {})
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {}


def get_api_headers(token: str) -> dict:
    """Returns headers for API requests."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": USER_AGENT,
        "X-Client-Version": "5.354.0",
    }


def fetch_documents(token: str, limit: int = 100, offset: int = 0) -> list:
    """Fetches documents from Granola API."""
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
    """Fetches document transcript via API."""
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
    """Converts ProseMirror JSON to Markdown."""
    if not node:
        return ""

    node_type = node.get("type", "")
    content = node.get("content", [])
    text = node.get("text", "")
    marks = node.get("marks", [])
    attrs = node.get("attrs", {})

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
            item_text = item_content.strip().replace("\n\n", "\n")
            result += f"{i}. {item_text}\n"
        return result + "\n"

    if node_type == "listItem":
        item_content = "".join(prosemirror_to_markdown(child, depth + 1) for child in content)
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

    return "".join(prosemirror_to_markdown(child, depth) for child in content)


def extract_summary(doc: dict) -> str:
    """Extracts summary from a Granola document."""
    last_viewed_panel = doc.get("last_viewed_panel", {})

    if last_viewed_panel:
        content = last_viewed_panel.get("content")
        if content:
            if isinstance(content, str) and content.strip().startswith("<"):
                return html_to_markdown(content)
            if isinstance(content, dict):
                return prosemirror_to_markdown(content)
            if isinstance(content, str) and content.strip().startswith("{"):
                try:
                    parsed = json.loads(content)
                    return prosemirror_to_markdown(parsed)
                except json.JSONDecodeError:
                    pass
            return content

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
    """Formats transcript segments into readable Markdown."""
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

        time_str = ""
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M:%S")
            except:
                pass

        # Check for speaker label in text (format "Speaker A: text")
        speaker_match = re.match(r'^(Speaker [A-Z]):\s*(.+)$', text, re.DOTALL)
        if speaker_match:
            speaker = speaker_match.group(1)
            text = speaker_match.group(2).strip()
        else:
            if source == "microphone":
                speaker = "You (microphone)"
            elif source == "system":
                speaker = "System audio"
            elif source == "assemblyai":
                speaker = "Participant"
            else:
                speaker = source.title()

        if speaker != current_speaker:
            current_speaker = speaker
            if time_str:
                lines.append(f"\n**{speaker}** ({time_str}):")
            else:
                lines.append(f"\n**{speaker}**:")

        lines.append(f"> {text}")

    return "\n".join(lines)


def sanitize_filename(name) -> str:
    """Sanitizes a string for use as a filename."""
    if not name or not isinstance(name, str):
        name = "Untitled"
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'-+', '-', name)
    if len(name) > 100:
        name = name[:100].rsplit(' ', 1)[0]
    return name


def format_date(date_str: str) -> str:
    """Formats a date from ISO format."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return datetime.now().strftime("%Y-%m-%d")


def load_sync_state() -> dict:
    """Loads sync state."""
    if os.path.exists(SYNC_STATE_FILE):
        with open(SYNC_STATE_FILE, "r") as f:
            return json.load(f)
    return {"synced_ids": {}}


def save_sync_state(state: dict):
    """Saves sync state."""
    with open(SYNC_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_content_hash(content: str) -> str:
    """Computes content hash for change detection."""
    return hashlib.md5(content.encode()).hexdigest()


def sync_documents():
    """Main sync function."""
    print("Starting Granola -> Obsidian sync...")

    meetings_path = Path(OBSIDIAN_VAULT_PATH) / MEETINGS_FOLDER
    meetings_path.mkdir(parents=True, exist_ok=True)

    try:
        token = get_access_token()
    except FileNotFoundError:
        print(f"Error: credentials file not found: {GRANOLA_CREDENTIALS_PATH}")
        print("Make sure Granola is installed and you are signed in.")
        return
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error reading credentials: {e}")
        return

    try:
        documents = fetch_documents(token)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from Granola API: {e}")
        return

    print(f"Found {len(documents)} documents in Granola")

    cache = load_granola_cache()
    cached_transcripts = cache.get("transcripts", {})
    print(f"Found {len(cached_transcripts)} transcripts in local cache")

    state = load_sync_state()
    synced_ids = state.get("synced_ids", {})

    new_count = 0
    updated_count = 0
    api_transcript_count = 0

    for doc in documents:
        doc_id = doc.get("id")
        title = doc.get("title") or "Untitled"
        created_at = doc.get("created_at", "")
        updated_at = doc.get("updated_at", created_at)

        # Format filename: YYYY-MM-DD - Title.md
        date_str = format_date(created_at)
        safe_title = sanitize_filename(title)
        filename = f"{date_str} - {safe_title}.md"
        filepath = meetings_path / filename

        summary = extract_summary(doc)

        # Try to get transcript: cache first, then API fallback
        transcript_segments = cached_transcripts.get(doc_id, [])

        if not transcript_segments:
            transcript_segments = fetch_transcript_from_api(token, doc_id)
            if transcript_segments:
                api_transcript_count += 1

        transcript_text = format_transcript(transcript_segments)

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

        if doc_id in synced_ids:
            if synced_ids[doc_id] == content_hash:
                continue
            updated_count += 1
            print(f"Updated: {filename}")
        else:
            new_count += 1
            print(f"New: {filename}")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_content)

        synced_ids[doc_id] = content_hash

    state["synced_ids"] = synced_ids
    state["last_sync"] = datetime.now().isoformat()
    save_sync_state(state)

    print(f"\nSync complete!")
    print(f"  New: {new_count}")
    print(f"  Updated: {updated_count}")
    print(f"  Transcripts via API: {api_transcript_count}")
    print(f"  Total in Granola: {len(documents)}")


if __name__ == "__main__":
    sync_documents()
