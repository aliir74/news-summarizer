"""Main entry point for the news summarizer bot."""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.bale_bot import BaleBot
from src.cadence import AdaptiveCadenceController, CadenceDecision
from src.cloudflare_radar import CloudflareRadarMonitor
from src.composite_writer import CompositeOutputWriter
from src.config import Config, ConfigError
from src.deduplicator import Deduplicator
from src.file_writer import FileWriter
from src.iran_filter import IranRelevanceFilter
from src.models import Message, build_cadence_notice
from src.output_writer import OutputWriter
from src.rss_reader import RSSReader
from src.summarizer import Summarizer
from src.telegram_bot import TelegramBot
from src.telegram_reader import TelegramReader

# Configure logging (level configurable via LOG_LEVEL env var)
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# File for persisting seen RSS article URLs (prevents duplicates)
SEEN_URLS_FILE = Path(".seen_urls")

# Maximum number of seen URLs to keep (prevents unbounded growth)
MAX_SEEN_URLS = 1000


class NewsSummarizer:
    """Main application class that coordinates all components."""

    def __init__(self, config: Config) -> None:
        """Initialize the news summarizer with configuration."""
        self.config = config
        self.telegram_reader = TelegramReader(config)
        self.rss_reader = RSSReader(config)
        self.iran_filter = IranRelevanceFilter(config.iran_filter)

        self.summarizer = Summarizer(config)

        # Select output writer based on test mode and Bale config
        self.output_writer: OutputWriter
        if config.test_mode:
            self.output_writer = FileWriter(config)
            logger.info("Test mode enabled - writing output to file")
        else:
            writers: list[OutputWriter] = [TelegramBot(config)]
            if config.bale_enabled:
                writers.append(BaleBot(config, self.summarizer))
                logger.info("Bale output enabled")
            if len(writers) == 1:
                self.output_writer = writers[0]
            else:
                self.output_writer = CompositeOutputWriter(writers)
        self.deduplicator = Deduplicator(config)
        self.scheduler = AsyncIOScheduler()
        self._last_check: datetime | None = None
        self._seen_urls: set[str] = set()
        self._running = False

        # Adaptive cadence controller (optional). Tracks the recent radar alert
        # state so the controller can treat an internet outage as a crisis signal.
        self._recent_radar_alert = False
        self.cadence_controller: AdaptiveCadenceController | None = None
        if config.adaptive_cadence.enabled:
            self.cadence_controller = AdaptiveCadenceController(config)
            logger.info("Adaptive cadence enabled")

        # Cloudflare Radar monitor (optional)
        self.radar_monitor: CloudflareRadarMonitor | None = None
        if config.radar_monitor.enabled and config.cloudflare_api_token:
            self.radar_monitor = CloudflareRadarMonitor(config)
            logger.info("Cloudflare Radar monitoring enabled")
        elif config.radar_monitor.enabled and not config.cloudflare_api_token:
            logger.warning(
                "Radar monitor enabled but CLOUDFLARE_API_TOKEN not set - skipping"
            )

        # State file path based on test mode
        self._state_file = config.effective_state_file

    async def start(self) -> None:
        """Start the news summarizer."""
        logger.info("Starting news summarizer...")

        # Load last check timestamp and seen URLs
        self._load_last_check()
        self._load_seen_urls()

        # Load cadence state before the scheduler starts (the first summarize job
        # fires immediately, so the controller must be warm beforehand).
        if self.cadence_controller:
            self.cadence_controller.load_state()

        # Start clients
        await self.telegram_reader.start()
        await self.rss_reader.start()
        await self.output_writer.start()

        # Start radar monitor if enabled
        if self.radar_monitor:
            await self.radar_monitor.start()

        # Start deduplicator if enabled
        if self.config.deduplication.enabled:
            self.deduplicator.start()
            logger.info("Deduplicator initialized")

        # Schedule the summarization job
        self.scheduler.add_job(
            self._summarize_job,
            "interval",
            minutes=self.config.effective_summary_interval_minutes,
            id="summarize_news",
            next_run_time=datetime.now(),  # Run immediately on start
            misfire_grace_time=None,  # Always run even after Mac sleep
            coalesce=True,  # Merge missed runs into one
        )

        # Schedule the radar monitoring job if enabled
        if self.radar_monitor:
            self.scheduler.add_job(
                self._check_radar_job,
                "interval",
                minutes=self.config.radar_monitor.interval_minutes,
                id="check_radar",
                next_run_time=datetime.now(),  # Run immediately on start
                misfire_grace_time=None,  # Always run even after Mac sleep
                coalesce=True,  # Merge missed runs into one
            )

        # Schedule the escalation probe job if fast escalation is enabled
        if self.cadence_controller and self.config.adaptive_cadence.fast_escalation:
            self.scheduler.add_job(
                self._probe_intensity_job,
                "interval",
                minutes=self.config.adaptive_cadence.probe_interval_minutes,
                id="probe_intensity",
                misfire_grace_time=None,  # Always run even after Mac sleep
                coalesce=True,  # Merge missed runs into one
            )
            logger.info(
                f"Fast escalation probe active every "
                f"{self.config.adaptive_cadence.probe_interval_minutes} minutes."
            )

        self.scheduler.start()

        self._running = True
        mode = "TEST" if self.config.test_mode else "PRODUCTION"
        logger.info(
            f"News summarizer started in {mode} mode. "
            f"Running every {self.config.effective_summary_interval_minutes} minutes."
        )
        logger.info(f"Monitoring {len(self.config.channels)} Telegram channels.")
        logger.info(f"Monitoring {len(self.config.rss_feeds)} RSS feeds.")
        if self.radar_monitor:
            logger.info(
                f"Cloudflare Radar monitoring every "
                f"{self.config.radar_monitor.interval_minutes} minutes."
            )

    async def stop(self) -> None:
        """Stop the news summarizer."""
        logger.info("Stopping news summarizer...")

        self._running = False
        self.scheduler.shutdown(wait=False)

        # Save last check timestamp and seen URLs
        self._save_last_check()
        self._save_seen_urls()

        # Persist cadence state so it survives restarts (systemd on the VPS).
        if self.cadence_controller:
            self.cadence_controller.save_state()

        # Stop deduplicator if enabled
        if self.config.deduplication.enabled:
            self.deduplicator.stop()

        # Stop clients
        await self.telegram_reader.stop()
        await self.rss_reader.stop()
        await self.output_writer.stop()

        # Stop radar monitor if enabled
        if self.radar_monitor:
            await self.radar_monitor.stop()

        logger.info("News summarizer stopped.")

    async def _summarize_job(self) -> None:
        """Job that fetches news and posts summaries."""
        try:
            # Determine the time window
            since = self._last_check or datetime.now() - timedelta(
                minutes=self.config.effective_summary_interval_minutes
            )

            logger.info(f"Fetching messages since {since}")

            # Fetch messages from Telegram channels
            telegram_messages = await self.telegram_reader.get_all_channel_updates(since)
            logger.info(f"Found {len(telegram_messages)} Telegram messages")

            # Fetch and filter messages from RSS feeds (pass seen_urls for deduplication)
            rss_messages = await self.rss_reader.get_all_feed_updates(
                since, seen_urls=self._seen_urls
            )
            logger.info(f"Found {len(rss_messages)} RSS articles")

            filtered_telegram = self.iran_filter.filter_messages(telegram_messages)
            logger.info(
                f"Filtered to {len(filtered_telegram)}/{len(telegram_messages)} "
                f"Iran-related Telegram messages"
            )

            filtered_rss = self.iran_filter.filter_messages(rss_messages)
            logger.info(f"Filtered to {len(filtered_rss)} Iran-related RSS articles")

            # Merge all messages
            messages = filtered_telegram + filtered_rss
            messages.sort(key=lambda m: m.timestamp, reverse=True)
            logger.info(f"Total {len(messages)} messages before deduplication")

            # Adapt the summary cadence from the pre-dedup filtered message rate.
            cadence_decision = self._apply_adaptive_cadence(messages, since)

            # Apply deduplication if enabled
            if self.config.deduplication.enabled and messages:
                messages = self.deduplicator.process_messages(messages)
                logger.info(f"After deduplication: {len(messages)} unique messages")

                # Cleanup old fingerprints periodically
                deleted = self.deduplicator.cleanup()
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old fingerprints")

            if messages:
                # Generate summary
                summary = self.summarizer.summarize_news(messages)

                if summary:
                    # Post summary (to Telegram or file based on mode)
                    success = await self.output_writer.post_summary(summary)
                    if success:
                        logger.info("Summary posted successfully")
                    else:
                        logger.error("Failed to post summary")
                else:
                    logger.warning("Failed to generate summary")
            else:
                logger.info("No new messages to summarize")

            # Tell subscribers why the rhythm changed (in Persian), after the
            # summary so the notice never lands ahead of the news itself. Only a
            # genuine surge onset is announced; decay and mid-event re-escalation
            # reschedule the cadence silently (see CadenceDecision.is_surge_onset).
            if cadence_decision is not None and cadence_decision.is_surge_onset:
                await self._post_cadence_notice(cadence_decision)

            # Add new RSS article URLs to seen set (for deduplication)
            for msg in filtered_rss:
                if msg.url:
                    self._seen_urls.add(msg.url)

            # Update last check timestamp and save state
            self._last_check = datetime.now()
            self._save_last_check()
            self._save_seen_urls()

        except Exception as e:
            logger.error(f"Error in summarization job: {e}", exc_info=True)

    def _apply_adaptive_cadence(
        self, filtered_messages: list[Message], since: datetime
    ) -> CadenceDecision | None:
        """Feed the measured message rate into the cadence controller and reschedule.

        Uses the pre-dedup filtered count over the elapsed window so the rate is
        independent of the current interval and not coupled to the LLM dedup
        pipeline. Reschedules the summarize job only when the interval changes;
        the change takes effect from the next fire, not the current run. Returns
        the decision so the caller can announce the change to subscribers.
        """
        controller = self.cadence_controller
        if controller is None:
            return None

        elapsed_minutes = max((datetime.now() - since).total_seconds() / 60, 0.5)
        rate = len(filtered_messages) / elapsed_minutes

        decision = controller.record_and_compute(rate, radar_alert=self._recent_radar_alert)
        self._recent_radar_alert = False

        if decision.changed:
            self.scheduler.reschedule_job(
                "summarize_news", trigger="interval", minutes=decision.new_interval
            )
            logger.info(
                f"Adaptive cadence: {decision.previous_interval}min -> "
                f"{decision.new_interval}min "
                f"(level={controller.current_level.value}, rate={rate:.2f}/min)"
            )
        return decision

    async def _post_cadence_notice(self, decision: CadenceDecision) -> None:
        """Post the Persian cadence-change notice to all output channels."""
        notice = build_cadence_notice(decision)
        success = await self.output_writer.post_alert(notice)
        if success:
            logger.info(f"Posted cadence notice ({decision.reason})")
        else:
            logger.error("Failed to post cadence notice")

    async def _probe_intensity_job(self) -> None:
        """Cheap escalate-only probe to bound cold-start detection latency.

        Counts filtered messages over a short trailing window (no LLM, no dedup,
        no posting) and may tighten the summary cadence between full runs. It is
        strictly side-effect-free: it never mutates _seen_urls, advances
        _last_check, or summarizes. It can only escalate, never relax, leaving
        decay to the real summarize runs.
        """
        controller = self.cadence_controller
        if controller is None:
            return

        try:
            # Average the rate over a trailing window decoupled from how often
            # the probe runs. A window wider than the run cadence smooths bursty
            # arrival so a single message cluster is not misread as a surge
            # against the full-run baseline (which is itself a long-window rate).
            probe_window = self.config.adaptive_cadence.probe_window_minutes
            since = datetime.now() - timedelta(minutes=probe_window)

            telegram_messages = await self.telegram_reader.get_all_channel_updates(since)
            # Pass a throwaway empty set so the probe never mutates the real
            # seen-URL state that the next summarize run depends on.
            rss_messages = await self.rss_reader.get_all_feed_updates(since, seen_urls=set())

            filtered = self.iran_filter.filter_messages(
                telegram_messages
            ) + self.iran_filter.filter_messages(rss_messages)

            rate = len(filtered) / probe_window

            # Consume the radar flag here too so a one-shot outage cannot keep
            # re-promoting on every probe tick; whichever job runs first wins.
            radar_alert = self._recent_radar_alert
            self._recent_radar_alert = False
            decision = controller.consider_escalation(rate, radar_alert=radar_alert)
            if decision.changed:
                self.scheduler.reschedule_job(
                    "summarize_news", trigger="interval", minutes=decision.new_interval
                )
                logger.info(
                    f"Probe escalated cadence to {decision.new_interval}min "
                    f"(level={controller.current_level.value}, rate={rate:.2f}/min)"
                )
                if decision.is_surge_onset:
                    await self._post_cadence_notice(decision)

        except Exception as e:
            logger.error(f"Error in intensity probe job: {e}", exc_info=True)

    async def _check_radar_job(self) -> None:
        """Job that checks Cloudflare Radar for alerts."""
        if not self.radar_monitor:
            return

        try:
            logger.info("Checking Cloudflare Radar for alerts...")
            alerts = await self.radar_monitor.check_all()

            for alert in alerts:
                success = await self.output_writer.post_alert(alert.message)
                if success:
                    logger.info(f"Posted radar alert: {alert.alert_type.value}")
                else:
                    logger.error(f"Failed to post radar alert: {alert.alert_type.value}")

            if alerts:
                # An internet outage is a likely crisis signal; surface it to the
                # cadence controller on the next summarize run.
                self._recent_radar_alert = True
            else:
                logger.info("No radar alerts to send")

        except Exception as e:
            logger.error(f"Error in radar check job: {e}", exc_info=True)

    def _load_last_check(self) -> None:
        """Load the last check timestamp from file."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                self._last_check = datetime.fromisoformat(data["last_check"])
                logger.info(f"Loaded last check timestamp: {self._last_check}")
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Could not load last check timestamp: {e}")
                self._last_check = None

    def _save_last_check(self) -> None:
        """Save the last check timestamp to file."""
        if self._last_check:
            try:
                self._state_file.write_text(
                    json.dumps({"last_check": self._last_check.isoformat()})
                )
            except OSError as e:
                logger.warning(f"Could not save last check timestamp: {e}")

    def _load_seen_urls(self) -> None:
        """Load seen RSS article URLs from file."""
        if SEEN_URLS_FILE.exists():
            try:
                data = json.loads(SEEN_URLS_FILE.read_text())
                self._seen_urls = set(data.get("urls", []))
                logger.info(f"Loaded {len(self._seen_urls)} seen URLs")
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Could not load seen URLs: {e}")
                self._seen_urls = set()

    def _save_seen_urls(self) -> None:
        """Save seen RSS article URLs to file."""
        try:
            # Keep only the most recent URLs to prevent unbounded growth
            urls_to_save = list(self._seen_urls)[-MAX_SEEN_URLS:]
            SEEN_URLS_FILE.write_text(json.dumps({"urls": urls_to_save}))
        except OSError as e:
            logger.warning(f"Could not save seen URLs: {e}")


async def main() -> None:
    """Main entry point."""
    try:
        config = Config.from_env()
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    if not config.channels and not config.rss_feeds:
        logger.warning("No sources configured. Check config/channels.yaml")

    summarizer = NewsSummarizer(config)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Start the summarizer
    await summarizer.start()

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Stop the summarizer
    await summarizer.stop()


if __name__ == "__main__":
    asyncio.run(main())
