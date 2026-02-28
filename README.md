# Telegram Persian News Summarizer Bot

A Python application that monitors Persian news Telegram channels, summarizes new posts using AI (OpenRouter LLM), and posts the summaries to your own Telegram channel.

## Features

- Monitors multiple Telegram news channels using your user account
- Monitors RSS feeds with keyword-based filtering for Iran-related news
- Generates Persian summaries using OpenRouter LLM API
- Posts summaries to a dedicated Telegram channel via bot
- Configurable check interval (default: 30 minutes)
- Persists last check timestamp to avoid duplicate summaries on restart
- **Test mode** for local development (writes to file, separate state)
- Deployable to Railway (free tier)

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

Save the output session string securely - you'll need it for deployment.

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
LLM_MODEL=google/gemma-2-9b-it
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

## Deployment to Railway

### 1. Create Railway Project

1. Go to [https://railway.app](https://railway.app)
2. Create a new project
3. Connect your GitHub repository

### 2. Configure Environment Variables

In Railway dashboard, add these environment variables:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `TELEGRAM_BOT_TOKEN`
- `OUTPUT_CHANNEL_ID`
- `OPENROUTER_API_KEY`
- `SUMMARY_INTERVAL_MINUTES` (optional, default: 30)
- `LLM_MODEL` (optional, default: google/gemma-2-9b-it)

### 3. Deploy

Railway will automatically deploy when you push to the main branch.

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
├── .github/workflows/       # CI/CD workflows
├── pyproject.toml          # Project configuration
└── railway.toml            # Railway deployment config
```

## Security Notes

- **Never commit** your `.env` file or session string to git
- The session string grants full access to your Telegram account
- If you suspect your session is compromised, terminate all sessions in Telegram settings
- Store credentials securely in your deployment environment

## License

MIT
