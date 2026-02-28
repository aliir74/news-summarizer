"""Shared message utilities for output writers."""

# Telegram/Bale message character limit
MAX_MESSAGE_LENGTH = 4096


def split_message(text: str) -> list[str]:
    """Split a message into chunks that fit the message length limit."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    messages: list[str] = []
    current = ""

    # Split by paragraphs first
    paragraphs = text.split("\n\n")

    for para in paragraphs:
        # If adding this paragraph exceeds the limit
        if len(current) + len(para) + 2 > MAX_MESSAGE_LENGTH:
            if current:
                messages.append(current.strip())
                current = ""

            # If single paragraph is too long, split by sentences
            if len(para) > MAX_MESSAGE_LENGTH:
                sentences = para.split(". ")
                for sentence in sentences:
                    if len(current) + len(sentence) + 2 > MAX_MESSAGE_LENGTH:
                        if current:
                            messages.append(current.strip())
                        current = sentence
                    else:
                        current = current + ". " + sentence if current else sentence
            else:
                current = para
        else:
            current = current + "\n\n" + para if current else para

    if current:
        messages.append(current.strip())

    return messages
