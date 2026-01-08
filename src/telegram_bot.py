"""Telegram bot for posting summaries."""

import logging

from pyrogram import Client

from src.config import Config
from src.models import Summary

logger = logging.getLogger(__name__)

# Telegram message limit
MAX_MESSAGE_LENGTH = 4096


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
        formatted = summary.format_for_telegram()

        try:
            # Split message if too long
            messages = self._split_message(formatted)

            for msg in messages:
                await self.client.send_message(
                    chat_id=self.config.output_channel_id,
                    text=msg,
                )

            logger.info(
                f"Posted summary with {summary.source_count} sources "
                f"from {len(summary.channels)} channels"
            )
            return True

        except Exception as e:
            logger.error(f"Error posting summary: {e}")
            return False

    def _split_message(self, text: str) -> list[str]:
        """Split a message into chunks that fit Telegram's limit."""
        if len(text) <= MAX_MESSAGE_LENGTH:
            return [text]

        messages = []
        current = ""

        # Split by paragraphs first
        paragraphs = text.split("\n\n")

        for para in paragraphs:
            # If adding this paragraph exceeds the limit
            if len(current) + len(para) + 2 > MAX_MESSAGE_LENGTH:
                if current:
                    messages.append(current.strip())
                    current = ""

                # If single paragraph is too long, split by sentences
                if len(para) > MAX_MESSAGE_LENGTH:
                    sentences = para.split(". ")
                    for sentence in sentences:
                        if len(current) + len(sentence) + 2 > MAX_MESSAGE_LENGTH:
                            if current:
                                messages.append(current.strip())
                            current = sentence
                        else:
                            current = current + ". " + sentence if current else sentence
                else:
                    current = para
            else:
                current = current + "\n\n" + para if current else para

        if current:
            messages.append(current.strip())

        return messages
