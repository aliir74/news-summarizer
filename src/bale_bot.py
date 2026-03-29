"""Bale Messenger bot for posting summaries."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from src.config import Config
from src.message_utils import split_message
from src.models import Summary
from src.summarizer import Summarizer

logger = logging.getLogger(__name__)

BALE_API_BASE = "https://tapi.bale.ai/bot"
BALE_QUEUE_FILE = Path(".bale_retry_queue")
BALE_RETRY_INTERVAL_SECONDS = 300
BALE_QUEUE_MAX_AGE_HOURS = 24


class BaleBot:
    """Posts summaries to a Bale channel using the Bale Bot API."""

    def __init__(self, config: Config, summarizer: Summarizer) -> None:
        """Initialize the Bale bot with configuration."""
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._queue: list[dict[str, str]] = []
        self._retry_task: asyncio.Task[None] | None = None
        self._summarizer = summarizer

    async def start(self) -> None:
        """Start the httpx client and retry loop."""
        self._client = httpx.AsyncClient(timeout=30.0)
        self._load_queue()
        self._retry_task = asyncio.create_task(self._retry_loop())
        logger.info("Bale bot client started")

    async def stop(self) -> None:
        """Stop the retry loop and httpx client."""
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
        self._save_queue()
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
            "parse_mode": "HTML",
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
            self._enqueue(formatted)
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
            self._enqueue(alert_text)
            return False

    def _enqueue(self, text: str) -> None:
        """Add a message to the retry queue."""
        self._queue.append({
            "text": text,
            "queued_at": datetime.now().isoformat(),
        })
        self._save_queue()
        logger.info(f"Queued message for retry (queue size: {len(self._queue)})")

    def _prune_expired(self) -> int:
        """Remove items older than the max age. Return count removed."""
        cutoff = datetime.now() - timedelta(hours=BALE_QUEUE_MAX_AGE_HOURS)
        original_len = len(self._queue)
        self._queue = [
            item for item in self._queue
            if datetime.fromisoformat(item["queued_at"]) > cutoff
        ]
        removed = original_len - len(self._queue)
        if removed > 0:
            logger.info(f"Pruned {removed} expired items from Bale retry queue")
        return removed

    def _load_queue(self) -> None:
        """Load the retry queue from disk."""
        if BALE_QUEUE_FILE.exists():
            try:
                data = json.loads(BALE_QUEUE_FILE.read_text())
                self._queue = data.get("items", [])
                self._prune_expired()
                logger.info(f"Loaded {len(self._queue)} items from Bale retry queue")
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Could not load Bale retry queue: {e}")
                self._queue = []
        else:
            self._queue = []

    def _save_queue(self) -> None:
        """Save the retry queue to disk."""
        try:
            BALE_QUEUE_FILE.write_text(
                json.dumps({"items": self._queue}, ensure_ascii=False)
            )
        except OSError as e:
            logger.warning(f"Could not save Bale retry queue: {e}")

    async def _flush_queue(self) -> bool:
        """Attempt to send all queued messages. Returns True on success."""
        self._prune_expired()

        if not self._queue:
            return True

        items_to_flush = list(self._queue)
        texts = [item["text"] for item in items_to_flush]

        if len(texts) == 1:
            text_to_send = texts[0]
        else:
            re_summarized = self._summarizer.re_summarize(texts)
            text_to_send = re_summarized if re_summarized else texts[-1]

        try:
            messages = split_message(text_to_send)
            for msg in messages:
                await self._send_message(msg)

            self._queue = self._queue[len(items_to_flush):]
            self._save_queue()
            logger.info(f"Flushed {len(items_to_flush)} queued messages to Bale")
            return True

        except Exception as e:
            logger.error(f"Failed to flush Bale retry queue: {e}")
            return False

    async def _retry_loop(self) -> None:
        """Background loop that retries queued messages."""
        while True:
            await asyncio.sleep(BALE_RETRY_INTERVAL_SECONDS)
            if self._queue:
                await self._flush_queue()
