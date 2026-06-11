"""Tests for the adaptive cadence controller."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.cadence import (
    AdaptiveCadenceController,
    CadenceChangeReason,
    CadenceDecision,
    IntensityLevel,
)
from src.config import Config


class TestIntensityLevel:
    """Tests for the IntensityLevel enum."""

    def test_string_values(self) -> None:
        """Test the enum has the expected string values."""
        assert IntensityLevel.NORMAL.value == "NORMAL"
        assert IntensityLevel.ELEVATED.value == "ELEVATED"
        assert IntensityLevel.SURGE.value == "SURGE"

    def test_severity_ordering(self) -> None:
        """Test levels have an explicit severity order for comparison."""
        assert IntensityLevel.NORMAL.severity < IntensityLevel.ELEVATED.severity
        assert IntensityLevel.ELEVATED.severity < IntensityLevel.SURGE.severity


class TestControllerInit:
    """Tests for AdaptiveCadenceController initialization."""

    def test_initializes_to_baseline(self, cadence_config: Config) -> None:
        """Test a fresh controller starts at the baseline interval, empty window."""
        controller = AdaptiveCadenceController(cadence_config)

        assert controller.current_interval == cadence_config.summary_interval_minutes
        assert controller.current_level == IntensityLevel.NORMAL
        assert controller._rate_window == []

    def test_baseline_uses_prod_interval_not_test(self, cadence_config: Config) -> None:
        """Test the baseline is summary_interval_minutes (not the test interval)."""
        controller = AdaptiveCadenceController(cadence_config)

        assert controller._baseline_interval == 30


class TestStatePersistence:
    """Tests for cadence state save/load round-trip."""

    def test_state_round_trip(
        self, cadence_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test the rate window, interval, and level round-trip through disk."""
        state_file = tmp_path / ".cadence_state"
        monkeypatch.setattr("src.cadence.CADENCE_STATE_FILE", state_file)

        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [0.5, 1.2, 3.4]
        controller._current_interval = 7
        controller._current_level = IntensityLevel.ELEVATED
        controller._calm_streak = 1
        controller._save_state()

        loaded = AdaptiveCadenceController(cadence_config)
        loaded._load_state()

        assert loaded._rate_window == [0.5, 1.2, 3.4]
        assert loaded.current_interval == 7
        assert loaded.current_level == IntensityLevel.ELEVATED
        assert loaded._calm_streak == 1

    def test_load_missing_file_keeps_defaults(
        self, cadence_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading when no state file exists leaves defaults intact."""
        state_file = tmp_path / ".cadence_state"
        monkeypatch.setattr("src.cadence.CADENCE_STATE_FILE", state_file)

        controller = AdaptiveCadenceController(cadence_config)
        controller._load_state()

        assert controller.current_interval == 30
        assert controller._rate_window == []

    def test_load_corrupt_file_keeps_defaults(
        self, cadence_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading a corrupt state file degrades gracefully."""
        state_file = tmp_path / ".cadence_state"
        state_file.write_text("not json {{{")
        monkeypatch.setattr("src.cadence.CADENCE_STATE_FILE", state_file)

        controller = AdaptiveCadenceController(cadence_config)
        controller._load_state()

        assert controller.current_interval == 30

    def test_load_invalid_level_falls_back_to_normal(
        self, cadence_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unrecognized level string in state loads as NORMAL."""
        state_file = tmp_path / ".cadence_state"
        state_file.write_text(
            '{"rate_window": [0.2], "current_interval": 12, '
            '"calm_streak": 0, "current_level": "BOGUS"}'
        )
        monkeypatch.setattr("src.cadence.CADENCE_STATE_FILE", state_file)

        controller = AdaptiveCadenceController(cadence_config)
        controller._load_state()

        assert controller.current_level == IntensityLevel.NORMAL
        assert controller.current_interval == 12

    def test_save_state_handles_os_error(
        self, cadence_config: Config, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An OSError while saving cadence state is swallowed with a warning."""
        fake_path = MagicMock()
        fake_path.write_text.side_effect = OSError("disk full")
        monkeypatch.setattr("src.cadence.CADENCE_STATE_FILE", fake_path)

        controller = AdaptiveCadenceController(cadence_config)
        controller._save_state()  # Should not raise.

        fake_path.write_text.assert_called_once()


class TestBaseline:
    """Tests for the rate baseline computation."""

    def test_empty_window_returns_floor(self, cadence_config: Config) -> None:
        """Test the baseline is the configured floor when no history exists."""
        controller = AdaptiveCadenceController(cadence_config)

        assert controller._baseline() == pytest.approx(0.1)

    def test_median_of_window(self, cadence_config: Config) -> None:
        """Test the baseline is the median of the rate window."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 2.0, 3.0]

        assert controller._baseline() == pytest.approx(2.0)

    def test_floor_applies_to_near_zero_history(self, cadence_config: Config) -> None:
        """Test a near-zero history is floored so a trickle is not a surge."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [0.0, 0.0, 0.0]

        assert controller._baseline() == pytest.approx(0.1)


class TestComputeLevel:
    """Tests for intensity level computation from a message rate."""

    def test_empty_window_returns_normal(self, cadence_config: Config) -> None:
        """Test no baseline history means NORMAL regardless of the rate."""
        controller = AdaptiveCadenceController(cadence_config)

        level = controller._compute_level(10.0, radar_alert=False)

        assert level == IntensityLevel.NORMAL

    def test_surge_when_rate_exceeds_surge_ratio(self, cadence_config: Config) -> None:
        """Test a rate at/above surge_ratio * baseline returns SURGE."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]  # baseline 1.0

        level = controller._compute_level(4.0, radar_alert=False)

        assert level == IntensityLevel.SURGE

    def test_elevated_and_normal_bands(self, cadence_config: Config) -> None:
        """Test the ELEVATED and NORMAL bands relative to the baseline."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]  # baseline 1.0

        assert controller._compute_level(2.0, radar_alert=False) == IntensityLevel.ELEVATED
        assert controller._compute_level(1.0, radar_alert=False) == IntensityLevel.NORMAL

    def test_floor_prevents_trickle_surge(self, cadence_config: Config) -> None:
        """Test a trickle against a near-zero history does not surge (floor)."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [0.0, 0.0, 0.0]  # baseline floored to 0.1

        # 0.2 / 0.1 = 2.0 => ELEVATED, not SURGE.
        level = controller._compute_level(0.2, radar_alert=False)

        assert level == IntensityLevel.ELEVATED

    def test_low_rate_never_surges_regardless_of_text(self, cadence_config: Config) -> None:
        """Regression: a trickle (0.05/min) must never read as SURGE.

        War vocabulary is the steady state of these sources; only volume vs the
        baseline (plus radar) may escalate. The VPS false-surge bug was a single
        keyword hit pinning SURGE at 0.01-0.06 msg/min.
        """
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [0.05, 0.05, 0.05, 0.05, 0.05]

        level = controller._compute_level(0.05, radar_alert=False)

        assert level == IntensityLevel.NORMAL

    def _config_with_floors(self, cadence_config: Config) -> Config:
        """Return a config whose level floors match production (0.75 / 1.5)."""
        return replace(
            cadence_config,
            adaptive_cadence=replace(
                cadence_config.adaptive_cadence,
                elevated_floor_rate=0.75,
                surge_floor_rate=1.5,
            ),
        )

    def test_absolute_floor_blocks_false_surge(self, cadence_config: Config) -> None:
        """A rate clearing the ratio but below the surge floor is not a SURGE.

        Reproduces the VPS noise: against a near-zero floored baseline (0.1),
        0.4 msg/min clears the 4x surge ratio but is ordinary traffic, so the
        1.5 msg/min surge floor must keep it out of SURGE.
        """
        controller = AdaptiveCadenceController(self._config_with_floors(cadence_config))
        controller._rate_window = [0.0, 0.0, 0.0]  # baseline floored to 0.1

        # 0.4 / 0.1 = 4.0 clears surge_ratio, but 0.4 < surge_floor_rate (1.5)
        # and 0.4 < elevated_floor_rate (0.75) => NORMAL.
        assert controller._compute_level(0.4, radar_alert=False) == IntensityLevel.NORMAL

    def test_absolute_floor_degrades_surge_to_elevated(self, cadence_config: Config) -> None:
        """A rate past the surge ratio + elevated floor but below the surge floor is ELEVATED."""
        controller = AdaptiveCadenceController(self._config_with_floors(cadence_config))
        controller._rate_window = [0.25, 0.25, 0.25]  # baseline floored to 0.25

        # 1.0 / 0.25 = 4.0 clears surge_ratio, but 1.0 < surge_floor_rate (1.5)
        # while 1.0 >= elevated_floor_rate (0.75) => ELEVATED.
        assert controller._compute_level(1.0, radar_alert=False) == IntensityLevel.ELEVATED

    def test_genuine_surge_clears_ratio_and_floor(self, cadence_config: Config) -> None:
        """A high-volume event clearing both the surge ratio and floor is a SURGE."""
        controller = AdaptiveCadenceController(self._config_with_floors(cadence_config))
        controller._rate_window = [0.5, 0.5, 0.5]  # baseline 0.5

        # 2.0 / 0.5 = 4.0 clears surge_ratio and 2.0 >= surge_floor_rate (1.5).
        assert controller._compute_level(2.0, radar_alert=False) == IntensityLevel.SURGE

    def test_radar_promotes_one_level(self, cadence_config: Config) -> None:
        """Test a radar outage flag bumps the level up by one step."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

        # NORMAL rate + radar => ELEVATED.
        assert controller._compute_level(1.0, radar_alert=True) == IntensityLevel.ELEVATED
        # ELEVATED rate + radar => SURGE.
        assert controller._compute_level(2.0, radar_alert=True) == IntensityLevel.SURGE


class TestRecordAndCompute:
    """Tests for the full record_and_compute escalate/decay path."""

    def _seed_baseline(self, controller: AdaptiveCadenceController) -> None:
        """Seed a baseline rate of 1.0 messages per minute."""
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

    def test_escalates_immediately_to_surge(self, cadence_config: Config) -> None:
        """Test a surge-level rate snaps straight to the floor interval."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        decision = controller.record_and_compute(4.0)

        assert decision.new_interval == 5  # min_interval_minutes
        assert controller.current_interval == 5
        assert controller.current_level == IntensityLevel.SURGE

    def test_escalates_to_elevated_half_interval(self, cadence_config: Config) -> None:
        """Test an elevated rate snaps to roughly half the baseline interval."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        decision = controller.record_and_compute(2.0)  # ratio 2.0 => ELEVATED

        assert decision.new_interval == 15  # round(30 / 2)
        assert controller.current_level == IntensityLevel.ELEVATED

    def test_returns_decision_with_int_interval(self, cadence_config: Config) -> None:
        """Test the decision carries an int interval (APScheduler minutes)."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        decision = controller.record_and_compute(4.0)

        assert isinstance(decision, CadenceDecision)
        assert isinstance(decision.new_interval, int)

    def test_decays_gradually_without_overshoot(self, cadence_config: Config) -> None:
        """Test calming grows the interval step by step, capped at baseline."""
        controller = AdaptiveCadenceController(cadence_config)
        controller.config.calm_streak_runs = 1  # isolate the decay-step math
        self._seed_baseline(controller)
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        intervals = [controller.record_and_compute(1.0).new_interval for _ in range(6)]

        # Strictly increasing toward the baseline, never overshooting it.
        assert intervals[0] == 8  # round(5 * 1.5)
        assert all(a <= b for a, b in zip(intervals, intervals[1:], strict=False))
        assert max(intervals) == 30  # baseline ceiling
        assert all(i <= 30 for i in intervals)

    def test_decay_doubles_each_step_to_baseline(self, cadence_config: Config) -> None:
        """Decay steps roughly double (30->60->120->240->360), not crawl by ~25%.

        Production uses decay_factor=2.0 so a surge unwinds in a few big steps
        instead of a dozen 30->38-style micro-steps.
        """
        config = replace(
            cadence_config,
            summary_interval_minutes=360,
            adaptive_cadence=replace(
                cadence_config.adaptive_cadence,
                min_interval_minutes=30,
                decay_factor=2.0,
                calm_streak_runs=1,  # isolate the decay-step math
            ),
        )
        controller = AdaptiveCadenceController(config)
        self._seed_baseline(controller)
        controller._current_interval = 30
        controller._current_level = IntensityLevel.SURGE

        intervals = [controller.record_and_compute(1.0).new_interval for _ in range(5)]

        assert intervals == [60, 120, 240, 360, 360]

    def test_never_below_min_interval(self, cadence_config: Config) -> None:
        """Test the interval floor is honored."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        for _ in range(5):
            decision = controller.record_and_compute(100.0)  # sustained surge
            assert decision.new_interval >= 5

    def test_appends_and_trims_window(self, cadence_config: Config) -> None:
        """Test each call appends a rate and trims to baseline_window."""
        controller = AdaptiveCadenceController(cadence_config)  # baseline_window=5

        for _ in range(7):
            controller.record_and_compute(1.0)

        assert len(controller._rate_window) == 5

    def test_max_interval_ceiling(self, cadence_config: Config) -> None:
        """Test decay can climb above baseline up to max_interval_minutes."""
        controller = AdaptiveCadenceController(cadence_config)
        controller.config.max_interval_minutes = 60
        controller.config.calm_streak_runs = 1  # isolate the decay-step math
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        intervals = [controller.record_and_compute(1.0).new_interval for _ in range(12)]

        assert max(intervals) == 60
        assert all(i <= 60 for i in intervals)

    def test_state_saved_on_each_call(
        self, cadence_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test record_and_compute persists state."""
        state_file = tmp_path / ".cadence_state"
        monkeypatch.setattr("src.cadence.CADENCE_STATE_FILE", state_file)
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        controller.record_and_compute(4.0)

        assert state_file.exists()


class TestCadenceDecisionReasons:
    """Tests for the change reason attached to each CadenceDecision."""

    def _seed_baseline(self, controller: AdaptiveCadenceController) -> None:
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

    def test_volume_escalation_reason(self, cadence_config: Config) -> None:
        """Test escalation driven by the volume ratio cites NEWS_VOLUME."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        decision = controller.record_and_compute(4.0)

        assert decision.changed is True
        assert decision.reason == CadenceChangeReason.NEWS_VOLUME
        assert decision.previous_interval == 30
        assert decision.new_interval == 5

    def test_radar_decisive_escalation_reason(self, cadence_config: Config) -> None:
        """Test escalation where the radar promotion was decisive cites RADAR_OUTAGE."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        # Rate 1.0 is NORMAL on its own; only the radar promotion escalates.
        decision = controller.record_and_compute(1.0, radar_alert=True)

        assert decision.changed is True
        assert decision.reason == CadenceChangeReason.RADAR_OUTAGE
        assert decision.level == IntensityLevel.ELEVATED

    def test_volume_escalation_with_radar_still_news_volume(
        self, cadence_config: Config
    ) -> None:
        """Test a rate already at SURGE cites NEWS_VOLUME even if radar also fired."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        # 4.0 is SURGE by volume alone; the radar promotion changes nothing.
        decision = controller.record_and_compute(4.0, radar_alert=True)

        assert decision.reason == CadenceChangeReason.NEWS_VOLUME

    def test_decay_reason(self, cadence_config: Config) -> None:
        """Test a decay step cites CALM_DECAY."""
        controller = AdaptiveCadenceController(cadence_config)
        controller.config.calm_streak_runs = 1  # decay on the first calm run
        self._seed_baseline(controller)
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        decision = controller.record_and_compute(1.0)

        assert decision.changed is True
        assert decision.reason == CadenceChangeReason.CALM_DECAY
        assert decision.new_interval > decision.previous_interval

    def test_unchanged_interval_has_no_reason(self, cadence_config: Config) -> None:
        """Test an unchanged interval yields changed False and no reason."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        decision = controller.record_and_compute(1.0)  # NORMAL at baseline interval

        assert decision.changed is False
        assert decision.reason is None


class TestConsiderEscalation:
    """Tests for the escalate-only probe path."""

    def _seed_baseline(self, controller: AdaptiveCadenceController) -> None:
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

    def test_escalates_when_level_rises(self, cadence_config: Config) -> None:
        """Test a higher level returns a shorter interval and updates state."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        decision = controller.consider_escalation(4.0, radar_alert=False)

        assert decision.changed is True
        assert decision.new_interval == 5
        assert decision.reason == CadenceChangeReason.NEWS_VOLUME
        assert controller.current_interval == 5
        assert controller.current_level == IntensityLevel.SURGE

    def test_non_changed_decision_when_no_escalation(self, cadence_config: Config) -> None:
        """Test a non-rising level returns a non-changed decision, state untouched."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        decision = controller.consider_escalation(1.0, radar_alert=False)

        assert decision.changed is False
        assert decision.reason is None
        assert controller.current_interval == 30
        assert controller.current_level == IntensityLevel.NORMAL

    def test_never_decays(self, cadence_config: Config) -> None:
        """Test the probe never relaxes an already-tightened cadence."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        decision = controller.consider_escalation(1.0, radar_alert=False)

        assert decision.changed is False
        assert controller.current_interval == 5  # not relaxed

    def test_does_not_relax_when_level_rises_below_held_interval(
        self, cadence_config: Config
    ) -> None:
        """Test a rising level does not WIDEN an interval held tight by hysteresis.

        Regression: a full run can hold interval=5 at a NORMAL level (decay
        hysteresis). An ELEVATED probe reading (target 15 > 5) must not relax the
        cadence back out to 15 and post a bogus "calming" notice.
        """
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)
        controller._current_interval = 5  # held tight
        controller._current_level = IntensityLevel.NORMAL  # but level is calm

        decision = controller.consider_escalation(2.0)  # ELEVATED, target 15

        assert decision.changed is False
        assert decision.reason is None
        assert controller.current_interval == 5  # not widened

    def test_does_not_append_to_window(self, cadence_config: Config) -> None:
        """Test the probe does not pollute the baseline window."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)
        before = list(controller._rate_window)

        controller.consider_escalation(4.0, radar_alert=False)

        assert controller._rate_window == before

    def test_radar_escalates(self, cadence_config: Config) -> None:
        """Test a radar outage promotes the level via the probe."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        decision = controller.consider_escalation(1.0, radar_alert=True)

        assert decision.changed is True
        assert decision.new_interval == 15  # ELEVATED => half the 30min baseline
        assert decision.reason == CadenceChangeReason.RADAR_OUTAGE
        assert controller.current_level == IntensityLevel.ELEVATED


class TestDecayHysteresis:
    """Tests for the calm-streak gate that prevents decay/re-escalate flapping.

    With the default calm_streak_runs=2, a single quiet window in the middle of
    a surge must not relax the cadence; only sustained calm decays it.
    """

    def _seed_baseline(self, controller: AdaptiveCadenceController) -> None:
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

    def test_holds_interval_until_calm_streak_met(self, cadence_config: Config) -> None:
        """Test the first calm run after a surge holds; the second decays."""
        controller = AdaptiveCadenceController(cadence_config)  # calm_streak_runs=2
        self._seed_baseline(controller)
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        first = controller.record_and_compute(1.0)  # NORMAL, streak -> 1
        assert first.changed is False
        assert first.new_interval == 5  # held, not relaxed

        second = controller.record_and_compute(1.0)  # NORMAL, streak -> 2
        assert second.changed is True
        assert second.reason == CadenceChangeReason.CALM_DECAY
        assert second.new_interval == 8  # round(5 * 1.5)

    def test_volume_escalation_resets_calm_streak(self, cadence_config: Config) -> None:
        """Test a renewed surge clears accumulated calm runs."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)
        controller._current_interval = 15
        controller._current_level = IntensityLevel.ELEVATED

        controller.record_and_compute(1.0)  # NORMAL, streak -> 1
        controller.record_and_compute(4.0)  # SURGE escalates to 5, streak -> 0

        assert controller.current_interval == 5

        # After the reset it again takes two calm runs to start decaying.
        first = controller.record_and_compute(1.0)
        assert first.changed is False  # held by the streak gate
        second = controller.record_and_compute(1.0)
        assert second.changed is True
        assert second.reason == CadenceChangeReason.CALM_DECAY

    def test_probe_escalation_resets_calm_streak(self, cadence_config: Config) -> None:
        """Test the exact flap scenario: a probe re-escalation blocks the next
        full run from immediately decaying off a stale calm streak."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        controller.record_and_compute(1.0)  # NORMAL, streak -> 1
        controller.record_and_compute(1.0)  # NORMAL, streak -> 2, decays 5 -> 8

        probe = controller.consider_escalation(4.0)  # SURGE re-escalates to 5
        assert probe.changed is True
        assert controller.current_interval == 5

        # Without the streak reset this run would decay again (flap). It must hold.
        after = controller.record_and_compute(1.0)
        assert after.changed is False
        assert after.new_interval == 5

    def test_decay_needs_fresh_streak_for_each_step(self, cadence_config: Config) -> None:
        """Test each decay step re-earns calm_streak_runs calm runs (slow decay).

        With calm_streak_runs=2 the interval steps up only every other calm run,
        not on every run, so the climb back toward the baseline stays gradual.
        """
        controller = AdaptiveCadenceController(cadence_config)  # calm_streak_runs=2
        self._seed_baseline(controller)
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        changed = [controller.record_and_compute(1.0).changed for _ in range(4)]

        # hold, decay, hold, decay — one step per two calm runs.
        assert changed == [False, True, False, True]

    def test_elevated_does_not_decay_on_its_own(self, cadence_config: Config) -> None:
        """Test an ELEVATED reading holds the tighter interval and resets calm."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        controller.record_and_compute(1.0)  # NORMAL, streak -> 1
        elevated = controller.record_and_compute(2.0)  # ELEVATED (target 15 > 5)

        assert elevated.changed is False  # not an escalation, not a decay
        assert controller.current_interval == 5  # held
        assert controller._calm_streak == 0  # reset; not calm


class TestSurgeOnset:
    """Tests for CadenceDecision.is_surge_onset and previous_level tracking."""

    def _seed_baseline(self, controller: AdaptiveCadenceController) -> None:
        """Seed a baseline rate of 1.0 messages per minute."""
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

    def test_onset_true_when_escalating_from_normal(self) -> None:
        """A volume escalation out of a NORMAL state is a surge onset."""
        decision = CadenceDecision(
            previous_interval=30,
            new_interval=5,
            level=IntensityLevel.SURGE,
            reason=CadenceChangeReason.NEWS_VOLUME,
            previous_level=IntensityLevel.NORMAL,
        )

        assert decision.is_surge_onset is True

    def test_onset_true_for_radar_outage_from_normal(self) -> None:
        """A radar-driven escalation out of NORMAL is also an onset."""
        decision = CadenceDecision(
            previous_interval=30,
            new_interval=15,
            level=IntensityLevel.ELEVATED,
            reason=CadenceChangeReason.RADAR_OUTAGE,
            previous_level=IntensityLevel.NORMAL,
        )

        assert decision.is_surge_onset is True

    def test_onset_false_for_decay(self) -> None:
        """A calm-decay step is never announced as an onset."""
        decision = CadenceDecision(
            previous_interval=30,
            new_interval=45,
            level=IntensityLevel.NORMAL,
            reason=CadenceChangeReason.CALM_DECAY,
            previous_level=IntensityLevel.NORMAL,
        )

        assert decision.is_surge_onset is False

    def test_onset_false_when_already_elevated(self) -> None:
        """Re-escalation while an event is already underway is silent."""
        decision = CadenceDecision(
            previous_interval=15,
            new_interval=5,
            level=IntensityLevel.SURGE,
            reason=CadenceChangeReason.NEWS_VOLUME,
            previous_level=IntensityLevel.ELEVATED,
        )

        assert decision.is_surge_onset is False

    def test_onset_false_when_interval_unchanged(self) -> None:
        """A no-op decision is never an onset."""
        decision = CadenceDecision(
            previous_interval=30,
            new_interval=30,
            level=IntensityLevel.NORMAL,
            reason=None,
            previous_level=IntensityLevel.NORMAL,
        )

        assert decision.is_surge_onset is False

    def test_record_and_compute_reports_previous_level(self, cadence_config: Config) -> None:
        """record_and_compute carries the level held before this evaluation."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        first = controller.record_and_compute(4.0)  # NORMAL -> SURGE
        assert first.previous_level is IntensityLevel.NORMAL
        assert first.is_surge_onset is True

        second = controller.record_and_compute(4.0)  # SURGE -> SURGE (held)
        assert second.previous_level is IntensityLevel.SURGE

    def test_consider_escalation_reports_previous_level(self, cadence_config: Config) -> None:
        """The probe escalation also carries the prior level for onset gating."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        decision = controller.consider_escalation(4.0)  # NORMAL -> SURGE

        assert decision.previous_level is IntensityLevel.NORMAL
        assert decision.is_surge_onset is True
