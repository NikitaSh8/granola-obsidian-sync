# Granola Obsidian Sync

Automatically sync meeting notes and full transcripts from [Granola AI](https://granola.ai) to your [Obsidian](https://obsidian.md) vault as Markdown files.

## Features

- Exports **both summary and full transcript** for each meeting
- Supports transcripts from **macOS and iOS** (via Granola API)
- Files named as `YYYY-MM-DD - Meeting Title.md` with YAML frontmatter
- **Incremental sync** — only new or changed documents are updated
- Deleted files are **not re-created** (respects manual cleanup)
- Converts HTML and ProseMirror JSON summaries to clean Markdown
- Formats transcripts with speaker labels and timestamps

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Granola AI  │────>│  granola_sync.py │────>│   Obsidian   │
│   (cloud)    │ API │                  │ .md │    Vault     │
└─────────────┘     │  ┌────────────┐  │     │  /Transcripts│
                    │  │ Local cache│  │     └──────────────┘
┌─────────────┐     │  │(cache-v3)  │  │
│  supabase   │────>│  └────────────┘  │
│  .json      │auth │                  │
│ (credentials│     │  ┌────────────┐  │
└─────────────┘     │  │ sync state │  │
                    │  │  (.json)   │  │
                    │  └────────────┘  │
                    └──────────────────┘
                      ▲           ▲
                      │           │
               ┌──────┘     ┌─────┘
               │             │
        ┌──────────┐  ┌───────────────┐
        │ macOS App│  │  LaunchAgent  │
        │ (manual) │  │(every 5 min)  │
        └──────────┘  └───────────────┘
```

## Setup

### 1. Prerequisites

- macOS with Python 3
- [Granola](https://granola.ai) installed and signed in
- [Obsidian](https://obsidian.md) vault

### 2. Install dependencies

```bash
pip3 install requests
```

### 3. Clone and configure

```bash
git clone https://github.com/NikitaSh8/granola-obsidian-sync.git
cd granola-obsidian-sync

# Copy and edit config
cp granola_sync_config.example.json granola_sync_config.json
```

Edit `granola_sync_config.json` — set the path to your Obsidian vault:

```json
{
  "obsidian_vault_path": "~/Documents/Obsidian Vault/Transcripts",
  "granola_credentials_path": "~/Library/Application Support/Granola/supabase.json",
  "granola_cache_path": "~/Library/Application Support/Granola/cache-v3.json"
}
```

### 4. Run manually

```bash
python3 granola_sync.py
```

## Auto-sync (LaunchAgent)

To run sync automatically every 5 minutes:

1. Copy and edit the LaunchAgent plist:

```bash
cp macos-app/com.user.granola-sync.plist ~/Library/LaunchAgents/
```

2. Edit `~/Library/LaunchAgents/com.user.granola-sync.plist` — replace `/PATH/TO/` with actual paths to your script and logs.

3. Load the agent:

```bash
launchctl load ~/Library/LaunchAgents/com.user.granola-sync.plist
```

Logs are written to `~/Library/Logs/granola-sync.log`.

## macOS App (manual sync)

A simple `.app` bundle is included in `macos-app/` for one-click sync from Finder or Spotlight.

1. Copy `macos-app/Granola Sync.app` to `~/Applications/`
2. Edit the script path inside `Granola Sync.app/Contents/MacOS/granola-sync`
3. Make it executable: `chmod +x ~/Applications/Granola\ Sync.app/Contents/MacOS/granola-sync`

## Output format

Each synced meeting creates a Markdown file like:

```markdown
---
granola_id: abc-123-def
created: 2026-01-15T10:00:00Z
updated: 2026-01-15T11:00:00Z
title: "Weekly Team Standup"
tags:
  - meeting
  - granola
---

## Summary

Key points discussed...

---

## Transcript

**Speaker A** (10:00:15):
> Hello everyone, let's get started...

**Speaker B** (10:00:22):
> Sure, I have an update on...
```

## How it works

1. Reads Granola auth token from `supabase.json` (stored by the Granola desktop app)
2. Fetches document list via `POST /v2/get-documents`
3. For each document, extracts the summary (HTML or ProseMirror JSON -> Markdown)
4. Fetches transcript: first checks local cache (`cache-v3.json`), then falls back to `POST /v1/get-document-transcript` API
5. Writes combined summary + transcript as a Markdown file with YAML frontmatter
6. Tracks content hashes in `.granola_sync_state.json` to avoid redundant writes

## License

MIT
