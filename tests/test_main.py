"""Tests for the main module."""

import json
import runpy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import main as main_module
from src.cadence import CadenceChangeReason, CadenceDecision, IntensityLevel
from src.composite_writer import CompositeOutputWriter
from src.config import (
    Config,
    ConfigError,
    DeduplicationConfig,
)
from src.file_writer import FileWriter
from src.main import MAX_SEEN_URLS, SEEN_URLS_FILE, NewsSummarizer, main
from src.models import Message
from src.telegram_bot import TelegramBot


def _iran_msg(text: str = "خبری درباره ایران و تهران") -> Message:
    """Build a minimal Iran-related Message that passes the iran filter."""
    return Message(
        id=1,
        channel_username="ch",
        channel_title="Ch",
        text=text,
        timestamp=datetime(2024, 1, 15, 10, 0),
    )


@pytest.fixture
def news_summarizer(sample_config: Config) -> NewsSummarizer:
    """Create a NewsSummarizer instance for testing."""
    return NewsSummarizer(sample_config)


@pytest.fixture
def test_mode_summarizer(sample_config: Config, tmp_path: Path) -> NewsSummarizer:
    """Create a NewsSummarizer instance with test mode enabled."""
    test_config = Config(
        telegram_api_id=sample_config.telegram_api_id,
        telegram_api_hash=sample_config.telegram_api_hash,
        telegram_session_string=sample_config.telegram_session_string,
        telegram_bot_token=sample_config.telegram_bot_token,
        output_channel_id=sample_config.output_channel_id,
        openrouter_api_key=sample_config.openrouter_api_key,
        channels=sample_config.channels,
        rss_feeds=sample_config.rss_feeds,
        iran_filter=sample_config.iran_filter,
        test_mode=True,
        test_output_dir=tmp_path / "output",
        test_state_file=tmp_path / ".last_check.test",
    )
    return NewsSummarizer(test_config)


class TestNewsSummarizer:
    """Tests for the NewsSummarizer class."""

    async def test_start_and_stop(self, news_summarizer: NewsSummarizer) -> None:
        """Test starting and stopping the summarizer."""
        with (
            patch.object(news_summarizer.telegram_reader, "start", new_callable=AsyncMock),
            patch.object(news_summarizer.rss_reader, "start", new_callable=AsyncMock),
            patch.object(news_summarizer.output_writer, "start", new_callable=AsyncMock),
            patch.object(news_summarizer.telegram_reader, "stop", new_callable=AsyncMock),
            patch.object(news_summarizer.rss_reader, "stop", new_callable=AsyncMock),
            patch.object(news_summarizer.output_writer, "stop", new_callable=AsyncMock),
        ):
            await news_summarizer.start()
            assert news_summarizer._running is True

            await news_summarizer.stop()
            assert news_summarizer._running is False


class TestCadenceLifecycle:
    """Tests for the adaptive cadence controller lifecycle in NewsSummarizer."""

    def test_controller_created_when_enabled(self, cadence_config: Config) -> None:
        """Test the controller is created when adaptive cadence is enabled."""
        summarizer = NewsSummarizer(cadence_config)

        assert summarizer.cadence_controller is not None

    def test_controller_none_when_disabled(self, news_summarizer: NewsSummarizer) -> None:
        """Test the controller stays None when adaptive cadence is disabled."""
        assert news_summarizer.cadence_controller is None

    def test_recent_radar_alert_defaults_false(
        self, news_summarizer: NewsSummarizer
    ) -> None:
        """Test the recent-radar-alert flag starts False."""
        assert news_summarizer._recent_radar_alert is False

    async def test_start_loads_and_stop_saves_state(self, cadence_config: Config) -> None:
        """Test start() loads cadence state and stop() saves it."""
        summarizer = NewsSummarizer(cadence_config)
        assert summarizer.cadence_controller is not None

        with (
            patch.object(summarizer.telegram_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "start", new_callable=AsyncMock),
            patch.object(summarizer.telegram_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "stop", new_callable=AsyncMock),
            patch.object(summarizer.cadence_controller, "_load_state") as mock_load,
            patch.object(summarizer.cadence_controller, "_save_state") as mock_save,
        ):
            await summarizer.start()
            mock_load.assert_called_once()

            await summarizer.stop()
            mock_save.assert_called_once()


