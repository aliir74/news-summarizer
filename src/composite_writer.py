"""Composite output writer that fans out to multiple writers."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from src.models import Summary
from src.output_writer import OutputWriter

logger = logging.getLogger(__name__)


class CompositeOutputWriter:
    """Wraps multiple OutputWriters, calling all of them concurrently.

    Returns True if at least one writer succeeds (partial success = success).
    """

    def __init__(self, writers: list[OutputWriter]) -> None:
        """Initialize with a list of output writers."""
        if not writers:
            raise ValueError("CompositeOutputWriter requires at least one writer")
        self._writers = writers

    async def start(self) -> None:
        """Start all output writers."""
        for writer in self._writers:
            await writer.start()

    async def stop(self) -> None:
        """Stop all output writers, even if some raise."""
        results = await asyncio.gather(
            *[w.stop() for w in self._writers],
            return_exceptions=True,
        )
        for writer, result in zip(self._writers, results, strict=True):
            if isinstance(result, Exception):
                logger.warning(f"Writer {type(writer).__name__} failed to stop: {result}")

    async def _fan_out(
        self,
        action: Callable[[OutputWriter], Awaitable[bool]],
        label: str,
    ) -> bool:
        """Run an action on all writers concurrently. Returns True if any succeed."""
        results = await asyncio.gather(
            *[action(w) for w in self._writers],
            return_exceptions=True,
        )
        any_success = False
        for writer, result in zip(self._writers, results, strict=True):
            if isinstance(result, Exception):
                logger.warning(f"Writer {type(writer).__name__} raised error: {result}")
            elif result:
                any_success = True
            else:
                logger.warning(f"Writer {type(writer).__name__} failed to {label}")
        return any_success

    async def post_summary(self, summary: Summary) -> bool:
        """Post summary to all writers concurrently. Returns True if any succeed."""
        return await self._fan_out(lambda w: w.post_summary(summary), "post summary")

    async def post_alert(self, alert_text: str) -> bool:
        """Post alert to all writers concurrently. Returns True if any succeed."""
        return await self._fan_out(lambda w: w.post_alert(alert_text), "post alert")
