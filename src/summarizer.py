"""News summarization using OpenRouter LLM."""

import logging
import re

from openai import OpenAI

from src.config import Config
from src.models import Message, SourceInfo, SourceType, Summary, extract_domain

logger = logging.getLogger(__name__)

# Pattern to detect Persian/Arabic characters
PERSIAN_PATTERN = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")

SUMMARIZATION_PROMPT = """You are a Persian news summarizer. Your task is to create a faithful summary in Persian from the news items below.

CRITICAL REQUIREMENTS:
1. ONLY include information explicitly stated in the news items - do not add any external knowledge
2. PRESERVE uncertainty language exactly - if the source says "might", "could", "may", "reportedly", keep these words in Persian (ممکن است، شاید، احتمالاً، طبق گزارش‌ها)
3. MAINTAIN original verb tenses - do not change conditional/future to past tense
4. If information conflicts between sources, report both versions with attribution
5. Do NOT add context, background, or information from your training data

Guidelines:
- Group related news together
- Keep it brief but informative (2-4 paragraphs)
- Use clear Persian language
- Include source attribution where relevant

News items (with timestamps):
{messages}

Write a faithful summary in Persian, preserving all uncertainty language:"""


ENGLISH_SUMMARY_PROMPT = """Summarize the following English news items accurately and concisely.

CRITICAL REQUIREMENTS:
1. Preserve ALL uncertainty language (might, could, may, reportedly, allegedly, according to)
2. Do NOT change verb tenses - keep conditional as conditional, future as future
3. Only include information explicitly stated in the news items
4. Do NOT add external knowledge or context

News items:
{messages}

Summary:"""


TRANSLATION_PROMPT = """Translate the following English news summary to Persian.

CRITICAL: Preserve all uncertainty language exactly:
- "might" → "ممکن است"
- "could" → "می‌تواند" or "شاید"
- "may" → "ممکن است"
- "reportedly" → "طبق گزارش‌ها"
- "allegedly" → "ظاهراً"
- "according to" → "به گفته"

Do NOT change verb tenses or add/remove information.

English summary:
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
        formatted_messages = self._format_messages(messages)
        prompt = SUMMARIZATION_PROMPT.format(messages=formatted_messages)

        content = self._call_llm(
            model=self.config.llm_model,
            system_prompt="You are a helpful Persian news summarizer.",
            user_prompt=prompt,
        )

        if not content:
            return None

        return self._build_summary(content, messages)

    def _two_stage_summarize(self, messages: list[Message]) -> Summary | None:
        """Generate a summary using two-stage approach for English content.

        1. Separate English and Persian messages
        2. Summarize English messages in English, then translate to Persian
        3. Summarize Persian messages directly in Persian
        4. Combine both summaries
        """
        # Separate messages by language
        english_messages = [m for m in messages if not self._is_persian(m.text)]
        persian_messages = [m for m in messages if self._is_persian(m.text)]

        logger.info(
            f"Two-stage: {len(english_messages)} English, {len(persian_messages)} Persian messages"
        )

        summaries: list[str] = []

        # Process English messages
        if english_messages:
            english_summary = self._summarize_english_messages(english_messages)
            if english_summary:
                persian_translation = self._translate_to_persian(english_summary)
                if persian_translation:
                    summaries.append(persian_translation)

        # Process Persian messages
        if persian_messages:
            formatted = self._format_messages(persian_messages)
            prompt = SUMMARIZATION_PROMPT.format(messages=formatted)
            persian_summary = self._call_llm(
                model=self.config.llm_model,
                system_prompt="You are a helpful Persian news summarizer.",
                user_prompt=prompt,
            )
            if persian_summary:
                summaries.append(persian_summary)

        if not summaries:
            logger.error("No summaries generated from either language")
            return None

        # Combine summaries with a separator if both exist
        combined_content = "\n\n---\n\n".join(summaries)

        return self._build_summary(combined_content, messages)

    def _summarize_english_messages(self, messages: list[Message]) -> str | None:
        """Summarize English messages in English."""
        formatted = self._format_messages(messages)
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

    def _call_llm(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
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

            content = response.choices[0].message.content
            if not content:
                logger.error(f"Empty response from LLM ({model})")
                return None
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

    def _format_messages(self, messages: list[Message]) -> str:
        """Format messages for the LLM prompt."""
        formatted = []
        for msg in messages:
            timestamp_str = msg.timestamp.strftime("%Y-%m-%d %H:%M")
            formatted.append(f"[{msg.channel_title} - {timestamp_str}]\n{msg.text}\n")
        return "\n---\n".join(formatted)
