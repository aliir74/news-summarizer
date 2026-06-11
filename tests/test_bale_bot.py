"""Tests for the Bale bot module."""

import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.bale_bot import BALE_API_BASE, BALE_QUEUE_MAX_AGE_HOURS, BaleBot
from src.config import Config
from src.models import Summary
from src.summarizer import Summarizer


@pytest.fixture
def bale_config(sample_config: Config) -> Config:
    """Create a config with Bale enabled."""
    return replace(
        sample_config,
        bale_bot_token="test_bale_token",
        bale_channel_id="@test_bale_channel",
    )


@pytest.fixture
def mock_summarizer(bale_config: Config) -> MagicMock:
    """Create a mock Summarizer."""
    summarizer = MagicMock(spec=Summarizer)
    summarizer.re_summarize = MagicMock(return_value="re-summarized text")
    return summarizer


@pytest.fixture
def bot(bale_config: Config, mock_summarizer: MagicMock) -> BaleBot:
    """Create a BaleBot instance for testing."""
    return BaleBot(bale_config, mock_summarizer)


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

    async def test_send_message_no_parse_mode(
        self, bot: BaleBot
    ) -> None:
        """Test that _send_message does not include parse_mode (Bale ignores it)."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        await bot.start()
        with patch.object(
            bot._client, "post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            await bot._send_message("test message")

            call_args = mock_post.call_args
            assert "parse_mode" not in call_args[1]["json"]

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


class TestBaleBotRetryQueue:
    """Tests for the BaleBot retry queue."""

    async def test_enqueue_on_post_summary_failure(
        self, bot: BaleBot, sample_summary: Summary, tmp_path: MagicMock
    ) -> None:
        """Test that failed post_summary enqueues the message."""
        queue_file = tmp_path / "bale_retry_queue"
        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            with patch.object(
                bot._client,
                "post",
                new_callable=AsyncMock,
                side_effect=Exception("Network error"),
            ):
                await bot.post_summary(sample_summary)

            assert len(bot._queue) == 1
            assert queue_file.exists()
            await bot.stop()

    async def test_no_enqueue_on_post_alert_failure(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test a failed post_alert is dropped, never queued for retry.

        Alerts (radar outages, cadence notices) are time-sensitive: delivering
        them late is misleading, and queueing them would pollute the summary
        retry queue's re_summarize condensation.
        """
        queue_file = tmp_path / "bale_retry_queue"
        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            with patch.object(
                bot._client,
                "post",
                new_callable=AsyncMock,
                side_effect=Exception("Network error"),
            ):
                result = await bot.post_alert("Test alert")

            assert result is False
            assert len(bot._queue) == 0
            await bot.stop()

    async def test_no_enqueue_on_success(
        self, bot: BaleBot, sample_summary: Summary, tmp_path: MagicMock
    ) -> None:
        """Test that successful post does not enqueue."""
        queue_file = tmp_path / "bale_retry_queue"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            with patch.object(
                bot._client, "post", new_callable=AsyncMock, return_value=mock_response
            ):
                await bot.post_summary(sample_summary)

            assert len(bot._queue) == 0
            await bot.stop()

    async def test_load_queue_on_start(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that queue is loaded from disk on start."""
        queue_file = tmp_path / "bale_retry_queue"
        queue_data = {
            "items": [
                {"text": "queued message", "queued_at": datetime.now().isoformat()}
            ]
        }
        queue_file.write_text(json.dumps(queue_data))

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            assert len(bot._queue) == 1
            assert bot._queue[0]["text"] == "queued message"
            await bot.stop()

    async def test_load_queue_missing_file(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that missing queue file is handled gracefully."""
        queue_file = tmp_path / "nonexistent_queue"
        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            assert len(bot._queue) == 0
            await bot.stop()

    async def test_load_queue_corrupted_file(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that corrupted queue file is handled gracefully."""
        queue_file = tmp_path / "bale_retry_queue"
        queue_file.write_text("not valid json{{{")

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            assert len(bot._queue) == 0
            await bot.stop()

    def test_prune_expired_items(self, bot: BaleBot) -> None:
        """Test that items older than max age are pruned."""
        old_time = (
            datetime.now() - timedelta(hours=BALE_QUEUE_MAX_AGE_HOURS + 1)
        ).isoformat()
        bot._queue = [
            {"text": "old message", "queued_at": old_time},
            {"text": "recent message", "queued_at": datetime.now().isoformat()},
        ]

        removed = bot._prune_expired()

        assert removed == 1
        assert len(bot._queue) == 1
        assert bot._queue[0]["text"] == "recent message"

    def test_prune_keeps_recent_items(self, bot: BaleBot) -> None:
        """Test that recent items are not pruned."""
        recent_time = datetime.now().isoformat()
        bot._queue = [
            {"text": "msg1", "queued_at": recent_time},
            {"text": "msg2", "queued_at": recent_time},
        ]

        removed = bot._prune_expired()

        assert removed == 0
        assert len(bot._queue) == 2

    async def test_flush_queue_success(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that successful flush clears the queue."""
        queue_file = tmp_path / "bale_retry_queue"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            bot._queue = [
                {"text": "queued msg", "queued_at": datetime.now().isoformat()}
            ]

            with (
                patch.object(
                    bot, "_is_healthy", new_callable=AsyncMock, return_value=True
                ),
                patch.object(
                    bot._client, "post", new_callable=AsyncMock,
                    return_value=mock_response
                ),
            ):
                result = await bot._flush_queue()

            assert result is True
            assert len(bot._queue) == 0
            await bot.stop()

    async def test_flush_queue_failure_keeps_items(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that failed flush keeps items in queue."""
        queue_file = tmp_path / "bale_retry_queue"
        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            bot._queue = [
                {"text": "queued msg", "queued_at": datetime.now().isoformat()}
            ]

            with (
                patch.object(
                    bot, "_is_healthy", new_callable=AsyncMock, return_value=True
                ),
                patch.object(
                    bot._client, "post", new_callable=AsyncMock,
                    side_effect=Exception("still down"),
                ),
            ):
                result = await bot._flush_queue()

            assert result is False
            assert len(bot._queue) == 1
            await bot.stop()

    async def test_flush_empty_queue(self, bot: BaleBot) -> None:
        """Test that flushing an empty queue returns True without sending."""
        await bot.start()
        bot._queue = []

        with patch.object(bot, "_send_message", new_callable=AsyncMock) as mock_send:
            result = await bot._flush_queue()

        assert result is True
        mock_send.assert_not_called()
        await bot.stop()

    async def test_flush_re_summarizes_multiple(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that multiple queued items are re-summarized."""
        queue_file = tmp_path / "bale_retry_queue"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            now = datetime.now().isoformat()
            bot._queue = [
                {"text": "summary 1", "queued_at": now},
                {"text": "summary 2", "queued_at": now},
            ]

            with (
                patch.object(
                    bot, "_is_healthy", new_callable=AsyncMock, return_value=True
                ),
                patch.object(
                    bot._client, "post", new_callable=AsyncMock,
                    return_value=mock_response
                ),
            ):
                await bot._flush_queue()

            bot._summarizer.re_summarize.assert_called_once_with(
                ["summary 1", "summary 2"]
            )
            await bot.stop()

    async def test_flush_single_item_no_re_summarize(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that a single queued item is sent as-is without LLM call."""
        queue_file = tmp_path / "bale_retry_queue"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            bot._queue = [
                {"text": "only one", "queued_at": datetime.now().isoformat()}
            ]

            with (
                patch.object(
                    bot, "_is_healthy", new_callable=AsyncMock, return_value=True
                ),
                patch.object(
                    bot._client, "post", new_callable=AsyncMock,
                    return_value=mock_response
                ),
            ):
                await bot._flush_queue()

            bot._summarizer.re_summarize.assert_not_called()
            await bot.stop()

    async def test_flush_re_summarize_fallback(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that LLM failure falls back to most recent item."""
        queue_file = tmp_path / "bale_retry_queue"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        bot._summarizer.re_summarize = MagicMock(return_value=None)

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            now = datetime.now().isoformat()
            bot._queue = [
                {"text": "older", "queued_at": now},
                {"text": "newest", "queued_at": now},
            ]

            with (
                patch.object(
                    bot, "_is_healthy", new_callable=AsyncMock, return_value=True
                ),
                patch.object(
                    bot._client, "post", new_callable=AsyncMock,
                    return_value=mock_response
                ) as mock_post,
            ):
                await bot._flush_queue()

            # Should have sent the most recent (last) item
            sent_text = mock_post.call_args[1]["json"]["text"]
            assert sent_text == "newest"
            await bot.stop()

    async def test_flush_skips_when_bale_unhealthy(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that flush skips LLM call when Bale health check fails."""
        queue_file = tmp_path / "bale_retry_queue"
        mock_response = MagicMock()
        mock_response.is_success = False

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            now = datetime.now().isoformat()
            bot._queue = [
                {"text": "summary 1", "queued_at": now},
                {"text": "summary 2", "queued_at": now},
            ]

            with patch.object(
                bot._client, "get", new_callable=AsyncMock, return_value=mock_response
            ):
                result = await bot._flush_queue()

            assert result is False
            assert len(bot._queue) == 2
            bot._summarizer.re_summarize.assert_not_called()
            await bot.stop()

    async def test_flush_proceeds_when_bale_healthy(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that flush proceeds normally when Bale health check passes."""
        queue_file = tmp_path / "bale_retry_queue"
        healthy_response = MagicMock()
        healthy_response.is_success = True
        send_response = MagicMock()
        send_response.raise_for_status = MagicMock()

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            now = datetime.now().isoformat()
            bot._queue = [
                {"text": "summary 1", "queued_at": now},
                {"text": "summary 2", "queued_at": now},
            ]

            with (
                patch.object(
                    bot._client, "get", new_callable=AsyncMock,
                    return_value=healthy_response
                ),
                patch.object(
                    bot._client, "post", new_callable=AsyncMock,
                    return_value=send_response
                ),
            ):
                result = await bot._flush_queue()

            assert result is True
            bot._summarizer.re_summarize.assert_called_once()
            await bot.stop()

    async def test_retry_loop_starts_and_stops(self, bot: BaleBot) -> None:
        """Test that start creates retry task and stop cancels it."""
        await bot.start()
        assert bot._retry_task is not None
        assert not bot._retry_task.done()

        await bot.stop()
        assert bot._retry_task.done()

    async def test_save_queue_on_stop(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that queue is saved when bot stops."""
        queue_file = tmp_path / "bale_retry_queue"
        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            bot._queue = [
                {"text": "persist me", "queued_at": datetime.now().isoformat()}
            ]
            await bot.stop()

            saved = json.loads(queue_file.read_text())
            assert len(saved["items"]) == 1
            assert saved["items"][0]["text"] == "persist me"

    async def test_persian_text_persistence(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that Persian content survives save/load cycle."""
        queue_file = tmp_path / "bale_retry_queue"
        persian_text = "این یک خلاصه خبری فارسی است"

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            bot._queue = [
                {"text": persian_text, "queued_at": datetime.now().isoformat()}
            ]
            bot._save_queue()

            bot._queue = []
            bot._load_queue()

            assert len(bot._queue) == 1
            assert bot._queue[0]["text"] == persian_text

    async def test_flush_concurrency_safety(
        self, bot: BaleBot, tmp_path: MagicMock
    ) -> None:
        """Test that items added during flush survive."""
        queue_file = tmp_path / "bale_retry_queue"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("src.bale_bot.BALE_QUEUE_FILE", queue_file):
            await bot.start()
            now = datetime.now().isoformat()
            bot._queue = [{"text": "original", "queued_at": now}]

            original_send = AsyncMock(return_value=mock_response)

            async def send_and_add(*args: object, **kwargs: object) -> MagicMock:
                """Simulate a new item arriving during flush."""
                bot._queue.append({"text": "added during flush", "queued_at": now})
                return await original_send(*args, **kwargs)

            with (
                patch.object(
                    bot, "_is_healthy", new_callable=AsyncMock, return_value=True
                ),
                patch.object(
                    bot._client, "post", new_callable=lambda: send_and_add
                ),
            ):
                await bot._flush_queue()

            # The item added during flush should survive
            assert len(bot._queue) == 1
            assert bot._queue[0]["text"] == "added during flush"
            await bot.stop()


class TestBaleBotCoverage:
    """Tests for Bale error paths and the retry loop body (coverage)."""

    async def test_save_queue_handles_os_error(
        self, bot: BaleBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An OSError while saving the retry queue is swallowed with a warning."""
        fake_path = MagicMock()
        fake_path.write_text.side_effect = OSError("disk full")
        monkeypatch.setattr("src.bale_bot.BALE_QUEUE_FILE", fake_path)

        bot._queue = [{"text": "x", "queued_at": datetime.now().isoformat()}]
        bot._save_queue()  # Should not raise.

        fake_path.write_text.assert_called_once()

    async def test_is_healthy_returns_false_on_exception(self, bot: BaleBot) -> None:
        """A network error during the health check reports unhealthy."""
        await bot.start()
        with patch.object(
            bot._client, "get", new_callable=AsyncMock, side_effect=httpx.HTTPError("down")
        ):
            healthy = await bot._is_healthy()
        await bot.stop()

        assert healthy is False

    async def test_retry_loop_flushes_when_queue_nonempty(self, bot: BaleBot) -> None:
        """The retry loop sleeps, then flushes a non-empty queue each tick."""
        bot._queue = [{"text": "x", "queued_at": datetime.now().isoformat()}]

        with (
            patch(
                "src.bale_bot.asyncio.sleep",
                new_callable=AsyncMock,
                side_effect=[None, asyncio.CancelledError()],
            ),
            patch.object(bot, "_flush_queue", new_callable=AsyncMock) as mock_flush,
        ):
            with pytest.raises(asyncio.CancelledError):
                await bot._retry_loop()

        mock_flush.assert_awaited_once()
