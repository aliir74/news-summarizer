"""News summarization using OpenRouter LLM."""

import logging
import re

from openai import OpenAI

from src.config import Config
from src.message_utils import SourceRefMap, postprocess_llm_output
from src.models import Message, SourceInfo, SourceType, Summary, extract_domain

logger = logging.getLogger(__name__)

# Pattern to detect Persian/Arabic characters
PERSIAN_PATTERN = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")

# Pattern: a complete bullet ends with source ref or period/sentence-ending punctuation
_COMPLETE_BULLET_RE = re.compile(
    r"[.؟!)\]،]$"  # period, question mark, exclamation, closing paren/bracket, comma
)


def _strip_incomplete_bullet(text: str) -> str:
    """Remove the last bullet if it appears truncated (no sentence-ending punctuation)."""
    lines = text.rstrip().split("\n")
    # Walk backwards to find the last 🔹 bullet
    for i in range(len(lines) - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped.startswith("🔹"):
            if not _COMPLETE_BULLET_RE.search(stripped):
                logger.warning("Stripping incomplete trailing bullet: %s", stripped[:80])
                # Remove this line and any trailing blank lines
                trimmed = "\n".join(lines[:i]).rstrip()
                return trimmed
            break  # last bullet is complete, nothing to strip
    return text

SUMMARIZATION_PROMPT = """You are a Persian news summarizer. Your task is to create a faithful summary in Persian from the news items below.

CRITICAL REQUIREMENTS:
1. ONLY include information explicitly stated in the news items - do not add any external knowledge
2. PRESERVE uncertainty language exactly - if the source says "might", "could", "may", "reportedly", keep these words in Persian (ممکن است، شاید، احتمالاً، طبق گزارش‌ها)
3. MAINTAIN original verb tenses - do not change conditional/future to past tense
4. If information conflicts between sources, report both versions with attribution

OUTPUT FORMAT:
- Output ONLY bullet points, one per news item or topic
- Start each bullet with 🔹
- Each bullet: 1-2 sentences, concise and direct
- End each bullet with the source reference number(s) in square brackets, e.g. [1] or [1,3] for combined items
- Use the reference numbers from the input headers (e.g. [1], [2]) to attribute your bullets
- Do NOT include URLs in your output - they will be added automatically
- Rank bullets by importance - most important news first
- Do NOT use paragraph style, sub-headers, or grouping headers
- Do NOT add context, background, or information from your training data

News items (with timestamps):
{messages}

Write bullet-point summary in Persian:"""


ENGLISH_SUMMARY_PROMPT = """Summarize the following English news items accurately and concisely.

CRITICAL REQUIREMENTS:
1. Preserve ALL uncertainty language (might, could, may, reportedly, allegedly, according to)
2. Do NOT change verb tenses - keep conditional as conditional, future as future
3. Only include information explicitly stated in the news items
4. Do NOT add external knowledge or context

OUTPUT FORMAT:
- Output ONLY bullet points, one per news item or topic
- Start each bullet with 🔹
- Each bullet: 1-2 sentences maximum
- End each bullet with the source reference number(s) in square brackets, e.g. [1] or [1,3]
- Use the reference numbers from the input headers to attribute your bullets
- Do NOT include URLs in your output - they will be added automatically
- Rank by importance - most important first

News items:
{messages}

Bullet-point summary:"""


RE_SUMMARIZE_PROMPT = """You have several previously-generated Persian news summaries below. Combine them into one concise set of bullet points.

CRITICAL REQUIREMENTS:
1. Remove duplicate or overlapping news items
2. PRESERVE uncertainty language exactly - if the source says "ممکن است", "شاید", "احتمالاً", "طبق گزارش‌ها", keep those words
3. MAINTAIN original verb tenses - do not change conditional/future to past tense
4. Do NOT add any information not present in the original summaries

OUTPUT FORMAT:
- Output ONLY 🔹 bullet points
- Each bullet: 1-2 sentences, concise
- Keep source attributions from original bullets
- Rank by importance

Summaries to combine:
{summaries}

Combined bullet-point summary in Persian:"""


TRANSLATION_PROMPT = """Translate the following English news bullet points to Persian.

CRITICAL: Preserve all uncertainty language exactly:
- "might" → "ممکن است"
- "could" → "می‌تواند" or "شاید"
- "may" → "ممکن است"
- "reportedly" → "طبق گزارش‌ها"
- "allegedly" → "ظاهراً"
- "according to" → "به گفته"

Do NOT change verb tenses or add/remove information.
Keep the 🔹 bullet format and source reference numbers [1], [2] etc. exactly as they are.

English bullet points:
{summary}

Persian translation:"""


class Summarizer:
    """Generates news summaries using OpenRouter LLM."""

    def __init__(self, config: Config) -> None:
        """Initialize the summarizer with configuration."""
        self.config = config
        self._client = OpenAI(
            api_key=config.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    def summarize_news(self, messages: list[Message]) -> Summary | None:
        """Generate a summary from a list of news messages.

        Uses two-stage summarization if enabled in config, otherwise single-stage.
        """
        if not messages:
            logger.info("No messages to summarize")
            return None

        if self.config.two_stage_summarization:
            return self._two_stage_summarize(messages)
        return self._single_stage_summarize(messages)

    def _single_stage_summarize(self, messages: list[Message]) -> Summary | None:
        """Generate a summary using single-stage Persian summarization."""
        formatted_messages, source_refs = self._format_messages(messages)
        prompt = SUMMARIZATION_PROMPT.format(messages=formatted_messages)

        content = self._call_llm(
            model=self.config.llm_model,
            system_prompt="You are a helpful Persian news summarizer.",
            user_prompt=prompt,
        )

        if not content:
            return None

        content = postprocess_llm_output(content, source_refs)
        return self._build_summary(content, messages)

    def _two_stage_summarize(self, messages: list[Message]) -> Summary | None:
        """Generate a summary using two-stage approach for English content.

        1. Separate English and Persian messages
        2. Summarize English messages in English, then translate to Persian
        3. Summarize Persian messages directly in Persian
        4. Combine both summaries
        """
        # Build global numbering across all messages
        numbered = list(enumerate(messages, start=1))
        source_refs: SourceRefMap = {
            i: (msg.channel_title, msg.url) for i, msg in numbered
        }

        # Separate messages by language, preserving global numbering
        english_numbered = [(i, m) for i, m in numbered if not self._is_persian(m.text)]
        persian_numbered = [(i, m) for i, m in numbered if self._is_persian(m.text)]

        logger.info(
            f"Two-stage: {len(english_numbered)} English, {len(persian_numbered)} Persian messages"
        )

        summaries: list[str] = []

        # Process English messages
        if english_numbered:
            formatted, _ = self._format_messages_numbered(english_numbered)
            english_summary = self._summarize_english_messages(formatted)
            if english_summary:
                persian_translation = self._translate_to_persian(english_summary)
                if persian_translation:
                    summaries.append(
                        postprocess_llm_output(persian_translation, source_refs)
                    )

        # Process Persian messages
        if persian_numbered:
            formatted, _ = self._format_messages_numbered(persian_numbered)
            prompt = SUMMARIZATION_PROMPT.format(messages=formatted)
            persian_summary = self._call_llm(
                model=self.config.llm_model,
                system_prompt="You are a helpful Persian news summarizer.",
                user_prompt=prompt,
            )
            if persian_summary:
                summaries.append(
                    postprocess_llm_output(persian_summary, source_refs)
                )

        if not summaries:
            logger.error("No summaries generated from either language")
            return None

        # Combine summaries with a separator if both exist
        combined_content = "\n\n---\n\n".join(summaries)

        return self._build_summary(combined_content, messages)

    def _summarize_english_messages(self, formatted: str) -> str | None:
        """Summarize English messages in English from pre-formatted input."""
        prompt = ENGLISH_SUMMARY_PROMPT.format(messages=formatted)

        return self._call_llm(
            model=self.config.english_llm_model,
            system_prompt="You are an accurate English news summarizer.",
            user_prompt=prompt,
        )

    def _translate_to_persian(self, english_summary: str) -> str | None:
        """Translate an English summary to Persian."""
        prompt = TRANSLATION_PROMPT.format(summary=english_summary)

        return self._call_llm(
            model=self.config.llm_model,
            system_prompt="You are a professional English to Persian translator.",
            user_prompt=prompt,
        )

    def re_summarize(self, texts: list[str]) -> str | None:
        """Re-summarize multiple previously-generated summaries into one.

        Used by the Bale retry queue to condense queued summaries into a
        single catch-up message.
        """
        joined = "\n\n---\n\n".join(texts)
        prompt = RE_SUMMARIZE_PROMPT.format(summaries=joined)

        return self._call_llm(
            model=self.config.llm_model,
            system_prompt="You are a helpful Persian news summarizer.",
            user_prompt=prompt,
        )

    def _call_llm(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4000,
    ) -> str | None:
        """Make an LLM API call and return the content."""
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0,
            )

            choice = response.choices[0]
            usage = response.usage
            logger.info(
                f"LLM response ({model}): finish_reason={choice.finish_reason}, "
                f"completion_tokens={usage.completion_tokens if usage else '?'}, "
                f"max_tokens={max_tokens}"
            )
            if choice.finish_reason != "stop":
                logger.warning(
                    f"LLM finish_reason={choice.finish_reason} ({model}) — "
                    f"output may be truncated"
                )
            content = choice.message.content
            if not content:
                logger.error(f"Empty response from LLM ({model})")
                return None
            content = _strip_incomplete_bullet(content)
            return content

        except Exception as e:
            logger.error(f"Error calling LLM ({model}): {e}")
            return None

    def _build_summary(self, content: str, messages: list[Message]) -> Summary:
        """Build a Summary object from content and messages."""
        channels = list({msg.channel_title for msg in messages})
        channel_usernames = list({msg.channel_username for msg in messages})

        seen_sources: dict[str, SourceInfo] = {}
        for msg in messages:
            if msg.channel_username not in seen_sources:
                domain = ""
                if msg.source_type == SourceType.RSS and msg.url:
                    domain = extract_domain(msg.url)
                seen_sources[msg.channel_username] = SourceInfo(
                    name=msg.channel_username,
                    source_type=msg.source_type,
                    domain=domain,
                )
        sources = list(seen_sources.values())

        return Summary(
            content=content,
            source_count=len(messages),
            channels=channels,
            channel_usernames=channel_usernames,
            sources=sources,
        )

    def _is_persian(self, text: str) -> bool:
        """Check if text is primarily Persian/Arabic script.

        Returns True if more than 20% of alphabetic characters are Persian/Arabic.
        """
        if not text:
            return False

        persian_chars = len(PERSIAN_PATTERN.findall(text))
        # Count Latin letters
        latin_chars = len(re.findall(r"[a-zA-Z]", text))

        total_alpha = persian_chars + latin_chars
        if total_alpha == 0:
            return False

        return persian_chars / total_alpha > 0.2

    def _format_messages(self, messages: list[Message]) -> tuple[str, SourceRefMap]:
        """Format messages for the LLM prompt with sequential numbering."""
        numbered = list(enumerate(messages, start=1))
        return self._format_messages_numbered(numbered)

    @staticmethod
    def _format_messages_numbered(
        numbered_msgs: list[tuple[int, Message]],
    ) -> tuple[str, SourceRefMap]:
        """Format messages with pre-assigned reference numbers."""
        formatted: list[str] = []
        source_refs: SourceRefMap = {}
        for num, msg in numbered_msgs:
            source_refs[num] = (msg.channel_title, msg.url)
            timestamp_str = msg.timestamp.strftime("%Y-%m-%d %H:%M")
            formatted.append(
                f"[{num}] [{msg.channel_title} - {timestamp_str}]\n{msg.text}\n"
            )
        return "\n---\n".join(formatted), source_refs
