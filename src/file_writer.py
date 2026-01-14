"""File writer for outputting summaries to text files (test mode)."""

import logging
from datetime import datetime

from src.config import Config
from src.models import Summary

logger = logging.getLogger(__name__)


class FileWriter:
    """Writes summaries to a text file instead of Telegram (for test mode)."""

    def __init__(self, config: Config) -> None:
        """Initialize the file writer with configuration."""
        self.config = config
        self._output_dir = config.test_output_dir
        self._output_file = self._output_dir / "summaries.txt"

    async def start(self) -> None:
        """Initialize the file writer (create output directory if needed)."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileWriter initialized, output to: {self._output_file}")

    async def stop(self) -> None:
        """Stop the file writer (no-op for files)."""
        logger.info("FileWriter stopped")

    async def post_summary(self, summary: Summary) -> bool:
        """Write a summary to the output file."""
        formatted = summary.format_for_telegram()

        try:
            # Append to file with separator
            with open(self._output_file, "a", encoding="utf-8") as f:
                f.write("=" * 60 + "\n")
                f.write(f"Written at: {datetime.now().isoformat()}\n")
                f.write("=" * 60 + "\n")
                f.write(formatted)
                f.write("\n\n")

            logger.info(
                f"Wrote summary with {summary.source_count} sources "
                f"from {len(summary.channels)} channels to {self._output_file}"
            )
            return True

        except OSError as e:
            logger.error(f"Error writing summary to file: {e}")
            return False
