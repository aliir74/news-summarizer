"""Tests for shared message utilities."""

from src.message_utils import MAX_MESSAGE_LENGTH, split_message


class TestSplitMessage:
    """Tests for the split_message function."""

    def test_short_message_not_split(self) -> None:
        """Test that short messages are not split."""
        text = "Short message"
        result = split_message(text)

        assert len(result) == 1
        assert result[0] == text

    def test_message_at_max_length(self) -> None:
        """Test message exactly at max length."""
        text = "x" * MAX_MESSAGE_LENGTH
        result = split_message(text)

        assert len(result) == 1

    def test_split_by_paragraphs(self) -> None:
        """Test splitting long message by paragraphs."""
        paragraph = "This is a paragraph. " * 100  # ~2100 chars
        text = f"{paragraph}\n\n{paragraph}\n\n{paragraph}"

        result = split_message(text)

        assert len(result) > 1
        for part in result:
            assert len(part) <= MAX_MESSAGE_LENGTH

    def test_split_long_single_paragraph(self) -> None:
        """Test splitting a single very long paragraph by sentences."""
        sentences = [f"This is sentence number {i}. " for i in range(200)]
        text = "".join(sentences)

        result = split_message(text)

        assert len(result) > 1
        for part in result:
            assert len(part) <= MAX_MESSAGE_LENGTH

    def test_preserves_content(self) -> None:
        """Test that splitting preserves all content."""
        paragraph1 = "First paragraph content."
        paragraph2 = "Second paragraph content."
        text = f"{paragraph1}\n\n{paragraph2}"

        result = split_message(text)

        combined = " ".join(result)
        assert "First paragraph" in combined
        assert "Second paragraph" in combined

    def test_empty_message(self) -> None:
        """Test splitting empty message."""
        result = split_message("")

        assert len(result) == 1
        assert result[0] == ""

    def test_max_message_length_constant(self) -> None:
        """Test that MAX_MESSAGE_LENGTH is 4096."""
        assert MAX_MESSAGE_LENGTH == 4096
