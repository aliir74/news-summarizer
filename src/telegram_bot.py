"""Telegram bot for posting summaries."""

import logging

from pyrogram import Client
from pyrogram.enums import ParseMode

from src.config import Config
from src.message_utils import split_message
from src.models import Summary

logger = logging.getLogger(__name__)


class TelegramBot:
    """Posts summaries to a Telegram channel using a bot."""

    def __init__(self, config: Config) -> None:
        """Initialize the Telegram bot with configuration."""
        self.config = config
        self._client: Client | None = None

    async def start(self) -> None:
        """Start the Pyrogram bot client."""
        self._client = Client(
            name="news_bot",
            api_id=self.config.telegram_api_id,
            api_hash=self.config.telegram_api_hash,
            bot_token=self.config.telegram_bot_token,
            in_memory=True,
        )
        await self._client.start()
        logger.info("Telegram bot client started")

    async def stop(self) -> None:
        """Stop the Pyrogram bot client."""
        if self._client:
            await self._client.stop()
            logger.info("Telegram bot client stopped")

    @property
    def client(self) -> Client:
        """Get the Pyrogram client, raising if not started."""
        if self._client is None:
            raise RuntimeError("TelegramBot not started. Call start() first.")
        return self._client

    async def post_summary(self, summary: Summary) -> bool:
        """Post a summary to the output channel."""
        formatted = summary.format_message()

        try:
            # Split message if too long
            messages = split_message(formatted)

            for msg in messages:
                await self.client.send_message(
                    chat_id=self.config.output_channel_id,
                    text=msg,
                    parse_mode=ParseMode.HTML,
                )

            logger.info(
                f"Posted summary with {summary.source_count} sources "
                f"from {len(summary.channels)} channels"
            )
            return True

        except Exception as e:
            logger.error(f"Error posting summary: {e}")
            return False

    async def post_alert(self, alert_text: str) -> bool:
        """Post an alert message to the output channel."""
        try:
            messages = split_message(alert_text)

            for msg in messages:
                await self.client.send_message(
                    chat_id=self.config.output_channel_id,
                    text=msg,
                    parse_mode=ParseMode.HTML,
                )

            logger.info("Posted alert message")
            return True

        except Exception as e:
            logger.error(f"Error posting alert: {e}")
            return False
