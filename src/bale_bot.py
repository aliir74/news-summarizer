"""Bale Messenger bot for posting summaries."""

import logging

import httpx

from src.config import Config
from src.message_utils import split_message
from src.models import Summary

logger = logging.getLogger(__name__)

BALE_API_BASE = "https://tapi.bale.ai/bot"


class BaleBot:
    """Posts summaries to a Bale channel using the Bale Bot API."""

    def __init__(self, config: Config) -> None:
        """Initialize the Bale bot with configuration."""
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Start the httpx client."""
        self._client = httpx.AsyncClient(timeout=30.0)
        logger.info("Bale bot client started")

    async def stop(self) -> None:
        """Stop the httpx client."""
        if self._client:
            await self._client.aclose()
            logger.info("Bale bot client stopped")

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the httpx client, raising if not started."""
        if self._client is None:
            raise RuntimeError("BaleBot not started. Call start() first.")
        return self._client

    async def _send_message(self, text: str) -> None:
        """Send a single message to the Bale channel."""
        url = f"{BALE_API_BASE}{self.config.bale_bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.bale_channel_id,
            "text": text,
        }
        response = await self.client.post(url, json=payload)
        response.raise_for_status()

    async def post_summary(self, summary: Summary) -> bool:
        """Post a summary to the Bale channel."""
        formatted = summary.format_message()

        try:
            messages = split_message(formatted)

            for msg in messages:
                await self._send_message(msg)

            logger.info(
                f"Posted summary to Bale with {summary.source_count} sources "
                f"from {len(summary.channels)} channels"
            )
            return True

        except Exception as e:
            logger.error(f"Error posting summary to Bale: {e}")
            return False

    async def post_alert(self, alert_text: str) -> bool:
        """Post an alert message to the Bale channel."""
        try:
            messages = split_message(alert_text)

            for msg in messages:
                await self._send_message(msg)

            logger.info("Posted alert to Bale")
            return True

        except Exception as e:
            logger.error(f"Error posting alert to Bale: {e}")
            return False
