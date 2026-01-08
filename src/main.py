"""Main entry point for the news summarizer bot."""

import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import Config, ConfigError
from src.summarizer import Summarizer
from src.telegram_bot import TelegramBot
from src.telegram_reader import TelegramReader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# File for persisting last check timestamp
LAST_CHECK_FILE = Path(".last_check")


class NewsSummarizer:
    """Main application class that coordinates all components."""

    def __init__(self, config: Config) -> None:
        """Initialize the news summarizer with configuration."""
        self.config = config
        self.reader = TelegramReader(config)
        self.bot = TelegramBot(config)
        self.summarizer = Summarizer(config)
        self.scheduler = AsyncIOScheduler()
        self._last_check: datetime | None = None
        self._running = False

    async def start(self) -> None:
        """Start the news summarizer."""
        logger.info("Starting news summarizer...")

        # Load last check timestamp
        self._load_last_check()

        # Start Telegram clients
        await self.reader.start()
        await self.bot.start()

        # Schedule the summarization job
        self.scheduler.add_job(
            self._summarize_job,
            "interval",
            minutes=self.config.summary_interval_minutes,
            id="summarize_news",
            next_run_time=datetime.now(),  # Run immediately on start
        )
        self.scheduler.start()

        self._running = True
        logger.info(
            f"News summarizer started. Running every {self.config.summary_interval_minutes} minutes."
        )
        logger.info(f"Monitoring {len(self.config.channels)} channels.")

    async def stop(self) -> None:
        """Stop the news summarizer."""
        logger.info("Stopping news summarizer...")

        self._running = False
        self.scheduler.shutdown(wait=False)

        # Save last check timestamp
        self._save_last_check()

        # Stop Telegram clients
        await self.reader.stop()
        await self.bot.stop()

        logger.info("News summarizer stopped.")

    async def _summarize_job(self) -> None:
        """Job that fetches news and posts summaries."""
        try:
            # Determine the time window
            since = self._last_check or datetime.now() - timedelta(
                minutes=self.config.summary_interval_minutes
            )

            logger.info(f"Fetching messages since {since}")

            # Fetch messages from all channels
            messages = await self.reader.get_all_channel_updates(since)
            logger.info(f"Found {len(messages)} new messages")

            if messages:
                # Generate summary
                summary = self.summarizer.summarize_news(messages)

                if summary:
                    # Post to channel
                    success = await self.bot.post_summary(summary)
                    if success:
                        logger.info("Summary posted successfully")
                    else:
                        logger.error("Failed to post summary")
                else:
                    logger.warning("Failed to generate summary")
            else:
                logger.info("No new messages to summarize")

            # Update last check timestamp
            self._last_check = datetime.now()
            self._save_last_check()

        except Exception as e:
            logger.error(f"Error in summarization job: {e}", exc_info=True)

    def _load_last_check(self) -> None:
        """Load the last check timestamp from file."""
        if LAST_CHECK_FILE.exists():
            try:
                data = json.loads(LAST_CHECK_FILE.read_text())
                self._last_check = datetime.fromisoformat(data["last_check"])
                logger.info(f"Loaded last check timestamp: {self._last_check}")
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Could not load last check timestamp: {e}")
                self._last_check = None

    def _save_last_check(self) -> None:
        """Save the last check timestamp to file."""
        if self._last_check:
            try:
                LAST_CHECK_FILE.write_text(
                    json.dumps({"last_check": self._last_check.isoformat()})
                )
            except OSError as e:
                logger.warning(f"Could not save last check timestamp: {e}")


async def main() -> None:
    """Main entry point."""
    try:
        config = Config.from_env()
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    if not config.channels:
        logger.warning("No channels configured. Check config/channels.yaml")

    summarizer = NewsSummarizer(config)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Start the summarizer
    await summarizer.start()

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Stop the summarizer
    await summarizer.stop()


if __name__ == "__main__":
    asyncio.run(main())
