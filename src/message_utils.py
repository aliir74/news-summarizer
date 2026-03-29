"""Shared message utilities for output writers."""

import html
import logging
import re

logger = logging.getLogger(__name__)

# Type alias for source reference mapping: {ref_num: (label, url)}
SourceRefMap = dict[int, tuple[str, str]]

# Telegram/Bale message character limit
MAX_MESSAGE_LENGTH = 4096

# Pattern: (source label | URL) at end of bullet
SOURCE_LINK_PATTERN = re.compile(
    r"\(([^|()]+?)\s*\|\s*(https?://[^\s)]+)\)"
)

# Pattern: line-starting bullet markers (markdown, numbered, dashed)
BULLET_PATTERN = re.compile(
    r"^(?:"
    r"\*\s+"  # * item  or  *   item
    r"|-\s+"  # - item
    r"|[0-9۰-۹]+[.\-\)]\s*"  # 1. or 1- or 1) or ۱. etc.
    r")",
    re.MULTILINE,
)

# Pattern: [1] or [1,3] or [1, 3] or [۱،۳] (Persian digits + comma)
SOURCE_REF_PATTERN = re.compile(
    r"\[([0-9۰-۹]+(?:\s*[,،]\s*[0-9۰-۹]+)*)\]"
)

# Persian digit to ASCII mapping
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_bullets(text: str) -> str:
    """Normalize markdown/numbered bullet prefixes to 🔹."""
    return BULLET_PATTERN.sub("🔹 ", text)


def resolve_source_refs(text: str, source_refs: SourceRefMap) -> str:
    """Replace [n] reference markers with (label | url) format.

    Supports Persian digits and Persian comma separator.
    Unknown reference numbers are left unchanged.
    """

    def _replacer(match: re.Match[str]) -> str:
        refs_str = match.group(1)
        nums = [
            int(n.strip().translate(_PERSIAN_DIGITS))
            for n in re.split(r"[,،]", refs_str)
        ]
        parts: list[str] = []
        seen: set[int] = set()
        for num in nums:
            if num in seen:
                continue
            seen.add(num)
            if num not in source_refs:
                logger.warning("Unknown source reference [%d] in LLM output", num)
                continue
            label, url = source_refs[num]
            if url:
                parts.append(f"({label} | {url})")
            else:
                parts.append(f"({label})")
        if parts:
            return " ".join(parts)
        return match.group(0)  # Leave unresolved refs as-is

    return SOURCE_REF_PATTERN.sub(_replacer, text)


def postprocess_llm_output(text: str, source_refs: SourceRefMap) -> str:
    """Normalize bullets and resolve source references in LLM output."""
    text = normalize_bullets(text)
    text = resolve_source_refs(text, source_refs)
    return text


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


def _has_balanced_html_tags(text: str) -> bool:
    """Check if <a> tags are balanced in the text."""
    return text.count("<a ") == text.count("</a>")


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

    # Validate no broken HTML tags in any chunk
    for i, msg in enumerate(messages):
        if not _has_balanced_html_tags(msg):
            messages[i] = re.sub(r"<[^>]+>", "", msg)

    return messages
