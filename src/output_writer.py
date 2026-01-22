"""Protocol for output writers."""

from typing import Protocol

from src.models import Summary


class OutputWriter(Protocol):
    """Protocol defining the interface for output writers.

    Both TelegramBot and FileWriter implement this protocol,
    allowing them to be used interchangeably.
    """

    async def start(self) -> None:
        """Start the output writer."""
        ...

    async def stop(self) -> None:
        """Stop the output writer."""
        ...

    async def post_summary(self, summary: Summary) -> bool:
        """Post a summary and return success status."""
        ...

    async def post_alert(self, alert_text: str) -> bool:
        """Post an alert message and return success status."""
        ...
