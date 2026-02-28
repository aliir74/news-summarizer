"""Tests for the Bale bot module."""

from dataclasses import replace
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.bale_bot import BALE_API_BASE, BaleBot
from src.config import Config
from src.models import Summary


@pytest.fixture
def bale_config(sample_config: Config) -> Config:
    """Create a config with Bale enabled."""
    return replace(
        sample_config,
        bale_bot_token="test_bale_token",
        bale_channel_id="@test_bale_channel",
    )


@pytest.fixture
def bot(bale_config: Config) -> BaleBot:
    """Create a BaleBot instance for testing."""
    return BaleBot(bale_config)


class TestBaleBot:
    """Tests for the BaleBot class."""

    async def test_start_creates_client(self, bot: BaleBot) -> None:
        """Test that start creates an httpx client."""
        await bot.start()
        assert bot._client is not None
        await bot.stop()

    async def test_stop_closes_client(self, bot: BaleBot) -> None:
        """Test that stop closes the httpx client."""
        await bot.start()
        client = bot._client
        assert client is not None
        await bot.stop()

    async def test_stop_without_start(self, bot: BaleBot) -> None:
        """Test stopping without starting does not raise."""
        await bot.stop()

    def test_client_property_not_started(self, bot: BaleBot) -> None:
        """Test accessing client before start raises error."""
        with pytest.raises(RuntimeError, match="not started"):
            _ = bot.client

    async def test_post_summary_success(
        self, bot: BaleBot, sample_summary: Summary
    ) -> None:
        """Test successful summary posting."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        await bot.start()
        with patch.object(bot._client, "post", new_callable=AsyncMock, return_value=mock_response):
            result = await bot.post_summary(sample_summary)

        assert result is True
        await bot.stop()

    async def test_post_summary_failure(
        self, bot: BaleBot, sample_summary: Summary
    ) -> None:
        """Test handling of posting failure."""
        await bot.start()
        with patch.object(
            bot._client,
            "post",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Error", request=MagicMock(), response=MagicMock()
            ),
        ):
            result = await bot.post_summary(sample_summary)

        assert result is False
        await bot.stop()

    async def test_post_summary_correct_url(
        self, bot: BaleBot, bale_config: Config, sample_summary: Summary
    ) -> None:
        """Test that summary is posted to correct Bale API URL."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        await bot.start()
        with patch.object(
            bot._client, "post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            await bot.post_summary(sample_summary)

            expected_url = f"{BALE_API_BASE}{bale_config.bale_bot_token}/sendMessage"
            call_args = mock_post.call_args
            assert call_args[0][0] == expected_url
            assert call_args[1]["json"]["chat_id"] == "@test_bale_channel"

        await bot.stop()

    async def test_post_alert_success(self, bot: BaleBot) -> None:
        """Test successful alert posting."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        await bot.start()
        with patch.object(bot._client, "post", new_callable=AsyncMock, return_value=mock_response):
            result = await bot.post_alert("Test alert")

        assert result is True
        await bot.stop()

    async def test_post_alert_failure(self, bot: BaleBot) -> None:
        """Test handling of alert posting failure."""
        await bot.start()
        with patch.object(
            bot._client,
            "post",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            result = await bot.post_alert("Test alert")

        assert result is False
        await bot.stop()

    async def test_post_long_summary_splits(self, bot: BaleBot) -> None:
        """Test that long summaries are split into multiple messages."""
        long_content = "x" * 5000
        long_summary = Summary(
            content=long_content,
            source_count=10,
            channels=["Channel A"],
            created_at=datetime(2024, 1, 15, 11, 0),
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        await bot.start()
        with patch.object(
            bot._client, "post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            await bot.post_summary(long_summary)

            assert mock_post.call_count > 1

        await bot.stop()
