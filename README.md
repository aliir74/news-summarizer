# Telegram Persian News Summarizer Bot

[![GitHub Sponsors](https://img.shields.io/badge/sponsor-30363D?style=for-the-badge&logo=GitHub-Sponsors&logoColor=#EA4AAA)](https://github.com/sponsors/aliir74)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/aliir74)

A Python application that monitors Persian news Telegram channels, summarizes new posts using AI (OpenRouter LLM), and posts the summaries to your own Telegram channel.

## Features

- Monitors multiple Telegram news channels using your user account
- Monitors RSS feeds with keyword-based filtering for Iran-related news
- Generates Persian summaries using OpenRouter LLM API
- Posts summaries to a dedicated Telegram channel via bot
- Configurable check interval (default: 30 minutes)
- Persists last check timestamp to avoid duplicate summaries on restart
- **Test mode** for local development (writes to file, separate state)
- Runs locally as a macOS LaunchAgent (auto-start, auto-restart)

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Telegram API credentials
- Telegram Bot token
- OpenRouter API key

## Setup

### 1. Clone and Install

```bash
git clone <repository-url>
cd news-summarizer
uv sync --all-extras
```

### 2. Get Telegram API Credentials

1. Go to [https://my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Go to "API development tools"
4. Create a new application
5. Copy your `API_ID` and `API_HASH`

### 3. Create a Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token provided
4. Add your bot as an admin to your output channel

### 4. Get OpenRouter API Key

1. Create an account at [https://openrouter.ai](https://openrouter.ai)
2. Go to API Keys section
3. Create a new API key

### 5. Generate Telegram Session String

Run the session generator script locally (one-time setup):

```bash
uv run python scripts/generate_session.py
```

You'll be prompted for:
- Your API ID and API Hash
- Your phone number
- The verification code sent to Telegram
- Your 2FA password (if enabled)

Save the output session string securely.

### 6. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION_STRING=your_session_string
TELEGRAM_BOT_TOKEN=your_bot_token
OUTPUT_CHANNEL_ID=@your_channel
OPENROUTER_API_KEY=your_openrouter_key
SUMMARY_INTERVAL_MINUTES=30
LLM_MODEL=google/gemini-2.5-flash-lite
```

See [docs/llm-comparison.md](docs/llm-comparison.md) for model options and pricing.

### 7. Configure Channels

Edit `config/channels.yaml` to add the channels you want to monitor:

```yaml
channels:
  - channel_username_1
  - channel_username_2
  - channel_username_3
```

Note: Your Telegram account must be able to view these channels (public channels or channels you've joined).

### 8. (Optional) Reflective Adaptive Cadence

By default the bot summarizes on a flat interval (`SUMMARY_INTERVAL_MINUTES`). You can make it reactive instead: it measures news intensity each run as a pre-dedup filtered message rate (messages per minute, so the signal does not depend on the current interval) and adapts the cadence:

- **Escalation is immediate.** When the rate spikes above the baseline (a war breaks out, a major event) or a Cloudflare Radar internet outage fires, the interval shortens at once, down to `min_interval_minutes` at a full surge.
- **Two-gate level test.** A level requires BOTH a ratio (rate vs the rolling median baseline) AND an absolute message-rate floor. The floor stops ordinary traffic (a few messages over the window) from clearing the 4x ratio against a near-zero baseline and reading as a false surge.
- **Decay is silent and steps back in meaningful jumps.** As things calm, the interval grows by `decay_factor` (default 2.0, i.e. doubling: 30→60→120→240→360) per decay step, never overshooting `SUMMARY_INTERVAL_MINUTES` (the steady-state baseline) unless you set `max_interval_minutes` higher.
- **Notices only on a genuine surge onset.** A one-line Persian notice is posted only when the cadence tightens out of a calm NORMAL state. Decay and mid-event re-escalation reschedule silently, so the channel is never spammed with contradictory "calming"/"rising" notices.
- **Optional cold-start probe.** With `fast_escalation: true`, a cheap probe runs every `probe_interval_minutes`, counting messages with no LLM call, and can tighten the cadence between full summary runs. It can only escalate, never relax.

Enable it in `config/channels.yaml`:

```yaml
adaptive_cadence:
  enabled: true
  min_interval_minutes: 5    # Floor cadence during a surge
  # max_interval_minutes: 60 # Optional; omit to cap at the baseline
  baseline_window: 10        # Recent rate samples for the median baseline
  elevated_ratio: 2.0        # >= 2x baseline => half interval (also needs elevated_floor_rate)
  surge_ratio: 4.0           # >= 4x baseline => min_interval (also needs surge_floor_rate)
  elevated_floor_rate: 0.75  # Absolute min rate (msg/min) to reach ELEVATED
  surge_floor_rate: 1.5      # Absolute min rate (msg/min) to reach SURGE
  decay_factor: 2.0          # Interval growth per decay step (doubling: 30->60->120)
  min_baseline_rate: 0.1     # Baseline floor, in messages per minute
  fast_escalation: false     # Cheap escalate-only probe between runs
  probe_interval_minutes: 5
```

Cadence state (the rate window and current interval) is persisted to `.cadence_state` so it survives restarts.

## Running Locally

```bash
uv run python -m src.main
```

The bot will:
1. Start monitoring the configured channels
2. Check for new messages at the configured interval
3. Generate and post summaries to your output channel

Press `Ctrl+C` to stop gracefully.

### Test Mode

Test mode allows you to run the application locally without posting to Telegram. Instead, summaries are written to a text file and state is tracked separately from production.

```bash
# Run in test mode (writes to output/summaries.txt)
TEST_MODE=true uv run python -m src.main

# Customize test interval (default: 5 minutes)
TEST_MODE=true TEST_SUMMARY_INTERVAL_MINUTES=1 uv run python -m src.main
```

Test mode features:
- Writes summaries to `output/summaries.txt` instead of Telegram
- Uses separate state file (`.last_check.test`) to keep test runs isolated
- Uses `config/channels.test.yaml` if it exists (falls back to `channels.yaml`)
- Shorter default interval (5 minutes vs 30 minutes)

Test mode environment variables:
| Variable | Default | Description |
|----------|---------|-------------|
| `TEST_MODE` | `false` | Enable test mode |
| `TEST_SUMMARY_INTERVAL_MINUTES` | `5` | Summary interval in test mode |
| `TEST_OUTPUT_DIR` | `output` | Directory for file output |
| `TEST_STATE_FILE` | `.last_check.test` | State file path in test mode |

## Development

### Running Tests

```bash
uv run pytest
```

With coverage:

```bash
uv run pytest --cov=src --cov-report=term-missing
```

### Linting

```bash
uv run ruff check src tests
```

### Type Checking

```bash
uv run pyright src
```

## Project Structure

```
news-summarizer/
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point, scheduler setup
│   ├── config.py            # Configuration loading
│   ├── telegram_reader.py   # Pyrogram client for reading channels
│   ├── rss_reader.py        # RSS/Atom feed reader
│   ├── iran_filter.py       # Keyword-based content filtering
│   ├── telegram_bot.py      # Bot for posting summaries
│   ├── file_writer.py       # File output for test mode
│   ├── output_writer.py     # Output writer protocol
│   ├── summarizer.py        # OpenRouter LLM integration
│   └── models.py            # Data models (Message, Summary)
├── tests/                   # Test suite
├── scripts/
│   └── generate_session.py  # Session string generator
├── config/
│   ├── channels.yaml        # Production channel list
│   └── channels.test.yaml   # Test mode channel list
├── .github/workflows/       # CI workflow
├── pyproject.toml          # Project configuration
```

## Security Notes

- **Never commit** your `.env` file or session string to git
- The session string grants full access to your Telegram account
- If you suspect your session is compromised, terminate all sessions in Telegram settings
- Store credentials securely in your `.env` file

## Support This Project

If you find this bot useful, consider supporting its development:

- Star this repo
- Report bugs and submit PRs
- [Sponsor on GitHub](https://github.com/sponsors/aliir74) or [Buy me a coffee](https://www.buymeacoffee.com/aliir74)

## License

MIT
