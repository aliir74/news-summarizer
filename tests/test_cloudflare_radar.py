"""Tests for the Cloudflare Radar monitor."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.cloudflare_radar import (
    CloudflareRadarMonitor,
    format_anomaly_alert,
    format_traffic_change_alert,
)
from src.config import Config
from src.models import AlertType, Anomaly, AnomalyStatus, TrafficChange


class TestCloudflareRadarMonitor:
    """Tests for CloudflareRadarMonitor class."""

    async def test_start_creates_client(self, radar_config: Config) -> None:
        """Test that start() creates an HTTP client."""
        monitor = CloudflareRadarMonitor(radar_config)
        await monitor.start()

        assert monitor._http_client is not None
        await monitor.stop()

    async def test_stop_closes_client(self, radar_config: Config) -> None:
        """Test that stop() closes the HTTP client."""
        monitor = CloudflareRadarMonitor(radar_config)
        await monitor.start()
        await monitor.stop()

        assert monitor._http_client is not None

    def test_client_property_raises_when_not_started(
        self, radar_config: Config
    ) -> None:
        """Test that accessing client raises when not started."""
        monitor = CloudflareRadarMonitor(radar_config)

        with pytest.raises(RuntimeError, match="not started"):
            _ = monitor.client

    async def test_get_cloudflare_anomalies_parses_response(
        self, radar_config: Config, sample_anomalies_api_response: dict
    ) -> None:
        """Test parsing Cloudflare anomalies API response."""
        monitor = CloudflareRadarMonitor(radar_config)

        mock_response = MagicMock()
        mock_response.json.return_value = sample_anomalies_api_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(monitor, "_http_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            monitor._http_client = mock_client

            anomalies = await monitor.get_cloudflare_anomalies()

            assert len(anomalies) == 2
            assert anomalies[0].id == "anomaly-123"
            assert anomalies[0].location == "IR"
            assert anomalies[0].status == AnomalyStatus.UNVERIFIED
            assert anomalies[1].status == AnomalyStatus.VERIFIED
            assert anomalies[1].asn == 12345

    async def test_get_cloudflare_anomalies_handles_http_error(
        self, radar_config: Config
    ) -> None:
        """Test graceful handling of HTTP errors."""
        monitor = CloudflareRadarMonitor(radar_config)

        with patch.object(monitor, "_http_client") as mock_client:
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )
            monitor._http_client = mock_client

            anomalies = await monitor.get_cloudflare_anomalies()

            assert anomalies == []

    async def test_get_traffic_timeseries_parses_response(
        self, radar_config: Config, sample_timeseries_api_response: dict
    ) -> None:
        """Test parsing traffic timeseries API response."""
        monitor = CloudflareRadarMonitor(radar_config)

        mock_response = MagicMock()
        mock_response.json.return_value = sample_timeseries_api_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(monitor, "_http_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            monitor._http_client = mock_client

            data_points = await monitor.get_traffic_timeseries(hours=3)

            assert len(data_points) == 3
            assert data_points[0].value == 0.85
            assert data_points[1].value == 0.90
            assert data_points[2].value == 0.80

    async def test_get_traffic_timeseries_handles_http_error(
        self, radar_config: Config
    ) -> None:
        """Test graceful handling of HTTP errors in timeseries."""
        monitor = CloudflareRadarMonitor(radar_config)

        with patch.object(monitor, "_http_client") as mock_client:
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )
            monitor._http_client = mock_client

            data_points = await monitor.get_traffic_timeseries()

            assert data_points == []

    async def test_detect_traffic_change_detects_drop(
        self, radar_config: Config, sample_timeseries_drop_response: dict
    ) -> None:
        """Test detection of significant traffic drop."""
        monitor = CloudflareRadarMonitor(radar_config)

        mock_response = MagicMock()
        mock_response.json.return_value = sample_timeseries_drop_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(monitor, "_http_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            monitor._http_client = mock_client

            change = await monitor.detect_traffic_change()

            assert change is not None
            assert change.is_drop
            assert not change.is_spike
            assert change.change_percent < -5.0  # More than 5% drop

    async def test_detect_traffic_change_detects_spike(
        self, radar_config: Config, sample_timeseries_spike_response: dict
    ) -> None:
        """Test detection of significant traffic increase."""
        monitor = CloudflareRadarMonitor(radar_config)

        mock_response = MagicMock()
        mock_response.json.return_value = sample_timeseries_spike_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(monitor, "_http_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            monitor._http_client = mock_client

            change = await monitor.detect_traffic_change()

            assert change is not None
            assert change.is_spike
            assert not change.is_drop
            assert change.change_percent > 5.0  # More than 5% increase

    async def test_detect_traffic_change_returns_none_for_stable(
        self, radar_config: Config, sample_timeseries_stable_response: dict
    ) -> None:
        """Test that stable traffic returns None."""
        monitor = CloudflareRadarMonitor(radar_config)

        mock_response = MagicMock()
        mock_response.json.return_value = sample_timeseries_stable_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(monitor, "_http_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            monitor._http_client = mock_client

            change = await monitor.detect_traffic_change()

            assert change is None  # Below 5% threshold

    async def test_detect_traffic_change_returns_none_for_insufficient_data(
        self, radar_config: Config
    ) -> None:
        """Test that insufficient data returns None."""
        monitor = CloudflareRadarMonitor(radar_config)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"serie_0": {"timestamps": [], "values": []}}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(monitor, "_http_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            monitor._http_client = mock_client

            change = await monitor.detect_traffic_change()

            assert change is None

    async def test_check_all_returns_new_anomaly_alerts(
        self,
        radar_config: Config,
        sample_anomalies_api_response: dict,
        sample_timeseries_stable_response: dict,
    ) -> None:
        """Test that check_all returns alerts for new anomalies."""
        monitor = CloudflareRadarMonitor(radar_config)

        anomaly_response = MagicMock()
        anomaly_response.json.return_value = sample_anomalies_api_response
        anomaly_response.raise_for_status = MagicMock()

        timeseries_response = MagicMock()
        timeseries_response.json.return_value = sample_timeseries_stable_response
        timeseries_response.raise_for_status = MagicMock()

        with patch.object(monitor, "_http_client") as mock_client:

            async def mock_get(url: str, **_: object) -> MagicMock:
                if "traffic_anomalies" in url:
                    return anomaly_response
                return timeseries_response

            mock_client.get = AsyncMock(side_effect=mock_get)
            monitor._http_client = mock_client

            alerts = await monitor.check_all()

            # Should have 2 anomaly alerts (no traffic change since stable)
            anomaly_alerts = [
                a for a in alerts if a.alert_type == AlertType.CLOUDFLARE_ANOMALY
            ]
            assert len(anomaly_alerts) == 2

    async def test_check_all_deduplicates_anomalies(
        self,
        radar_config: Config,
        sample_anomalies_api_response: dict,
        sample_timeseries_stable_response: dict,
    ) -> None:
        """Test that check_all doesn't return duplicate anomaly alerts."""
        monitor = CloudflareRadarMonitor(radar_config)

        # Mark first anomaly as already seen
        monitor._seen_anomaly_ids.add("anomaly-123")

        anomaly_response = MagicMock()
        anomaly_response.json.return_value = sample_anomalies_api_response
        anomaly_response.raise_for_status = MagicMock()

        timeseries_response = MagicMock()
        timeseries_response.json.return_value = sample_timeseries_stable_response
        timeseries_response.raise_for_status = MagicMock()

        with patch.object(monitor, "_http_client") as mock_client:

            async def mock_get(url: str, **_: object) -> MagicMock:
                if "traffic_anomalies" in url:
                    return anomaly_response
                return timeseries_response

            mock_client.get = AsyncMock(side_effect=mock_get)
            monitor._http_client = mock_client

            alerts = await monitor.check_all()

            # Should only have 1 anomaly alert (anomaly-123 was already seen)
            anomaly_alerts = [
                a for a in alerts if a.alert_type == AlertType.CLOUDFLARE_ANOMALY
            ]
            assert len(anomaly_alerts) == 1
            assert anomaly_alerts[0].anomaly_id == "anomaly-456"

    async def test_check_all_returns_traffic_change_alerts(
        self,
        radar_config: Config,
        sample_timeseries_drop_response: dict,
    ) -> None:
        """Test that check_all returns traffic change alerts."""
        monitor = CloudflareRadarMonitor(radar_config)

        anomaly_response = MagicMock()
        anomaly_response.json.return_value = {"result": {"trafficAnomalies": []}}
        anomaly_response.raise_for_status = MagicMock()

        timeseries_response = MagicMock()
        timeseries_response.json.return_value = sample_timeseries_drop_response
        timeseries_response.raise_for_status = MagicMock()

        with patch.object(monitor, "_http_client") as mock_client:

            async def mock_get(url: str, **_: object) -> MagicMock:
                if "traffic_anomalies" in url:
                    return anomaly_response
                return timeseries_response

            mock_client.get = AsyncMock(side_effect=mock_get)
            monitor._http_client = mock_client

            alerts = await monitor.check_all()

            # Should have 1 traffic change alert
            change_alerts = [
                a for a in alerts if a.alert_type == AlertType.TRAFFIC_CHANGE
            ]
            assert len(change_alerts) == 1
            assert change_alerts[0].change_percent is not None
            assert change_alerts[0].change_percent < 0  # Drop

    def test_state_persistence(
        self, radar_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that state is correctly saved and loaded."""
        # Use temp file for state
        state_file = tmp_path / ".radar_state"
        monkeypatch.setattr(
            "src.cloudflare_radar.RADAR_STATE_FILE", state_file
        )

        monitor = CloudflareRadarMonitor(radar_config)
        monitor._seen_anomaly_ids = {"anomaly-1", "anomaly-2"}
        monitor._last_traffic_value = 0.85
        monitor._last_alert_timestamp = datetime(2024, 1, 15, 10, 0)
        monitor._last_alert_direction = "drop"

        # Save state
        monitor._save_state()

        # Create new monitor and load state
        monitor2 = CloudflareRadarMonitor(radar_config)
        monitor2._load_state()

        assert "anomaly-1" in monitor2._seen_anomaly_ids
        assert "anomaly-2" in monitor2._seen_anomaly_ids
        assert monitor2._last_alert_direction == "drop"


class TestCloudflareRadarCoverage:
    """Tests for radar error paths and edge cases (coverage completeness)."""

    def _monitor_with_get(
        self, radar_config: Config, response: MagicMock
    ) -> CloudflareRadarMonitor:
        """Build a monitor whose HTTP client returns the given response."""
        monitor = CloudflareRadarMonitor(radar_config)
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=response)
        monitor._http_client = mock_client
        return monitor

    async def test_anomaly_invalid_status_falls_back_to_unverified(
        self, radar_config: Config
    ) -> None:
        """An unrecognized status string is parsed as UNVERIFIED."""
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "result": {
                "trafficAnomalies": [
                    {
                        "uuid": "a-1",
                        "locationCode": "IR",
                        "startDate": "2024-01-15T10:00:00Z",
                        "endDate": None,
                        "status": "TOTALLY_UNKNOWN",
                        "asnNumber": None,
                    }
                ]
            }
        }
        monitor = self._monitor_with_get(radar_config, response)

        anomalies = await monitor.get_cloudflare_anomalies()

        assert len(anomalies) == 1
        assert anomalies[0].status == AnomalyStatus.UNVERIFIED

    async def test_anomaly_unparseable_item_is_skipped(
        self, radar_config: Config
    ) -> None:
        """An anomaly with an unparseable startDate is skipped, not fatal."""
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "result": {
                "trafficAnomalies": [
                    {
                        "uuid": "bad",
                        "locationCode": "IR",
                        "startDate": "not-a-date",
                        "status": "UNVERIFIED",
                    }
                ]
            }
        }
        monitor = self._monitor_with_get(radar_config, response)

        anomalies = await monitor.get_cloudflare_anomalies()

        assert anomalies == []

    async def test_anomaly_generic_exception_returns_empty(
        self, radar_config: Config
    ) -> None:
        """A non-HTTP error while fetching anomalies returns an empty list."""
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.side_effect = RuntimeError("boom")
        monitor = self._monitor_with_get(radar_config, response)

        anomalies = await monitor.get_cloudflare_anomalies()

        assert anomalies == []

    async def test_timeseries_unparseable_point_is_skipped(
        self, radar_config: Config
    ) -> None:
        """A traffic data point with a null value is skipped."""
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "result": {
                "serie_0": {
                    "timestamps": ["2024-01-15T10:00:00Z", "2024-01-15T11:00:00Z"],
                    "values": [None, 0.9],
                }
            }
        }
        monitor = self._monitor_with_get(radar_config, response)

        data_points = await monitor.get_traffic_timeseries()

        assert len(data_points) == 1
        assert data_points[0].value == 0.9

    async def test_timeseries_generic_exception_returns_empty(
        self, radar_config: Config
    ) -> None:
        """A non-HTTP error while fetching the timeseries returns an empty list."""
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.side_effect = RuntimeError("boom")
        monitor = self._monitor_with_get(radar_config, response)

        data_points = await monitor.get_traffic_timeseries()

        assert data_points == []

    async def test_detect_traffic_change_skips_zero_previous(
        self, radar_config: Config
    ) -> None:
        """A zero previous value short-circuits change detection (no div-by-zero)."""
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "result": {
                "serie_0": {
                    "timestamps": ["2024-01-15T10:00:00Z", "2024-01-15T11:00:00Z"],
                    "values": [0.0, 0.5],
                }
            }
        }
        monitor = self._monitor_with_get(radar_config, response)

        change = await monitor.detect_traffic_change()

        assert change is None

    async def test_check_all_skips_false_positive_anomaly(
        self, radar_config: Config, sample_timeseries_stable_response: dict
    ) -> None:
        """A FALSE_POSITIVE anomaly produces no alert."""
        monitor = CloudflareRadarMonitor(radar_config)

        anomaly_response = MagicMock()
        anomaly_response.raise_for_status = MagicMock()
        anomaly_response.json.return_value = {
            "result": {
                "trafficAnomalies": [
                    {
                        "uuid": "fp-1",
                        "locationCode": "IR",
                        "startDate": "2024-01-15T10:00:00Z",
                        "endDate": None,
                        "status": "FALSE_POSITIVE",
                        "asnNumber": None,
                    }
                ]
            }
        }
        timeseries_response = MagicMock()
        timeseries_response.raise_for_status = MagicMock()
        timeseries_response.json.return_value = sample_timeseries_stable_response

        mock_client = MagicMock()

        async def mock_get(url: str, **_: object) -> MagicMock:
            if "traffic_anomalies" in url:
                return anomaly_response
            return timeseries_response

        mock_client.get = AsyncMock(side_effect=mock_get)
        monitor._http_client = mock_client

        alerts = await monitor.check_all()

        assert alerts == []

    async def test_check_all_respects_cooldown(
        self, radar_config: Config, sample_timeseries_drop_response: dict
    ) -> None:
        """A recent same-direction alert within the cooldown is suppressed."""
        cooldown_config = replace(
            radar_config,
            radar_monitor=replace(radar_config.radar_monitor, alert_cooldown_hours=6),
        )
        monitor = CloudflareRadarMonitor(cooldown_config)
        monitor._last_alert_timestamp = datetime.now()
        monitor._last_alert_direction = "drop"

        anomaly_response = MagicMock()
        anomaly_response.raise_for_status = MagicMock()
        anomaly_response.json.return_value = {"result": {"trafficAnomalies": []}}
        timeseries_response = MagicMock()
        timeseries_response.raise_for_status = MagicMock()
        timeseries_response.json.return_value = sample_timeseries_drop_response

        mock_client = MagicMock()

        async def mock_get(url: str, **_: object) -> MagicMock:
            if "traffic_anomalies" in url:
                return anomaly_response
            return timeseries_response

        mock_client.get = AsyncMock(side_effect=mock_get)
        monitor._http_client = mock_client

        alerts = await monitor.check_all()

        change_alerts = [a for a in alerts if a.alert_type == AlertType.TRAFFIC_CHANGE]
        assert change_alerts == []

    def test_load_state_handles_invalid_json(
        self, radar_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid radar state JSON is logged and ignored, not fatal."""
        state_file = tmp_path / ".radar_state"
        state_file.write_text("not valid json")
        monkeypatch.setattr("src.cloudflare_radar.RADAR_STATE_FILE", state_file)

        monitor = CloudflareRadarMonitor(radar_config)
        monitor._load_state()  # Should not raise.

        assert monitor._seen_anomaly_ids == set()

    def test_save_state_handles_os_error(
        self, radar_config: Config, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An OSError while writing radar state is swallowed with a warning."""
        fake_path = MagicMock()
        fake_path.write_text.side_effect = OSError("disk full")
        monkeypatch.setattr("src.cloudflare_radar.RADAR_STATE_FILE", fake_path)

        monitor = CloudflareRadarMonitor(radar_config)
        monitor._save_state()  # Should not raise.

        fake_path.write_text.assert_called_once()


class TestFormatAnomalyAlert:
    """Tests for format_anomaly_alert function."""

    def test_format_anomaly_alert(self, sample_anomaly: Anomaly) -> None:
        """Test formatting of anomaly alert."""
        message = format_anomaly_alert(sample_anomaly)

        assert "هشدار" in message  # Persian for "warning"
        assert "Cloudflare Anomaly Detected" in message
        assert "IR" in message
        assert "radar.cloudflare.com" in message
        assert "#InternetOutage" in message

    def test_format_anomaly_alert_includes_timestamp(
        self, sample_anomaly: Anomaly
    ) -> None:
        """Test that anomaly alert includes timestamp."""
        message = format_anomaly_alert(sample_anomaly)

        assert "2024-01-15" in message


class TestFormatTrafficChangeAlert:
    """Tests for format_traffic_change_alert function."""

    def test_format_traffic_drop_alert(self) -> None:
        """Test formatting of traffic drop alert."""
        change = TrafficChange(
            timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            previous_value=0.90,
            current_value=0.80,
            change_percent=-11.1,
        )

        message = format_traffic_change_alert(change, "IR")

        assert "هشدار" in message  # Persian for "warning"
        assert "DROPPED" in message
        assert "11.1%" in message
        assert "کاهش" in message  # Persian for "decrease"
        assert "#InternetOutage" in message

    def test_format_traffic_spike_alert(self) -> None:
        """Test formatting of traffic increase alert."""
        change = TrafficChange(
            timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            previous_value=0.80,
            current_value=0.90,
            change_percent=12.5,
        )

        message = format_traffic_change_alert(change, "IR")

        assert "بهبود" in message  # Persian for "improvement"
        assert "INCREASED" in message
        assert "12.5%" in message
        assert "افزایش" in message  # Persian for "increase"
        assert "#InternetRecovery" in message

    def test_format_traffic_alert_includes_radar_link(self) -> None:
        """Test that traffic alert includes Cloudflare Radar link."""
        change = TrafficChange(
            timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            previous_value=0.90,
            current_value=0.80,
            change_percent=-11.1,
        )

        message = format_traffic_change_alert(change, "IR")

        assert "radar.cloudflare.com/ir" in message


class TestTrafficChangeModel:
    """Tests for TrafficChange model properties."""

    def test_is_drop_property(self) -> None:
        """Test is_drop property for negative change."""
        change = TrafficChange(
            timestamp=datetime(2024, 1, 15, 10, 0),
            previous_value=0.90,
            current_value=0.80,
            change_percent=-11.1,
        )

        assert change.is_drop
        assert not change.is_spike

    def test_is_spike_property(self) -> None:
        """Test is_spike property for positive change."""
        change = TrafficChange(
            timestamp=datetime(2024, 1, 15, 10, 0),
            previous_value=0.80,
            current_value=0.90,
            change_percent=12.5,
        )

        assert change.is_spike
        assert not change.is_drop

    def test_zero_change(self) -> None:
        """Test properties for zero change."""
        change = TrafficChange(
            timestamp=datetime(2024, 1, 15, 10, 0),
            previous_value=0.85,
            current_value=0.85,
            change_percent=0.0,
        )

        assert not change.is_drop
        assert not change.is_spike
