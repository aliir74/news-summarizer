#!/bin/bash
# Wrapper script for launchd to run the news summarizer bot

set -e

cd /Users/aliirani/Downloads/Coding/personal/news-summarizer

# Load environment variables from .env
set -a
source .env
set +a

exec /Users/aliirani/.local/bin/uv run python -m src.main
