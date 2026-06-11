"""Telegram channel reader using Pyrogram."""

import logging
from datetime import datetime

from pyrogram import Client
from pyrogram.errors import ChannelPrivate, UsernameNotOccupied

from src.config import Config
from src.models import Message

logger = logging.getLogger(__name__)


class TelegramReader:
    """Reads messages from Telegram channels using a user session."""

    def __init__(self, config: Config) -> None:
        """Initialize the Telegram reader with configuration."""
        self.config = config
        self._client: Client | None = None

    async def start(self) -> None:
        """Start the Pyrogram client."""
        self._client = Client(
            name="news_reader",
            api_id=self.config.telegram_api_id,
            api_hash=self.config.telegram_api_hash,
            session_string=self.config.telegram_session_string,
            in_memory=True,
        )
        await self._client.start()
        logger.info("Telegram reader client started")

    async def stop(self) -> None:
        """Stop the Pyrogram client."""
        if self._client:
            await self._client.stop()
            logger.info("Telegram reader client stopped")

    @property
    def client(self) -> Client:
        """Get the Pyrogram client, raising if not started."""
        if self._client is None:
            raise RuntimeError("TelegramReader not started. Call start() first.")
        return self._client

    async def get_recent_messages(
        self, channel: str, since: datetime, limit: int = 100
    ) -> list[Message]:
        """Fetch recent messages from a channel since the given timestamp."""
        messages: list[Message] = []

        try:
            chat = await self.client.get_chat(channel)
            chat_title = getattr(chat, "title", channel)

            # Pyrogram's stub types get_chat_history as a coroutine, but at
            # runtime it is an async generator; the stub is incomplete.
            async for msg in self.client.get_chat_history(  # pyright: ignore[reportGeneralTypeIssues]
                channel, limit=limit
            ):
                # Stop if we've reached messages older than since
                if msg.date and msg.date < since:
                    break

                # Skip messages without text content
                if not msg.text and not msg.caption:
                    continue

                text = str(msg.text or msg.caption or "")

                messages.append(
                    Message(
                        id=msg.id,
                        channel_username=channel,
                        channel_title=str(chat_title),
                        text=text,
                        timestamp=msg.date or datetime.now(),
                    )
                )

        except UsernameNotOccupied:
            logger.warning(f"Channel not found: {channel}")
        except ChannelPrivate:
            logger.warning(f"Cannot access private channel: {channel}")
        except Exception as e:
            logger.error(f"Error fetching messages from {channel}: {e}")

        return messages

    async def get_all_channel_updates(
        self, since: datetime, limit_per_channel: int = 50
    ) -> list[Message]:
        """Fetch recent messages from all configured channels."""
        all_messages: list[Message] = []

        for channel in self.config.channels:
            logger.info(f"Fetching messages from {channel}")
            messages = await self.get_recent_messages(channel, since, limit_per_channel)
            all_messages.extend(messages)
            logger.info(f"Found {len(messages)} new messages from {channel}")

        # Sort by timestamp, newest first
        all_messages.sort(key=lambda m: m.timestamp, reverse=True)

        return all_messages