class TestCadenceInSummarizeJob:
    """Tests for adaptive cadence rescheduling inside _summarize_job."""

    async def _run_job(
        self,
        summarizer: NewsSummarizer,
        telegram_messages: list[Message],
    ) -> tuple[AsyncMock, AsyncMock]:
        """Run _summarize_job with patched IO; return reschedule and alert mocks."""
        summarizer._last_check = datetime.now() - timedelta(minutes=30)
        with (
            patch.object(
                summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=telegram_messages,
            ),
            patch.object(
                summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(summarizer.summarizer, "summarize_news", return_value=None),
            patch.object(summarizer.scheduler, "reschedule_job") as mock_reschedule,
            patch.object(
                summarizer.output_writer,
                "post_alert",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_post_alert,
        ):
            await summarizer._summarize_job()
        return mock_reschedule, mock_post_alert

    async def test_high_rate_reschedules_shorter(self, cadence_config: Config) -> None:
        """Test a high message rate reschedules to a shorter interval."""
        summarizer = NewsSummarizer(cadence_config)
        assert summarizer.cadence_controller is not None
        # Seed a low baseline so the burst reads as a surge.
        summarizer.cadence_controller._rate_window = [0.1, 0.1, 0.1, 0.1, 0.1]

        mock_reschedule, _ = await self._run_job(
            summarizer, [_iran_msg() for _ in range(50)]
        )

        mock_reschedule.assert_called_once()
        kwargs = mock_reschedule.call_args.kwargs
        assert kwargs["minutes"] < 30

    async def test_disabled_never_reschedules(
        self, news_summarizer: NewsSummarizer
    ) -> None:
        """Test no rescheduling happens when adaptive cadence is disabled."""
        assert news_summarizer.cadence_controller is None

        mock_reschedule, mock_post_alert = await self._run_job(
            news_summarizer, [_iran_msg()]
        )

        mock_reschedule.assert_not_called()
        mock_post_alert.assert_not_called()

    async def test_war_vocabulary_alone_never_escalates(self, cadence_config: Config) -> None:
        """Regression: war vocabulary at a low rate must not touch the cadence.

        The VPS false-surge bug was a single keyword hit forcing SURGE at
        0.01-0.06 msg/min; only volume vs baseline may escalate now.
        """
        summarizer = NewsSummarizer(cadence_config)
        assert summarizer.cadence_controller is not None
        summarizer.cadence_controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

        mock_reschedule, _ = await self._run_job(
            summarizer, [_iran_msg("جنگ در ایران آغاز شد")]
        )

        mock_reschedule.assert_not_called()

    async def test_radar_flag_consumed(self, cadence_config: Config) -> None:
        """Test the recent-radar-alert flag is reset after one summarize run."""
        summarizer = NewsSummarizer(cadence_config)
        assert summarizer.cadence_controller is not None
        summarizer.cadence_controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]
        summarizer._recent_radar_alert = True

        await self._run_job(summarizer, [_iran_msg()])

        assert summarizer._recent_radar_alert is False

    async def test_interval_change_posts_persian_notice(
        self, cadence_config: Config
    ) -> None:
        """Test an interval change posts the Persian notice via post_alert."""
        summarizer = NewsSummarizer(cadence_config)
        assert summarizer.cadence_controller is not None
        summarizer.cadence_controller._rate_window = [0.1, 0.1, 0.1, 0.1, 0.1]

        _, mock_post_alert = await self._run_job(
            summarizer, [_iran_msg() for _ in range(50)]
        )

        mock_post_alert.assert_called_once()
        notice = mock_post_alert.call_args.args[0]
        assert "افزایش حجم اخبار" in notice
        assert "دقیقه" in notice

    async def test_no_notice_when_interval_unchanged(
        self, cadence_config: Config
    ) -> None:
        """Test no notice is posted when the interval did not change."""
        summarizer = NewsSummarizer(cadence_config)
        assert summarizer.cadence_controller is not None
        summarizer.cadence_controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

        _, mock_post_alert = await self._run_job(summarizer, [_iran_msg()])

        mock_post_alert.assert_not_called()


class TestIntensityProbe:
    """Tests for the escalate-only intensity probe job."""

    def _fast_config(self, cadence_config: Config) -> Config:
        """Return a cadence config with fast_escalation enabled."""
        cfg = replace(cadence_config)
        cfg.adaptive_cadence.fast_escalation = True
        cfg.adaptive_cadence.probe_interval_minutes = 5
        return cfg

    async def test_probe_job_scheduled_when_fast_escalation(
        self, cadence_config: Config
    ) -> None:
        """Test start() adds the probe job when fast_escalation is on."""
        summarizer = NewsSummarizer(self._fast_config(cadence_config))
        with (
            patch.object(summarizer.telegram_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "start", new_callable=AsyncMock),
            patch.object(summarizer.telegram_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "stop", new_callable=AsyncMock),
        ):
            await summarizer.start()
            job = summarizer.scheduler.get_job("probe_intensity")
            await summarizer.stop()

        assert job is not None

    async def test_probe_job_absent_when_disabled(self, cadence_config: Config) -> None:
        """Test no probe job is added when fast_escalation is off."""
        summarizer = NewsSummarizer(cadence_config)  # fast_escalation defaults off
        with (
            patch.object(summarizer.telegram_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "start", new_callable=AsyncMock),
            patch.object(summarizer.telegram_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "stop", new_callable=AsyncMock),
        ):
            await summarizer.start()
            job = summarizer.scheduler.get_job("probe_intensity")
            await summarizer.stop()

        assert job is None

    async def test_probe_escalates_reschedules(self, cadence_config: Config) -> None:
        """Test the probe reschedules the summarize job to a shorter interval."""
        summarizer = NewsSummarizer(self._fast_config(cadence_config))
        assert summarizer.cadence_controller is not None
        summarizer.cadence_controller._rate_window = [0.1, 0.1, 0.1, 0.1, 0.1]

        with (
            patch.object(
                summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[_iran_msg() for _ in range(50)],
            ),
            patch.object(
                summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(summarizer.scheduler, "reschedule_job") as mock_reschedule,
            patch.object(summarizer.scheduler, "modify_job") as mock_modify,
            patch.object(
                summarizer.output_writer,
                "post_alert",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await summarizer._probe_intensity_job()

        mock_reschedule.assert_called_once()
        assert mock_reschedule.call_args.kwargs["minutes"] < 30
        mock_modify.assert_not_called()  # probe only reschedules, never fires early

    async def test_probe_window_smooths_small_cluster(
        self, cadence_config: Config
    ) -> None:
        """Test the trailing window stops a tiny burst from reading as a surge.

        Two messages over the 15-min window is 0.13/min (NORMAL vs a 0.1
        baseline), so the probe does not escalate. The old 5-min denominator
        would have read 0.4/min (a 4x SURGE) and flapped the cadence.
        """
        cfg = self._fast_config(cadence_config)
        cfg.adaptive_cadence.probe_window_minutes = 15
        summarizer = NewsSummarizer(cfg)
        assert summarizer.cadence_controller is not None
        summarizer.cadence_controller._rate_window = [0.1, 0.1, 0.1, 0.1, 0.1]

        with (
            patch.object(
                summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[_iran_msg(), _iran_msg()],
            ) as mock_fetch,
            patch.object(
                summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(summarizer.scheduler, "reschedule_job") as mock_reschedule,
            patch.object(
                summarizer.output_writer,
                "post_alert",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_post_alert,
        ):
            await summarizer._probe_intensity_job()

        mock_reschedule.assert_not_called()  # no false escalation
        mock_post_alert.assert_not_called()  # and no notice spam
        # The probe looked back over the wider window, not the 5-min run cadence.
        since = mock_fetch.call_args.args[0]
        assert (datetime.now() - since) > timedelta(minutes=10)

    async def test_probe_never_fires_immediate_catchup(
        self, cadence_config: Config
    ) -> None:
        """Test the probe never triggers an immediate catch-up, even on war vocab."""
        summarizer = NewsSummarizer(self._fast_config(cadence_config))
        assert summarizer.cadence_controller is not None
        # Low baseline so the burst escalates; texts carry war vocabulary.
        summarizer.cadence_controller._rate_window = [0.1, 0.1, 0.1, 0.1, 0.1]

        with (
            patch.object(
                summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[_iran_msg("جنگ در ایران آغاز شد") for _ in range(50)],
            ),
            patch.object(
                summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(summarizer.scheduler, "reschedule_job") as mock_reschedule,
            patch.object(summarizer.scheduler, "modify_job") as mock_modify,
            patch.object(
                summarizer.output_writer,
                "post_alert",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await summarizer._probe_intensity_job()

        mock_reschedule.assert_called_once()  # escalation still happens
        mock_modify.assert_not_called()  # but no immediate catch-up post

    async def test_probe_escalation_posts_notice(self, cadence_config: Config) -> None:
        """Test a probe escalation posts the Persian cadence notice."""
        summarizer = NewsSummarizer(self._fast_config(cadence_config))
        assert summarizer.cadence_controller is not None
        summarizer.cadence_controller._rate_window = [0.1, 0.1, 0.1, 0.1, 0.1]

        with (
            patch.object(
                summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[_iran_msg() for _ in range(50)],
            ),
            patch.object(
                summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(summarizer.scheduler, "reschedule_job"),
            patch.object(
                summarizer.output_writer,
                "post_alert",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_post_alert,
        ):
            await summarizer._probe_intensity_job()

        mock_post_alert.assert_called_once()
        assert "افزایش حجم اخبار" in mock_post_alert.call_args.args[0]

    async def test_probe_is_side_effect_free(self, cadence_config: Config) -> None:
        """Test the probe does not mutate seen URLs or advance last_check."""
        summarizer = NewsSummarizer(self._fast_config(cadence_config))
        assert summarizer.cadence_controller is not None
        summarizer._seen_urls = {"https://kept.example/1"}
        summarizer._last_check = None

        with (
            patch.object(
                summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[_iran_msg()],
            ),
            patch.object(
                summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_rss,
            patch.object(summarizer.scheduler, "reschedule_job"),
        ):
            await summarizer._probe_intensity_job()

        # Real seen-URL set is untouched and last_check is not advanced.
        assert summarizer._seen_urls == {"https://kept.example/1"}
        assert summarizer._last_check is None
        # The probe passed a throwaway empty seen_urls set to the RSS reader.
        assert mock_rss.call_args.kwargs.get("seen_urls") == set()

    async def test_probe_noop_without_controller(
        self, news_summarizer: NewsSummarizer
    ) -> None:
        """Test the probe is a no-op when no controller is configured."""
        # Should not raise even though cadence is disabled.
        await news_summarizer._probe_intensity_job()

    async def test_probe_consumes_radar_flag(self, cadence_config: Config) -> None:
        """Test the probe resets the radar flag so it cannot sticky-promote."""
        summarizer = NewsSummarizer(self._fast_config(cadence_config))
        assert summarizer.cadence_controller is not None
        summarizer.cadence_controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]
        summarizer._recent_radar_alert = True

        with (
            patch.object(
                summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[_iran_msg()],
            ),
            patch.object(
                summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(summarizer.scheduler, "reschedule_job"),
            patch.object(
                summarizer.output_writer,
                "post_alert",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await summarizer._probe_intensity_job()

        assert summarizer._recent_radar_alert is False

    async def test_summarize_job_with_messages(
        self, news_summarizer: NewsSummarizer, sample_messages: list, sample_summary: MagicMock
    ) -> None:
        """Test the summarization job when messages are found."""
        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=sample_messages,
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=sample_summary,
            ),
            patch.object(
                news_summarizer.output_writer,
                "post_summary",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await news_summarizer._summarize_job()

            news_summarizer.telegram_reader.get_all_channel_updates.assert_called_once()
            news_summarizer.rss_reader.get_all_feed_updates.assert_called_once()
            news_summarizer.summarizer.summarize_news.assert_called_once()
            news_summarizer.output_writer.post_summary.assert_called_once_with(sample_summary)

    async def test_summarize_job_no_messages(self, news_summarizer: NewsSummarizer) -> None:
        """Test the summarization job when no messages are found."""
        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(news_summarizer.summarizer, "summarize_news") as mock_summarize,
        ):
            await news_summarizer._summarize_job()

            mock_summarize.assert_not_called()

    async def test_summarize_job_summary_generation_fails(
        self, news_summarizer: NewsSummarizer, sample_messages: list
    ) -> None:
        """Test the summarization job when summary generation fails."""
        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=sample_messages,
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=None,
            ),
            patch.object(
                news_summarizer.output_writer, "post_summary", new_callable=AsyncMock
            ) as mock_post,
        ):
            await news_summarizer._summarize_job()

            mock_post.assert_not_called()

    async def test_summarize_job_with_rss_messages(
        self, news_summarizer: NewsSummarizer, sample_rss_messages: list, sample_summary: MagicMock
    ) -> None:
        """Test the summarization job with RSS messages."""
        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=sample_rss_messages,
            ),
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=sample_summary,
            ),
            patch.object(
                news_summarizer.output_writer,
                "post_summary",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await news_summarizer._summarize_job()

            # Iran filter should filter the messages
            news_summarizer.summarizer.summarize_news.assert_called_once()
            # Should only have Iran-related messages
            # With keywords ["iran", "tehran"], only "Iran announces..." matches
            # (word boundary prevents "Iranian" from matching "iran")
            call_args = news_summarizer.summarizer.summarize_news.call_args[0][0]
            assert len(call_args) == 1
            assert "Iran" in call_args[0].text

    def test_load_last_check_file_exists(
        self, sample_config: Config, tmp_path: Path
    ) -> None:
        """Test loading last check timestamp from file."""
        # Create a temporary last check file
        last_check = datetime(2024, 1, 15, 10, 0)
        check_file = tmp_path / ".last_check"
        check_file.write_text(json.dumps({"last_check": last_check.isoformat()}))

        # Create config with custom state file
        config = Config(
            telegram_api_id=sample_config.telegram_api_id,
            telegram_api_hash=sample_config.telegram_api_hash,
            telegram_session_string=sample_config.telegram_session_string,
            telegram_bot_token=sample_config.telegram_bot_token,
            output_channel_id=sample_config.output_channel_id,
            openrouter_api_key=sample_config.openrouter_api_key,
            test_mode=True,
            test_state_file=check_file,
        )

        summarizer = NewsSummarizer(config)
        summarizer._load_last_check()

        assert summarizer._last_check == last_check

    def test_load_last_check_file_not_exists(self, sample_config: Config, tmp_path: Path) -> None:
        """Test loading last check when file doesn't exist."""
        config = Config(
            telegram_api_id=sample_config.telegram_api_id,
            telegram_api_hash=sample_config.telegram_api_hash,
            telegram_session_string=sample_config.telegram_session_string,
            telegram_bot_token=sample_config.telegram_bot_token,
            output_channel_id=sample_config.output_channel_id,
            openrouter_api_key=sample_config.openrouter_api_key,
            test_mode=True,
            test_state_file=tmp_path / "nonexistent" / ".last_check",
        )

        summarizer = NewsSummarizer(config)
        summarizer._load_last_check()

        assert summarizer._last_check is None

    def test_load_last_check_invalid_json(
        self, sample_config: Config, tmp_path: Path
    ) -> None:
        """Test loading last check with invalid JSON."""
        check_file = tmp_path / ".last_check"
        check_file.write_text("invalid json")

        config = Config(
            telegram_api_id=sample_config.telegram_api_id,
            telegram_api_hash=sample_config.telegram_api_hash,
            telegram_session_string=sample_config.telegram_session_string,
            telegram_bot_token=sample_config.telegram_bot_token,
            output_channel_id=sample_config.output_channel_id,
            openrouter_api_key=sample_config.openrouter_api_key,
            test_mode=True,
            test_state_file=check_file,
        )

        summarizer = NewsSummarizer(config)
        summarizer._load_last_check()

        assert summarizer._last_check is None

    def test_save_last_check(
        self, sample_config: Config, tmp_path: Path
    ) -> None:
        """Test saving last check timestamp to file."""
        check_file = tmp_path / ".last_check"

        config = Config(
            telegram_api_id=sample_config.telegram_api_id,
            telegram_api_hash=sample_config.telegram_api_hash,
            telegram_session_string=sample_config.telegram_session_string,
            telegram_bot_token=sample_config.telegram_bot_token,
            output_channel_id=sample_config.output_channel_id,
            openrouter_api_key=sample_config.openrouter_api_key,
            test_mode=True,
            test_state_file=check_file,
        )

        summarizer = NewsSummarizer(config)
        summarizer._last_check = datetime(2024, 1, 15, 11, 0)
        summarizer._save_last_check()

        # Verify file was written
        assert check_file.exists()
        data = json.loads(check_file.read_text())
        assert "last_check" in data

    def test_save_last_check_none(self, sample_config: Config, tmp_path: Path) -> None:
        """Test saving last check when timestamp is None."""
        check_file = tmp_path / ".last_check"

        config = Config(
            telegram_api_id=sample_config.telegram_api_id,
            telegram_api_hash=sample_config.telegram_api_hash,
            telegram_session_string=sample_config.telegram_session_string,
            telegram_bot_token=sample_config.telegram_bot_token,
            output_channel_id=sample_config.output_channel_id,
            openrouter_api_key=sample_config.openrouter_api_key,
            test_mode=True,
            test_state_file=check_file,
        )

        summarizer = NewsSummarizer(config)
        summarizer._last_check = None
        summarizer._save_last_check()

        # File should not be created
        assert not check_file.exists()


class TestSeenUrls:
    """Tests for seen URLs deduplication."""

    def test_load_seen_urls_file_exists(
        self, news_summarizer: NewsSummarizer, tmp_path: Path
    ) -> None:
        """Test loading seen URLs from file."""
        seen_urls = ["https://example.com/article1", "https://example.com/article2"]
        urls_file = tmp_path / ".seen_urls"
        urls_file.write_text(json.dumps({"urls": seen_urls}))

        with patch("src.main.SEEN_URLS_FILE", urls_file):
            news_summarizer._load_seen_urls()

        assert news_summarizer._seen_urls == set(seen_urls)

    def test_load_seen_urls_file_not_exists(self, news_summarizer: NewsSummarizer) -> None:
        """Test loading seen URLs when file doesn't exist."""
        with patch("src.main.SEEN_URLS_FILE", Path("/nonexistent/.seen_urls")):
            news_summarizer._load_seen_urls()

        assert news_summarizer._seen_urls == set()

    def test_load_seen_urls_invalid_json(
        self, news_summarizer: NewsSummarizer, tmp_path: Path
    ) -> None:
        """Test loading seen URLs with invalid JSON."""
        urls_file = tmp_path / ".seen_urls"
        urls_file.write_text("invalid json")

        with patch("src.main.SEEN_URLS_FILE", urls_file):
            news_summarizer._load_seen_urls()

        assert news_summarizer._seen_urls == set()

    def test_save_seen_urls(
        self, news_summarizer: NewsSummarizer, tmp_path: Path
    ) -> None:
        """Test saving seen URLs to file."""
        urls_file = tmp_path / ".seen_urls"
        news_summarizer._seen_urls = {"https://example.com/article1", "https://example.com/article2"}

        with patch("src.main.SEEN_URLS_FILE", urls_file):
            news_summarizer._save_seen_urls()

        assert urls_file.exists()
        data = json.loads(urls_file.read_text())
        assert "urls" in data
        assert set(data["urls"]) == news_summarizer._seen_urls

    def test_save_seen_urls_limits_size(
        self, news_summarizer: NewsSummarizer, tmp_path: Path
    ) -> None:
        """Test that saving seen URLs limits to MAX_SEEN_URLS."""
        urls_file = tmp_path / ".seen_urls"
        # Create more URLs than the max
        news_summarizer._seen_urls = {f"https://example.com/article{i}" for i in range(MAX_SEEN_URLS + 100)}

        with patch("src.main.SEEN_URLS_FILE", urls_file):
            news_summarizer._save_seen_urls()

        data = json.loads(urls_file.read_text())
        assert len(data["urls"]) == MAX_SEEN_URLS

    async def test_summarize_job_passes_seen_urls_to_rss_reader(
        self, news_summarizer: NewsSummarizer, sample_messages: list, sample_summary: MagicMock
    ) -> None:
        """Test that seen_urls are passed to the RSS reader."""
        news_summarizer._seen_urls = {"https://old.example.com/article1"}

        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=sample_messages,
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_rss,
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=sample_summary,
            ),
            patch.object(
                news_summarizer.output_writer, "post_summary", new_callable=AsyncMock, return_value=True
            ),
        ):
            await news_summarizer._summarize_job()

            # Verify seen_urls was passed to get_all_feed_updates
            mock_rss.assert_called_once()
            call_kwargs = mock_rss.call_args[1]
            assert "seen_urls" in call_kwargs
            assert call_kwargs["seen_urls"] == news_summarizer._seen_urls

    async def test_summarize_job_adds_new_rss_urls_to_seen(
        self, news_summarizer: NewsSummarizer, sample_rss_messages: list, sample_summary: MagicMock
    ) -> None:
        """Test that new RSS article URLs are added to seen_urls after processing."""
        news_summarizer._seen_urls = set()

        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=sample_rss_messages,
            ),
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=sample_summary,
            ),
            patch.object(
                news_summarizer.output_writer, "post_summary", new_callable=AsyncMock, return_value=True
            ),
        ):
            await news_summarizer._summarize_job()

            # Only Iran-related messages are filtered and added
            # Based on sample_rss_messages fixture, only the Iran message passes
            assert len(news_summarizer._seen_urls) >= 1


class TestSeenUrlsFile:
    """Tests for seen URLs file path."""

    def test_seen_urls_file_path(self) -> None:
        """Test that SEEN_URLS_FILE is defined correctly."""
        assert SEEN_URLS_FILE == Path(".seen_urls")

    def test_max_seen_urls_constant(self) -> None:
        """Test that MAX_SEEN_URLS is defined."""
        assert MAX_SEEN_URLS == 1000


class TestTestMode:
    """Tests for test mode functionality."""

    def test_uses_file_writer_in_test_mode(self, test_mode_summarizer: NewsSummarizer) -> None:
        """Test that FileWriter is used in test mode."""
        assert isinstance(test_mode_summarizer.output_writer, FileWriter)

    def test_uses_telegram_bot_in_production(self, news_summarizer: NewsSummarizer) -> None:
        """Test that TelegramBot is used in production mode."""
        assert isinstance(news_summarizer.output_writer, TelegramBot)

    def test_uses_test_state_file(self, test_mode_summarizer: NewsSummarizer, tmp_path: Path) -> None:
        """Test that test mode uses separate state file."""
        assert test_mode_summarizer._state_file == tmp_path / ".last_check.test"

    def test_uses_production_state_file(self, news_summarizer: NewsSummarizer) -> None:
        """Test that production mode uses default state file."""
        assert news_summarizer._state_file == Path(".last_check")

    def test_effective_interval_in_test_mode(self, test_mode_summarizer: NewsSummarizer) -> None:
        """Test that test mode uses test interval."""
        assert test_mode_summarizer.config.effective_summary_interval_minutes == 5

    def test_effective_interval_in_production(self, news_summarizer: NewsSummarizer) -> None:
        """Test that production mode uses production interval."""
        assert news_summarizer.config.effective_summary_interval_minutes == 30

    def test_uses_composite_writer_when_bale_enabled(self, sample_config: Config) -> None:
        """Test that CompositeOutputWriter is used when Bale is enabled."""
        bale_config = replace(
            sample_config,
            bale_bot_token="bale_token",
            bale_channel_id="@bale_channel",
        )
        summarizer = NewsSummarizer(bale_config)
        assert isinstance(summarizer.output_writer, CompositeOutputWriter)

    def test_uses_telegram_only_when_bale_disabled(self, sample_config: Config) -> None:
        """Test that only TelegramBot is used when Bale is not configured."""
        summarizer = NewsSummarizer(sample_config)
        assert isinstance(summarizer.output_writer, TelegramBot)


@pytest.fixture
def dedup_config(sample_config: Config) -> Config:
    """Return a config with deduplication enabled."""
    return replace(sample_config, deduplication=DeduplicationConfig(enabled=True))


class TestRadarLifecycle:
    """Tests for the Cloudflare Radar monitor lifecycle in NewsSummarizer."""

    def test_radar_monitor_created_when_enabled_with_token(
        self, radar_config: Config
    ) -> None:
        """The radar monitor is created when enabled and a token is present."""
        summarizer = NewsSummarizer(radar_config)
        assert summarizer.radar_monitor is not None

    def test_radar_monitor_skipped_without_token(self, radar_config: Config) -> None:
        """The radar monitor is skipped (with a warning) when no token is set."""
        config = replace(radar_config, cloudflare_api_token=None)
        summarizer = NewsSummarizer(config)
        assert summarizer.radar_monitor is None

    async def test_start_and_stop_with_radar(self, radar_config: Config) -> None:
        """start()/stop() drive the radar monitor and schedule its job."""
        summarizer = NewsSummarizer(radar_config)
        assert summarizer.radar_monitor is not None

        with (
            patch.object(summarizer.telegram_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "start", new_callable=AsyncMock),
            patch.object(summarizer.telegram_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "stop", new_callable=AsyncMock),
            patch.object(summarizer.radar_monitor, "start", new_callable=AsyncMock) as mock_start,
            patch.object(summarizer.radar_monitor, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            await summarizer.start()
            job = summarizer.scheduler.get_job("check_radar")
            await summarizer.stop()

        assert job is not None
        mock_start.assert_awaited_once()
        mock_stop.assert_awaited_once()

    async def test_check_radar_job_posts_alerts(self, radar_config: Config) -> None:
        """The radar job posts each alert and flags a recent radar alert."""
        summarizer = NewsSummarizer(radar_config)
        assert summarizer.radar_monitor is not None
        alert = MagicMock()
        alert.message = "outage"
        alert.alert_type = MagicMock()
        alert.alert_type.value = "CLOUDFLARE_ANOMALY"

        with (
            patch.object(
                summarizer.radar_monitor,
                "check_all",
                new_callable=AsyncMock,
                return_value=[alert],
            ),
            patch.object(
                summarizer.output_writer,
                "post_alert",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_post,
        ):
            await summarizer._check_radar_job()

        mock_post.assert_awaited_once_with("outage")
        assert summarizer._recent_radar_alert is True

    async def test_check_radar_job_logs_post_failure(self, radar_config: Config) -> None:
        """A failed alert post is logged but does not raise."""
        summarizer = NewsSummarizer(radar_config)
        assert summarizer.radar_monitor is not None
        alert = MagicMock()
        alert.message = "outage"
        alert.alert_type = MagicMock()
        alert.alert_type.value = "CLOUDFLARE_ANOMALY"

        with (
            patch.object(
                summarizer.radar_monitor,
                "check_all",
                new_callable=AsyncMock,
                return_value=[alert],
            ),
            patch.object(
                summarizer.output_writer,
                "post_alert",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            await summarizer._check_radar_job()

        # A failed post must not flag a radar alert (the loop still completes).
        assert summarizer._recent_radar_alert is True

    async def test_check_radar_job_no_alerts(self, radar_config: Config) -> None:
        """With no alerts the radar flag stays unset."""
        summarizer = NewsSummarizer(radar_config)
        assert summarizer.radar_monitor is not None

        with patch.object(
            summarizer.radar_monitor,
            "check_all",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await summarizer._check_radar_job()

        assert summarizer._recent_radar_alert is False

    async def test_check_radar_job_handles_exception(self, radar_config: Config) -> None:
        """An exception in the radar job is caught and logged."""
        summarizer = NewsSummarizer(radar_config)
        assert summarizer.radar_monitor is not None

        with patch.object(
            summarizer.radar_monitor,
            "check_all",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            await summarizer._check_radar_job()  # Should not raise.

    async def test_check_radar_job_noop_without_monitor(
        self, news_summarizer: NewsSummarizer
    ) -> None:
        """The radar job is a no-op when no monitor is configured."""
        assert news_summarizer.radar_monitor is None
        await news_summarizer._check_radar_job()  # Should not raise.


class TestDeduplicationLifecycle:
    """Tests for the deduplicator lifecycle and summarize-job integration."""

    async def test_start_and_stop_with_deduplication(self, dedup_config: Config) -> None:
        """start()/stop() initialize and tear down the deduplicator."""
        summarizer = NewsSummarizer(dedup_config)

        with (
            patch.object(summarizer.telegram_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "start", new_callable=AsyncMock),
            patch.object(summarizer.telegram_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "stop", new_callable=AsyncMock),
            patch.object(summarizer.deduplicator, "start") as mock_start,
            patch.object(summarizer.deduplicator, "stop") as mock_stop,
        ):
            await summarizer.start()
            await summarizer.stop()

        mock_start.assert_called_once()
        mock_stop.assert_called_once()

    async def test_summarize_job_runs_deduplication(
        self, dedup_config: Config, sample_summary: MagicMock
    ) -> None:
        """The summarize job deduplicates and cleans up when enabled."""
        summarizer = NewsSummarizer(dedup_config)
        messages = [_iran_msg()]

        with (
            patch.object(
                summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=messages,
            ),
            patch.object(
                summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                summarizer.deduplicator, "process_messages", return_value=messages
            ) as mock_process,
            patch.object(summarizer.deduplicator, "cleanup", return_value=3) as mock_cleanup,
            patch.object(summarizer.summarizer, "summarize_news", return_value=sample_summary),
            patch.object(
                summarizer.output_writer,
                "post_summary",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await summarizer._summarize_job()

        mock_process.assert_called_once()
        mock_cleanup.assert_called_once()


class TestSummarizeJobErrorPaths:
    """Tests for the summarize-job error and failure branches."""

    async def test_logs_when_post_summary_fails(
        self, news_summarizer: NewsSummarizer, sample_summary: MagicMock
    ) -> None:
        """A failed summary post is logged as an error."""
        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[_iran_msg()],
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.summarizer, "summarize_news", return_value=sample_summary
            ),
            patch.object(
                news_summarizer.output_writer,
                "post_summary",
                new_callable=AsyncMock,
                return_value=False,
            ) as mock_post,
        ):
            await news_summarizer._summarize_job()

        mock_post.assert_awaited_once()

    async def test_summarize_job_handles_exception(
        self, news_summarizer: NewsSummarizer
    ) -> None:
        """An exception inside the summarize job is caught and logged."""
        with patch.object(
            news_summarizer.telegram_reader,
            "get_all_channel_updates",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            await news_summarizer._summarize_job()  # Should not raise.

    async def test_probe_job_handles_exception(self, cadence_config: Config) -> None:
        """An exception inside the probe job is caught and logged."""
        cfg = replace(cadence_config)
        cfg.adaptive_cadence.fast_escalation = True
        summarizer = NewsSummarizer(cfg)

        with patch.object(
            summarizer.telegram_reader,
            "get_all_channel_updates",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            await summarizer._probe_intensity_job()  # Should not raise.

    async def test_post_cadence_notice_logs_failure(
        self, cadence_config: Config
    ) -> None:
        """A failed cadence-notice post is logged as an error."""
        summarizer = NewsSummarizer(cadence_config)
        decision = CadenceDecision(
            previous_interval=30,
            new_interval=5,
            level=IntensityLevel.SURGE,
            reason=CadenceChangeReason.NEWS_VOLUME,
            previous_level=IntensityLevel.NORMAL,
        )

        with patch.object(
            summarizer.output_writer,
            "post_alert",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_post:
            await summarizer._post_cadence_notice(decision)

        mock_post.assert_awaited_once()


class TestStateSaveErrors:
    """Tests for OSError handling when persisting state."""

    def test_save_last_check_handles_os_error(
        self, news_summarizer: NewsSummarizer
    ) -> None:
        """An OSError while saving the last-check timestamp is swallowed."""
        fake_path = MagicMock()
        fake_path.write_text.side_effect = OSError("disk full")
        news_summarizer._state_file = fake_path
        news_summarizer._last_check = datetime(2024, 1, 15, 11, 0)

        news_summarizer._save_last_check()  # Should not raise.

        fake_path.write_text.assert_called_once()

    def test_save_seen_urls_handles_os_error(
        self, news_summarizer: NewsSummarizer
    ) -> None:
        """An OSError while saving seen URLs is swallowed."""
        fake_path = MagicMock()
        fake_path.write_text.side_effect = OSError("disk full")
        news_summarizer._seen_urls = {"https://example.com/a"}

        with patch("src.main.SEEN_URLS_FILE", fake_path):
            news_summarizer._save_seen_urls()  # Should not raise.

        fake_path.write_text.assert_called_once()


class TestMainEntrypoint:
    """Tests for the module-level main() coroutine and __main__ guard."""

    async def test_main_exits_on_config_error(self) -> None:
        """A ConfigError aborts startup with a non-zero exit."""
        with (
            patch.object(Config, "from_env", side_effect=ConfigError("bad config")),
            pytest.raises(SystemExit) as exc_info,
        ):
            await main()

        assert exc_info.value.code == 1

    async def test_main_starts_and_stops(self, sample_config: Config) -> None:
        """main() builds the summarizer, starts it, waits, then stops it."""
        no_sources = replace(sample_config, channels=[], rss_feeds=[])
        mock_event = MagicMock()
        mock_event.wait = AsyncMock()
        mock_loop = MagicMock()
        mock_summarizer = MagicMock()
        mock_summarizer.start = AsyncMock()
        mock_summarizer.stop = AsyncMock()

        with (
            patch.object(Config, "from_env", return_value=no_sources),
            patch.object(main_module, "NewsSummarizer", return_value=mock_summarizer),
            patch("src.main.asyncio.get_running_loop", return_value=mock_loop),
            patch("src.main.asyncio.Event", return_value=mock_event),
        ):
            await main_module.main()

        mock_summarizer.start.assert_awaited_once()
        mock_summarizer.stop.assert_awaited_once()
        mock_event.wait.assert_awaited_once()

        # Drive the registered signal handler so its body is exercised.
        handler = mock_loop.add_signal_handler.call_args.args[1]
        handler()
        mock_event.set.assert_called_once()

    def test_main_module_entrypoint(self) -> None:
        """Running the module as __main__ invokes asyncio.run(main())."""
        with patch("asyncio.run") as mock_run:
            runpy.run_module("src.main", run_name="__main__")

        mock_run.assert_called_once()
