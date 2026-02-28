# LLM Model Comparison for Persian News Summarization

This document compares cost-effective LLM models available on OpenRouter for Persian language summarization tasks.

**Last Updated:** January 2026

## Model Comparison Table

| Model | OpenRouter Model ID | Input $/1M | Output $/1M | Persian Quality | Speed | Context |
|-------|---------------------|------------|-------------|-----------------|-------|---------|
| **Gemma 2 9B** ⭐ | `google/gemma-2-9b-it` | $0.03 | $0.09 | **Excellent** | Fast | 8K |
| Gemini 2.0 Flash Lite | `google/gemini-2.0-flash-lite-001` | $0.075 | $0.30 | Good | Fast | 1M |
| Gemini 2.5 Flash Lite | `google/gemini-2.5-flash-lite` | $0.10 | $0.40 | Good | Fast | 1M |
| Gemini 2.0 Flash | `google/gemini-2.0-flash-001` | $0.125 | $0.50 | Good | Fast | 1M |
| GPT-4o Mini | `openai/gpt-4o-mini` | $0.15 | $0.60 | Good | Fast | 128K |
| Mistral Saba | `mistralai/mistral-saba-24b` | $0.20 | $0.60 | **Good** | Fast | 32K |
| DeepSeek V3 | `deepseek/deepseek-chat` | $0.30 | $1.20 | Good | Medium | 64K |
| Llama 3.3 70B | `meta-llama/llama-3.3-70b-instruct` | $0.10 | $0.40 | Fair | Medium | 128K |
| Claude 3.5 Haiku | `anthropic/claude-3.5-haiku` | $0.80 | $4.00 | **Excellent** | Fast | 200K |
| Qwen 2.5 72B | `qwen/qwen-2.5-72b-instruct` | ~$0.35 | ~$0.40 | Good | Medium | 128K |

⭐ = Current default model

## Persian Language Performance

### Top Performers

1. **Gemma 2 9B** - Research shows it "consistently outperforms other models across nearly all Persian tasks" with benchmark scores of 0.61 in few-shot and 0.42 in zero-shot learning. Best open-source option for Persian.

2. **Claude 3.5 Haiku** - According to the EPT (Evaluation of Persian Trustworthiness) benchmark, "Claude outperforms all other models across most aspects" including ethics, fairness, and cultural nuances. Higher cost but highest quality.

3. **Mistral Saba** - Specifically designed for Middle East and South Asia regions, trained on curated regional datasets. Good balance of cost and regional language support.

4. **Gemini Flash variants** - Good multilingual support with excellent speed. Strong training data diversity helps with Persian.

### Limited Persian Support

- **Llama 3.3 70B** - Persian not officially supported in training languages
- **Qwen 2.5** - Persian not in official language list (29+ languages supported)

## Recommendations by Use Case

### Best Value (Cost vs Quality)
- **Gemma 2 9B** (`google/gemma-2-9b-it`) - $0.03/$0.09 per 1M tokens
- Best Persian benchmark results among open-source models
- Extremely cost-effective for high-volume summarization

### Best Quality
- **Claude 3.5 Haiku** (`anthropic/claude-3.5-haiku`) - $0.80/$4.00 per 1M tokens
- Highest trustworthiness and cultural accuracy for Persian
- Best for when quality matters more than cost

### Best Balance (Quality + Context Window)
- **Gemini 2.0 Flash** (`google/gemini-2.0-flash-001`) - $0.125/$0.50 per 1M tokens
- Good Persian support with 1M token context window
- Useful if summarizing very long content

### Budget Option
- **Gemma 2 9B** with free tier available on some providers
- **Llama 3.3 70B** free version available (but Persian not officially supported)

## Cost Estimation

For a news summarizer checking 10 channels every 30 minutes:

| Scenario | Daily Messages | Daily Tokens (est.) | Monthly Cost (Gemma 2 9B) |
|----------|----------------|---------------------|---------------------------|
| Low volume | ~100 | ~50K input, ~10K output | ~$0.05 |
| Medium volume | ~500 | ~250K input, ~50K output | ~$0.25 |
| High volume | ~2000 | ~1M input, ~200K output | ~$1.00 |

## Changing the Model

To use a different model, update your `.env` file:

```env
LLM_MODEL=google/gemma-2-9b-it      # Default - best value
LLM_MODEL=anthropic/claude-3.5-haiku  # Best quality
LLM_MODEL=google/gemini-2.0-flash-001 # Best balance
```

## Research Sources

- [OpenRouter Pricing](https://openrouter.ai/pricing)
- [OpenRouter Models](https://openrouter.ai/models)
- [Benchmarking Open-Source LLMs for Persian](https://arxiv.org/html/2510.12807v1)
- [Khayyam Challenge (PersianMMLU)](https://arxiv.org/abs/2404.06644)
- [EPT Benchmark: Persian Trustworthiness](https://arxiv.org/html/2509.06838)
