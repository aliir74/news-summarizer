"""Shared message utilities for output writers."""

import html
import re

# Telegram/Bale message character limit
MAX_MESSAGE_LENGTH = 4096

# Pattern: (source label | URL) at end of bullet
SOURCE_LINK_PATTERN = re.compile(
    r"\(([^|()]+?)\s*\|\s*(https?://[^\s)]+)\)"
)


def format_html_links(text: str) -> str:
    """Convert (source | url) patterns to HTML links and escape other HTML."""
    matches = list(SOURCE_LINK_PATTERN.finditer(text))

    if not matches:
        return html.escape(text)

    result = []
    last_end = 0

    for match in matches:
        # Escape text before this match
        result.append(html.escape(text[last_end:match.start()]))
        # Build HTML link
        label = html.escape(match.group(1).strip())
        url = match.group(2).strip()
        result.append(f'(<a href="{url}">{label}</a>)')
        last_end = match.end()

    # Escape remaining text
    result.append(html.escape(text[last_end:]))

    return "".join(result)


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
