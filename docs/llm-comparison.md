# LLM Model Comparison for Persian News Summarization

This document compares cost-effective LLM models available on OpenRouter for Persian language summarization tasks.

**Last Updated:** February 2026

## Model Comparison Table

| Model | OpenRouter Model ID | Input $/1M | Output $/1M | Persian Quality | Speed | Context |
|-------|---------------------|------------|-------------|-----------------|-------|---------|
| **Gemini 2.5 Flash Lite** ⭐ | `google/gemini-2.5-flash-lite` | $0.10 | $0.40 | **Excellent** | Fast | 1M |
| Gemma 3 27B | `google/gemma-3-27b-it` | $0.04 | $0.15 | **Very Good** | Fast | 131K |
| Gemma 3 12B | `google/gemma-3-12b-it` | $0.04 | $0.13 | Good | Fast | 131K |
| Gemma 2 9B | `google/gemma-2-9b-it` | $0.03 | $0.09 | Good | Fast | 8K |
| Qwen 2.5 72B | `qwen/qwen-2.5-72b-instruct` | $0.04 | $0.10 | Good | Medium | 33K |
| Qwen3 32B | `qwen/qwen3-32b` | $0.06 | $0.24 | Good | Fast | 41K |
| Gemini 2.0 Flash Lite | `google/gemini-2.0-flash-lite-001` | $0.07 | $0.30 | Good | Fast | 1M |
| Gemini 2.0 Flash | `google/gemini-2.0-flash-001` | $0.10 | $0.40 | Good | Fast | 1M |
| GPT-4o Mini | `openai/gpt-4o-mini` | $0.15 | $0.60 | Good | Fast | 128K |
| Mistral Saba | `mistralai/mistral-saba-24b` | $0.20 | $0.60 | Fair | Fast | 32K |
| DeepSeek V3.2 | `deepseek/deepseek-v3.2` | $0.26 | $0.38 | Fair | Medium | 164K |
| DeepSeek V3 | `deepseek/deepseek-chat` | $0.32 | $0.89 | Fair | Medium | 164K |
| Claude 3.5 Haiku | `anthropic/claude-3.5-haiku` | $0.80 | $4.00 | **Excellent** | Fast | 200K |

⭐ = Current default model

## Persian Language Performance

### Benchmark Results

**Persian Medical Board Exams (2025, published in *Scientific Reports*):**
- Gemini 2.5 Flash: **79.9%** (internal medicine), **73.9%** (surgical) — best performer
- GPT-5: 74.5% / 73.3%
- GPT-4o: 68.9% / 68.2%

**EPT Benchmark — Persian Trustworthiness (Sep 2025):**
- Claude 3.7 Sonnet: **89.6%** avg compliance (best overall)
- Gemini 2.5 Pro / GPT-4o: **93.0%** robustness
- Qwen 3: 70.4% avg, **48.75% safety** (weakest)

**Open-Source Persian Benchmarks (Oct 2025):**
- Gemma 2 9B: **0.61** few-shot, **0.42** zero-shot (best open-source)

**MELAC — Persian Cultural Alignment (Aug 2025):**
- OpenAI models lead on Persian linguistic/cultural tasks
- All 41 tested LLMs performed poorly on Iranian culturally-specific content (<50% for most)

### Top Performers

1. **Gemini 2.5 Flash Lite** - Best proven Persian benchmark scores among affordable models. Scored highest on Persian medical board exams. 1M token context window.

2. **Gemma 3 27B** - Successor to Gemma 2, trained with double the multilingual data and a new 262K-entry tokenizer shared with Gemini. Supports 140+ languages including Persian. Massive upgrade over Gemma 2 9B at minimal cost increase.

3. **Gemma 2 9B** - Still recognized as the best open-source model for Persian in zero/few-shot benchmarks, but now surpassed by newer models.

4. **Claude 3.5 Haiku** - Highest trustworthiness and cultural accuracy for Persian (EPT benchmark). Premium pricing.

