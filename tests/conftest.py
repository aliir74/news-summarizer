"""Shared test fixtures."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Config
from src.models import Message, Summary


@pytest.fixture
def sample_config() -> Config:
    """Create a sample configuration for testing."""
    return Config(
        telegram_api_id=12345,
        telegram_api_hash="test_api_hash",
        telegram_session_string="test_session_string",
        telegram_bot_token="test_bot_token",
        output_channel_id="@test_channel",
        openrouter_api_key="test_openrouter_key",
        summary_interval_minutes=30,
        llm_model="google/gemma-2-9b-it",
        channels=["channel1", "channel2"],
    )


@pytest.fixture
def sample_messages() -> list[Message]:
    """Create sample messages for testing."""
    return [
        Message(
            id=1,
            channel_username="channel1",
            channel_title="Channel One",
            text="این یک خبر تست است.",
            timestamp=datetime(2024, 1, 15, 10, 30),
        ),
        Message(
            id=2,
            channel_username="channel1",
            channel_title="Channel One",
            text="خبر دوم برای تست.",
            timestamp=datetime(2024, 1, 15, 10, 35),
        ),
        Message(
            id=3,
            channel_username="channel2",
            channel_title="Channel Two",
            text="خبر از کانال دوم.",
            timestamp=datetime(2024, 1, 15, 10, 40),
        ),
    ]


@pytest.fixture
def sample_summary() -> Summary:
    """Create a sample summary for testing."""
    return Summary(
        content="این خلاصه اخبار است. شامل سه خبر از دو کانال می‌باشد.",
        source_count=3,
        channels=["Channel One", "Channel Two"],
        created_at=datetime(2024, 1, 15, 11, 0),
    )


@pytest.fixture
def mock_pyrogram_client() -> MagicMock:
    """Create a mock Pyrogram client."""
    client = MagicMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.get_chat = AsyncMock()
    client.get_chat_history = MagicMock()
    client.send_message = AsyncMock()
    return client


@pytest.fixture
def mock_openai_client() -> MagicMock:
    """Create a mock OpenAI client."""
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "خلاصه تست شده اخبار"
    client.chat.completions.create.return_value = response
    return client


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up required environment variables."""
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "test_api_hash")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "test_session_string")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")
    monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@test_channel")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_openrouter_key")
