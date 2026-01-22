"""Cloudflare Radar monitoring for internet traffic anomalies."""

import json
import logging
from datetime import datetime
from pathlib import Path

import httpx

from src.config import Config
from src.models import (
    AlertType,
    Anomaly,
    AnomalyStatus,
    RadarAlert,
    TrafficChange,
    TrafficDataPoint,
)

logger = logging.getLogger(__name__)

# Cloudflare Radar API base URL
RADAR_API_BASE = "https://api.cloudflare.com/client/v4/radar"

# State file for persistence
RADAR_STATE_FILE = Path(".radar_state")


class CloudflareRadarMonitor:
    """Monitor Cloudflare Radar for traffic anomalies and changes."""

    def __init__(self, config: Config) -> None:
        """Initialize the radar monitor with configuration."""
        self.config = config
        self.api_token = config.cloudflare_api_token
        self.location = config.radar_monitor.location
        self.change_threshold = config.radar_monitor.change_threshold_percent
        self.cooldown_hours = config.radar_monitor.alert_cooldown_hours
        self._http_client: httpx.AsyncClient | None = None
        self._seen_anomaly_ids: set[str] = set()
        self._last_traffic_value: float | None = None
        self._last_alert_timestamp: datetime | None = None
        self._last_alert_direction: str | None = None  # "drop" or "spike"

    async def start(self) -> None:
        """Start the HTTP client and load state."""
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
        )
        self._load_state()
        logger.info(f"Cloudflare Radar monitor started for location: {self.location}")

    async def stop(self) -> None:
        """Stop the HTTP client and save state."""
        self._save_state()
        if self._http_client:
            await self._http_client.aclose()
            logger.info("Cloudflare Radar monitor stopped")

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not started."""
        if self._http_client is None:
            raise RuntimeError("CloudflareRadarMonitor not started. Call start() first.")
        return self._http_client

    async def get_cloudflare_anomalies(self) -> list[Anomaly]:
        """Fetch traffic anomalies from Cloudflare Radar API.

        Returns:
            List of traffic anomalies for the configured location.
        """
        anomalies: list[Anomaly] = []

        try:
            url = f"{RADAR_API_BASE}/traffic_anomalies"
            params = {
                "location": self.location,
                "dateRange": "7d",  # Look back 7 days for anomalies
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            result = data.get("result", {})
            traffic_anomalies = result.get("trafficAnomalies", [])

            for item in traffic_anomalies:
                try:
                    # Parse status string to enum
                    status_str = item.get("status", "UNVERIFIED")
                    try:
                        status = AnomalyStatus(status_str)
                    except ValueError:
                        status = AnomalyStatus.UNVERIFIED

                    # Parse end date (may be null for ongoing anomalies)
                    end_date_str = item.get("endDate")
                    end_date = None
                    if end_date_str:
                        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))

                    anomaly = Anomaly(
                        id=item.get("uuid", ""),
                        location=item.get("locationCode", self.location),
                        start_date=datetime.fromisoformat(
                            item.get("startDate", "").replace("Z", "+00:00")
                        ),
                        end_date=end_date,
                        status=status,
                        asn=item.get("asnNumber"),
                    )
                    anomalies.append(anomaly)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Error parsing anomaly: {e}")
                    continue

            logger.info(f"Found {len(anomalies)} traffic anomalies for {self.location}")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching anomalies: {e}")
        except Exception as e:
            logger.error(f"Error fetching anomalies: {e}")

        return anomalies

    async def get_traffic_timeseries(self, hours: int = 3) -> list[TrafficDataPoint]:
        """Fetch traffic timeseries data from Cloudflare Radar API.

        Args:
            hours: Number of hours of data to fetch (default: 3 for safety margin).

        Returns:
            List of traffic data points sorted by timestamp.
        """
        data_points: list[TrafficDataPoint] = []

        try:
            url = f"{RADAR_API_BASE}/http/timeseries"
            params = {
                "location": self.location,
                "aggInterval": "1h",
                "dateRange": f"{hours}h",
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            result = data.get("result", {})
            serie = result.get("serie_0", {})
            timestamps = serie.get("timestamps", [])
            values = serie.get("values", [])

            for ts, val in zip(timestamps, values, strict=False):
                try:
                    data_points.append(
                        TrafficDataPoint(
                            timestamp=datetime.fromisoformat(ts.replace("Z", "+00:00")),
                            value=float(val),
                        )
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing traffic data point: {e}")
                    continue

            # Sort by timestamp
            data_points.sort(key=lambda x: x.timestamp)
            logger.debug(f"Fetched {len(data_points)} traffic data points")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching traffic timeseries: {e}")
        except Exception as e:
            logger.error(f"Error fetching traffic timeseries: {e}")

        return data_points

    async def detect_traffic_change(self) -> TrafficChange | None:
        """Detect significant traffic changes between consecutive hours.

        Returns:
            TrafficChange if change exceeds threshold, None otherwise.
        """
        data_points = await self.get_traffic_timeseries(hours=3)

        if len(data_points) < 2:
            logger.warning("Not enough data points to detect traffic change")
            return None

        # Get the last two data points
        previous = data_points[-2]
        current = data_points[-1]

        # Avoid division by zero
        if previous.value == 0:
            logger.warning("Previous traffic value is zero, skipping change detection")
            return None

        # Calculate percentage change
        change_percent = ((current.value - previous.value) / previous.value) * 100

        logger.info(
            f"Traffic change: {previous.value:.4f} -> {current.value:.4f} "
            f"({change_percent:+.1f}%)"
        )

        # Check if change exceeds threshold
        if abs(change_percent) >= self.change_threshold:
            return TrafficChange(
                timestamp=current.timestamp,
                previous_value=previous.value,
                current_value=current.value,
                change_percent=change_percent,
            )

        return None

    async def check_all(self) -> list[RadarAlert]:
        """Check for all types of alerts (anomalies and traffic changes).

        Returns:
            List of alerts to be sent.
        """
        alerts: list[RadarAlert] = []

        # Check for Cloudflare anomalies
        anomalies = await self.get_cloudflare_anomalies()
        for anomaly in anomalies:
            # Skip already-seen anomalies
            if anomaly.id in self._seen_anomaly_ids:
                continue

            # Skip false positives
            if anomaly.status == AnomalyStatus.FALSE_POSITIVE:
                continue

            # Create alert
            alert = RadarAlert(
                alert_type=AlertType.CLOUDFLARE_ANOMALY,
                location=anomaly.location,
                timestamp=anomaly.start_date,
                message=format_anomaly_alert(anomaly),
                anomaly_id=anomaly.id,
            )
            alerts.append(alert)

            # Mark as seen
            self._seen_anomaly_ids.add(anomaly.id)
            logger.info(f"New Cloudflare anomaly detected: {anomaly.id}")

        # Check for traffic changes
        traffic_change = await self.detect_traffic_change()
        if traffic_change:
            # Check cooldown (optional)
            should_alert = True
            if self.cooldown_hours > 0 and self._last_alert_timestamp:
                hours_since_last = (
                    datetime.now() - self._last_alert_timestamp
                ).total_seconds() / 3600
                direction = "drop" if traffic_change.is_drop else "spike"
                if (
                    hours_since_last < self.cooldown_hours
                    and direction == self._last_alert_direction
                ):
                    should_alert = False
                    logger.info(
                        f"Skipping alert due to cooldown "
                        f"({hours_since_last:.1f}h < {self.cooldown_hours}h)"
                    )

            if should_alert:
                alert = RadarAlert(
                    alert_type=AlertType.TRAFFIC_CHANGE,
                    location=self.location,
                    timestamp=traffic_change.timestamp,
                    message=format_traffic_change_alert(traffic_change, self.location),
                    change_percent=traffic_change.change_percent,
                )
                alerts.append(alert)

                # Update last alert tracking
                self._last_alert_timestamp = datetime.now()
                self._last_alert_direction = "drop" if traffic_change.is_drop else "spike"
                logger.info(
                    f"Traffic change alert: {traffic_change.change_percent:+.1f}%"
                )

        # Save state after checking
        self._save_state()

        return alerts

    def _load_state(self) -> None:
        """Load state from file."""
        if RADAR_STATE_FILE.exists():
            try:
                data = json.loads(RADAR_STATE_FILE.read_text())
                self._seen_anomaly_ids = set(data.get("seen_anomaly_ids", []))
                self._last_traffic_value = data.get("last_traffic_value")
                if data.get("last_alert_timestamp"):
                    self._last_alert_timestamp = datetime.fromisoformat(
                        data["last_alert_timestamp"]
                    )
                self._last_alert_direction = data.get("last_alert_direction")
                logger.info(
                    f"Loaded radar state: {len(self._seen_anomaly_ids)} seen anomalies"
                )
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Could not load radar state: {e}")

    def _save_state(self) -> None:
        """Save state to file."""
        try:
            # Keep only recent anomaly IDs (last 100)
            recent_ids = list(self._seen_anomaly_ids)[-100:]
            data = {
                "seen_anomaly_ids": recent_ids,
                "last_traffic_value": self._last_traffic_value,
                "last_alert_timestamp": (
                    self._last_alert_timestamp.isoformat()
                    if self._last_alert_timestamp
                    else None
                ),
                "last_alert_direction": self._last_alert_direction,
            }
            RADAR_STATE_FILE.write_text(json.dumps(data, indent=2))
        except OSError as e:
            logger.warning(f"Could not save radar state: {e}")


def format_anomaly_alert(anomaly: Anomaly) -> str:
    """Format a Cloudflare anomaly as a Telegram alert message."""
    return f"""⚠️ هشدار: اختلال اینترنت در ایران