### Caution

- **Qwen3** - Despite explicit Persian language support and good tokenizer, scored poorly on Persian trustworthiness (EPT: 48.75% safety). Use with caution.
- **DeepSeek V3/V3.2** - Known RTL/Persian rendering bugs. Chain-of-thought defaults to Chinese/English even when prompted in Persian.
- **Mistral Saba** - Designed for Middle East but focuses on Arabic, not Persian specifically.
- **Llama 4** - Persian not confirmed in supported language list.

## Recommendations by Use Case

### Best Quality for Persian
- **Gemini 2.5 Flash Lite** (`google/gemini-2.5-flash-lite`) - $0.10/$0.40 per 1M tokens
- Best benchmark scores on Persian medical exams
- 1M token context window for long content

### Best Value Upgrade
- **Gemma 3 27B** (`google/gemma-3-27b-it`) - $0.04/$0.15 per 1M tokens
- Direct successor to Gemma 2, 3x larger, improved Persian tokenizer
- Free tier available (`google/gemma-3-27b-it:free`)

### Budget Option
- **Qwen 2.5 72B** (`qwen/qwen-2.5-72b-instruct`) - $0.04/$0.10 per 1M tokens
- 72B parameters at near-free pricing (massive Feb 2026 price drop)
- Context limited to 33K on OpenRouter

### Premium Quality
- **Claude 3.5 Haiku** (`anthropic/claude-3.5-haiku`) - $0.80/$4.00 per 1M tokens
- Highest trustworthiness and cultural accuracy for Persian
- Best when quality matters more than cost

## Cost Estimation

For a news summarizer checking 10 channels every 30 minutes:

| Scenario | Daily Messages | Daily Tokens (est.) | Monthly Cost (Gemini 2.5 Flash Lite) | Monthly Cost (Gemma 2 9B) |
|----------|----------------|---------------------|--------------------------------------|---------------------------|
| Low volume | ~100 | ~50K input, ~10K output | ~$0.27 | ~$0.05 |
| Medium volume | ~500 | ~250K input, ~50K output | ~$1.35 | ~$0.25 |
| High volume | ~2000 | ~1M input, ~200K output | ~$5.40 | ~$1.00 |

## Changing the Model

To use a different model, update your `.env` file:

```env
LLM_MODEL=google/gemini-2.5-flash-lite  # Default - best Persian quality
LLM_MODEL=google/gemma-3-27b-it         # Best value upgrade
LLM_MODEL=google/gemma-2-9b-it          # Legacy - cheapest
LLM_MODEL=anthropic/claude-3.5-haiku    # Premium quality
```

## Research Sources

- [OpenRouter Pricing](https://openrouter.ai/pricing)
- [OpenRouter Models](https://openrouter.ai/models)
- [Benchmarking Open-Source LLMs for Persian (Oct 2025)](https://arxiv.org/html/2510.12807v1)
- [Khayyam Challenge / PersianMMLU](https://arxiv.org/abs/2404.06644)
- [EPT Benchmark: Persian Trustworthiness (Sep 2025)](https://arxiv.org/html/2509.06838)
- [MELAC: Persian Cultural Alignment (Aug 2025)](https://arxiv.org/abs/2508.00673)
- [PerHalluEval: Persian Hallucination Evaluation (Sep 2025)](https://arxiv.org/abs/2509.21104)
- [Persian Medical Board Exam Benchmark (Nature Scientific Reports)](https://www.nature.com/articles/s41598-025-31251-3)
- [MasalBench: Persian Proverbs (Jan 2026)](https://arxiv.org/abs/2601.22050)
- [MIZAN Persian LLM Leaderboard](https://huggingface.co/spaces/MCINext/mizan-llm-leaderboard)
- [Open Persian LLM Leaderboard](https://huggingface.co/spaces/PartAI/open-persian-llm-leaderboard)
