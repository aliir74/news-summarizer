# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram Persian News Summarizer Bot - A Python application that monitors Persian news Telegram channels and RSS feeds, generates AI-powered summaries using OpenRouter LLM, and posts summaries to a Telegram channel. Includes keyword-based filtering for Iran-related news from RSS feeds. Runs on de-rarecloud VPS under systemd.

## Commands

```bash
# Install dependencies
uv sync --all-extras

# Run application (production mode)
uv run python -m src.main

# Run application (test mode - writes to file, separate state)
TEST_MODE=true uv run python -m src.main

# Run tests
uv run pytest

# Run tests with coverage (CI requires 90% minimum)
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=90

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
- **FileWriter (file_writer.py)** - File output for test mode, writes summaries to text file
- **OutputWriter (output_writer.py)** - Protocol defining output writer interface (TelegramBot/FileWriter)
- **BaleBot (bale_bot.py)** - Bale messenger output with persistent retry queue. On send failure, messages are queued to `.bale_retry_queue` and retried every 5 minutes. Retries run a health check (`getMe`) before attempting to flush — if Bale is unreachable, the flush is skipped entirely to avoid wasting LLM calls on `re_summarize()`. Items expire after 24 hours.
- **Summarizer (summarizer.py)** - OpenRouter API integration via OpenAI SDK for Persian summarization (includes `re_summarize()` for condensing multiple summaries)
- **AdaptiveCadenceController (cadence.py)** - Optional reflective cadence. Measures news intensity as a pre-dedup filtered message rate (messages/min) over a rolling window and maps it to an `IntensityLevel` (NORMAL/ELEVATED/SURGE) from the volume ratio against the rolling median baseline only (crisis keywords were removed as a zero-precision signal); a Cloudflare Radar outage promotes one level. Each evaluation returns a frozen `CadenceDecision` (previous/new interval, level, `CadenceChangeReason`): escalation is immediate (down to `min_interval_minutes`), decay is gradual (interval grows by `decay_factor` per calm run, capped at `SUMMARY_INTERVAL_MINUTES` or `max_interval_minutes`). Decay is gated behind `calm_streak_runs` consecutive NORMAL full-runs of hysteresis: a single quiet window mid-surge holds the tighter interval instead of relaxing, and any escalation (full-run or probe) resets the streak. This prevents the decay/re-escalate flapping that otherwise posts contradictory "calming"/"surging" notices minutes apart during a bursty event. Every interval change posts a one-line Persian notice via `post_alert` stating why the cadence changed (news volume rise, internet outage, calm decay) and the old-to-new interval. State persists to `.cadence_state`. Gated behind `adaptive_cadence.enabled`; an optional escalate-only probe (`fast_escalation`) tightens cadence between runs.
- **Models (models.py)** - Data models for messages and sources, HTML output formatting with Shamsi dates (jdatetime) and clickable source links
- **Config (config.py)** - Loads from environment variables + config/channels.yaml (supports Telegram channels, RSS feeds, Iran filter, adaptive cadence, test mode)

**Data Flow:**
1. Scheduler triggers at configured interval (default: 30 min production, 5 min test mode)
2. TelegramReader fetches messages from monitored Telegram channels since last check
3. RSSReader fetches articles from configured RSS feeds since last check (skips already-seen URLs)
4. IranRelevanceFilter filters RSS articles for Iran-related content using keyword matching
5. Messages from both sources are merged and sorted by timestamp
6. Summarizer sends messages to LLM for Persian summary generation
7. OutputWriter posts HTML-formatted summary with 🔹 bullet points and clickable source links (TelegramBot in production, FileWriter in test mode)
7b. If Bale summary posting fails, the message is queued to `.bale_retry_queue` for automatic retry. Retries health-check Bale first (`getMe`); only if healthy, multiple queued items are condensed via LLM re-summarization into one catch-up message. Failed alerts (radar, cadence notices) are dropped, never queued — a late alert is misleading
7c. If adaptive cadence is enabled, the pre-dedup filtered message rate (computed in step 4/5, before dedup) is fed to AdaptiveCadenceController, which reschedules the `summarize_news` job when the interval changes and posts a Persian cadence-change notice (reason + old-to-new interval) to the output channels via `post_alert`. With `fast_escalation`, a separate `probe_intensity` job runs every `probe_interval_minutes` to count messages cheaply (no LLM) and can escalate (posting the same notice) between full runs.
8. State persisted: last-check timestamp to state file (.last_check or .last_check.test), seen RSS URLs to .seen_urls file (max 1000 URLs), Bale retry queue to .bale_retry_queue, cadence window + current interval to .cadence_state

## Code Style

- **Line length:** 100 characters
- **String quotes:** Double quotes
- **Linter:** Ruff with E, W, F, I, B, C4, UP, PLC0415 rules
- **Type checker:** Pyright in basic mode (Pyrogram lacks complete type stubs)
- **Import sorting:** isort via Ruff with "src" as first-party
- **Imports:** All imports must be at the top of the file (no inline/function-level imports). Enforced by PLC0415 rule.
- **Fixed string values:** Always create Enum types for fields with fixed string values instead of using raw strings with comments. Example: use `AnomalyStatus` enum instead of `status: str  # "UNVERIFIED", "VERIFIED"`.

## Testing

Tests use pytest-asyncio with auto mode. Shared fixtures in tests/conftest.py include sample configs, messages, and mock clients.

## Environment Variables

**Required:** TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING, TELEGRAM_BOT_TOKEN, OUTPUT_CHANNEL_ID, OPENROUTER_API_KEY

**Optional:** SUMMARY_INTERVAL_MINUTES (default: 30), LLM_MODEL (default: google/gemini-2.5-flash-lite), BALE_BOT_TOKEN (Bale messenger bot token), BALE_CHANNEL_ID (Bale output channel)

**Test Mode:** TEST_MODE (default: false), TEST_SUMMARY_INTERVAL_MINUTES (default: 5), TEST_OUTPUT_DIR (default: output), TEST_STATE_FILE (default: .last_check.test)

Generate session string with: `uv run python scripts/generate_session.py`

## CI

Push to main branch triggers GitHub Actions CI (lint, type-check, test).

## Git Identity

This repo is on GitHub under `aliir74` (personal account).
- Remote URL must use SSH alias: `git@github.com-personal:aliir74/news-summarizer.git`
- Before pushing or creating PRs, switch gh CLI to `aliir74`: `gh auth switch --user aliir74`

## VPS Service (systemd)

Runs on **de-rarecloud** (85.121.124.176) as a systemd service, auto-starting on boot and restarting on crash.

**Code:** `/opt/news-summarizer/` (cloned from `origin/main`)
**Unit:** `/etc/systemd/system/news-summarizer.service`
**State files:** `.env`, `.last_check`, `.seen_urls`, `.bale_retry_queue`, `.cadence_state` — all in `/opt/news-summarizer/`
**Logs:** `journalctl -u news-summarizer`

**Deploy workflow:** push to `origin/main`, then `make deploy` from your local repo.

```bash
# Deploy latest main to VPS (git pull + uv sync + restart)
make deploy

# Service management
make status
make restart
make start
make stop

# Logs
make logs          # last 100 lines
make logs-follow   # tail -f

# SSH into VPS at /opt/news-summarizer/
make ssh

# Sync .env from local to VPS (destructive — 3s abort window)
make push-env

# Download state files to ./state-backup/
make pull-state
```