🔴 Cloudflare Anomaly Detected - {anomaly.location}

📅 زمان: {anomaly.start_date.strftime("%Y-%m-%d %H:%M")} UTC

🔗 https://radar.cloudflare.com/{anomaly.location.lower()}
#InternetOutage #Iran"""


def format_traffic_change_alert(change: TrafficChange, location: str) -> str:
    """Format a traffic change as a Telegram alert message."""
    if change.is_drop:
        return f"""⚠️ هشدار: کاهش ترافیک اینترنت ایران
📉 Iran Internet Traffic DROPPED by {abs(change.change_percent):.1f}%

📅 زمان: {change.timestamp.strftime("%Y-%m-%d %H:%M")} UTC
📊 کاهش {abs(change.change_percent):.1f}% نسبت به ساعت قبل

🔗 https://radar.cloudflare.com/{location.lower()}
#InternetOutage #Iran"""
    else:
        return f"""✅ بهبود: افزایش ترافیک اینترنت ایران
📈 Iran Internet Traffic INCREASED by {abs(change.change_percent):.1f}%

📅 زمان: {change.timestamp.strftime("%Y-%m-%d %H:%M")} UTC
📊 افزایش {abs(change.change_percent):.1f}% نسبت به ساعت قبل

🔗 https://radar.cloudflare.com/{location.lower()}
#InternetRecovery #Iran"""
