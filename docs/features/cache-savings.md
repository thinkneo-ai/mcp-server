# Prompt Cache Savings Tracking

ThinkNEO tracks cached vs uncached token usage per provider and calculates cost savings from prompt caching.

## Supported Providers

| Provider | Cache Mechanism | Read Discount | Detected Fields |
|----------|----------------|--------------|-----------------|
| Anthropic | Prompt caching | 90% | `cache_read_input_tokens`, `cache_creation_input_tokens` |
| OpenAI | Automatic caching | 50% | `prompt_tokens_details.cached_tokens` |
| Google | Context caching | 75% | `cached_content_token_count` |

## How It Works

1. When an AI request passes through the gateway, the response includes token usage data
2. ThinkNEO parses cache-related fields from the provider's response
3. Savings are calculated: `(tokens_at_full_price - tokens_at_cached_price) = savings`
4. Results are aggregated per workspace, agent, model, and time period

## Report Fields

```json
{
  "period": "30d",
  "total_requests": 1250,
  "total_tokens": 5000000,
  "cached_read_tokens": 3500000,
  "cache_hit_rate_pct": 70.0,
  "cost_without_cache_usd": 15.00,
  "cost_with_cache_usd": 6.75,
  "total_savings_usd": 8.25,
  "savings_pct": 55.0,
  "by_model": {
    "claude-sonnet-4": { "savings_usd": 5.50, "requests": 800 },
    "gpt-4o": { "savings_usd": 2.75, "requests": 450 }
  }
}
```

## Architecture

```
Provider Response → Parse cache_* fields → Calculate savings
                                             ↓
                                    PostgreSQL: cache_usage table
                                             ↓
                              thinkneo_cache_savings_report tool
```
