"""Tests for the composite output writer."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.composite_writer import CompositeOutputWriter
from src.models import Summary


def _make_writer(
    post_summary_return: bool = True,
    post_alert_return: bool = True,
    post_summary_side_effect: Exception | None = None,
    post_alert_side_effect: Exception | None = None,
) -> MagicMock:
    """Create a mock OutputWriter."""
    writer = MagicMock()
    writer.start = AsyncMock()
    writer.stop = AsyncMock()
    writer.post_summary = AsyncMock(
        return_value=post_summary_return, side_effect=post_summary_side_effect
    )
    writer.post_alert = AsyncMock(
        return_value=post_alert_return, side_effect=post_alert_side_effect
    )
    return writer


class TestCompositeOutputWriter:
    """Tests for the CompositeOutputWriter class."""

    def test_empty_writers_raises(self) -> None:
        """Test that empty writers list raises ValueError."""
        with pytest.raises(ValueError, match="at least one writer"):
            CompositeOutputWriter([])

    async def test_start_calls_all_writers(self) -> None:
        """Test that start calls start on all writers."""
        w1 = _make_writer()
        w2 = _make_writer()
        composite = CompositeOutputWriter([w1, w2])

        await composite.start()

        w1.start.assert_called_once()
        w2.start.assert_called_once()

    async def test_stop_calls_all_writers(self) -> None:
        """Test that stop calls stop on all writers."""
        w1 = _make_writer()
        w2 = _make_writer()
        composite = CompositeOutputWriter([w1, w2])

        await composite.stop()

        w1.stop.assert_called_once()
        w2.stop.assert_called_once()

    async def test_post_summary_all_succeed(self, sample_summary: Summary) -> None:
        """Test post_summary returns True when all writers succeed."""
        w1 = _make_writer()
        w2 = _make_writer()
        composite = CompositeOutputWriter([w1, w2])

        result = await composite.post_summary(sample_summary)

        assert result is True
        w1.post_summary.assert_called_once_with(sample_summary)
        w2.post_summary.assert_called_once_with(sample_summary)

    async def test_post_summary_partial_fail(self, sample_summary: Summary) -> None:
        """Test post_summary returns True when at least one writer succeeds."""
        w1 = _make_writer(post_summary_return=True)
        w2 = _make_writer(post_summary_return=False)
        composite = CompositeOutputWriter([w1, w2])

        result = await composite.post_summary(sample_summary)

        assert result is True

    async def test_post_summary_all_fail(self, sample_summary: Summary) -> None:
        """Test post_summary returns False when all writers fail."""
        w1 = _make_writer(post_summary_return=False)
        w2 = _make_writer(post_summary_return=False)
        composite = CompositeOutputWriter([w1, w2])

        result = await composite.post_summary(sample_summary)

        assert result is False

    async def test_post_summary_exception_handled(self, sample_summary: Summary) -> None:
        """Test post_summary handles exceptions from writers gracefully."""
        w1 = _make_writer(post_summary_side_effect=Exception("boom"))
        w2 = _make_writer(post_summary_return=True)
        composite = CompositeOutputWriter([w1, w2])

        result = await composite.post_summary(sample_summary)

        assert result is True

    async def test_post_summary_all_raise(self, sample_summary: Summary) -> None:
        """Test post_summary returns False when all writers raise."""
        w1 = _make_writer(post_summary_side_effect=Exception("boom"))
        w2 = _make_writer(post_summary_side_effect=Exception("crash"))
        composite = CompositeOutputWriter([w1, w2])

        result = await composite.post_summary(sample_summary)

        assert result is False

    async def test_post_alert_all_succeed(self) -> None:
        """Test post_alert returns True when all writers succeed."""
        w1 = _make_writer()
        w2 = _make_writer()
        composite = CompositeOutputWriter([w1, w2])

        result = await composite.post_alert("Test alert")

        assert result is True

    async def test_post_alert_partial_fail(self) -> None:
        """Test post_alert returns True when at least one writer succeeds."""
        w1 = _make_writer(post_alert_return=True)
        w2 = _make_writer(post_alert_return=False)
        composite = CompositeOutputWriter([w1, w2])

        result = await composite.post_alert("Test alert")

        assert result is True

    async def test_post_alert_all_fail(self) -> None:
        """Test post_alert returns False when all writers fail."""
        w1 = _make_writer(post_alert_return=False)
        w2 = _make_writer(post_alert_return=False)
        composite = CompositeOutputWriter([w1, w2])

        result = await composite.post_alert("Test alert")

        assert result is False

    async def test_post_alert_exception_handled(self) -> None:
        """Test post_alert handles exceptions from writers gracefully."""
        w1 = _make_writer(post_alert_side_effect=Exception("boom"))
        w2 = _make_writer(post_alert_return=True)
        composite = CompositeOutputWriter([w1, w2])

        result = await composite.post_alert("Test alert")

        assert result is True
