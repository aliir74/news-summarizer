"""News summarization using OpenRouter LLM."""

import logging

from openai import OpenAI

from src.config import Config
from src.models import Message, Summary

logger = logging.getLogger(__name__)

SUMMARIZATION_PROMPT = """You are a Persian news summarizer. Given the following news items from various Telegram channels, create a concise summary in Persian.

Guidelines:
- Group related news together
- Keep it brief but informative (2-4 paragraphs)
- Use clear Persian language
- Focus on the most important and newsworthy items
- Include source attribution where relevant

News items:
{messages}

Write a summary in Persian:"""


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
        """Generate a summary from a list of news messages."""
        if not messages:
            logger.info("No messages to summarize")
            return None

        # Format messages for the prompt
        formatted_messages = self._format_messages(messages)
        prompt = SUMMARIZATION_PROMPT.format(messages=formatted_messages)

        try:
            response = self._client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful Persian news summarizer.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.7,
            )

            content = response.choices[0].message.content
            if not content:
                logger.error("Empty response from LLM")
                return None

            # Get unique channel names
            channels = list({msg.channel_title for msg in messages})

            return Summary(
                content=content,
                source_count=len(messages),
                channels=channels,
            )

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return None

    def _format_messages(self, messages: list[Message]) -> str:
        """Format messages for the LLM prompt."""
        formatted = []
        for msg in messages:
            timestamp_str = msg.timestamp.strftime("%H:%M")
            formatted.append(f"[{msg.channel_title} - {timestamp_str}]\n{msg.text}\n")
        return "\n---\n".join(formatted)
