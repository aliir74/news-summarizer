# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram Persian News Summarizer Bot - A Python application that monitors Persian news Telegram channels and RSS feeds, generates AI-powered summaries using OpenRouter LLM, and posts summaries to a Telegram channel. Includes keyword-based filtering for Iran-related news from RSS feeds. Deployed on Railway platform.

## Commands

```bash
# Install dependencies
uv sync --all-extras

# Run application
uv run python -m src.main

# Run tests
uv run pytest

# Run tests with coverage (CI requires 80% minimum)
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80

# Lint
uv run ruff check src tests

# Type check
uv run pyright src
```

## Architecture

**Main Components:**

- **NewsSummarizer (main.py)** - Orchestrator that manages lifecycle, scheduling (APScheduler), and graceful shutdown via signal handlers
- **TelegramReader (telegram_reader.py)** - Pyrogram client with session string auth for reading channel messages
- **RSSReader (rss_reader.py)** - Async HTTP client (httpx) with feedparser for fetching and parsing RSS/Atom feeds. Includes URL-based deduplication to prevent duplicate articles across runs.
- **IranRelevanceFilter (iran_filter.py)** - Keyword-based filtering for Iran-related content with configurable keywords
- **TelegramBot (telegram_bot.py)** - Pyrogram bot for posting summaries with smart message splitting (4096 char limit)
- **Summarizer (summarizer.py)** - OpenRouter API integration via OpenAI SDK for Persian summarization
- **Config (config.py)** - Loads from environment variables + config/channels.yaml (supports Telegram channels, RSS feeds, Iran filter)

**Data Flow:**
1. Scheduler triggers at configured interval (default: 30 min)
2. TelegramReader fetches messages from monitored Telegram channels since last check
3. RSSReader fetches articles from configured RSS feeds since last check (skips already-seen URLs)
4. IranRelevanceFilter filters RSS articles for Iran-related content using keyword matching
5. Messages from both sources are merged and sorted by timestamp
6. Summarizer sends messages to LLM for Persian summary generation
7. TelegramBot posts formatted summary to output channel
8. State persisted: last-check timestamp to .last_check file, seen RSS URLs to .seen_urls file (max 1000 URLs)

## Code Style

- **Line length:** 100 characters
- **String quotes:** Double quotes
- **Linter:** Ruff with E, W, F, I, B, C4, UP, PLC0415 rules
- **Type checker:** Pyright in basic mode (Pyrogram lacks complete type stubs)
- **Import sorting:** isort via Ruff with "src" as first-party
- **Imports:** All imports must be at the top of the file (no inline/function-level imports). Enforced by PLC0415 rule.

## Testing

Tests use pytest-asyncio with auto mode. Shared fixtures in tests/conftest.py include sample configs, messages, and mock clients.

## Environment Variables

**Required:** TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING, TELEGRAM_BOT_TOKEN, OUTPUT_CHANNEL_ID, OPENROUTER_API_KEY

**Optional:** SUMMARY_INTERVAL_MINUTES (default: 30), LLM_MODEL (default: google/gemma-2-9b-it)

Generate session string with: `uv run python scripts/generate_session.py`

## Deployment

Push to main branch triggers GitHub Actions CI (lint, type-check, test) then auto-deploys to Railway if CI passes.
