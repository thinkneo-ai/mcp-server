# Rate Limiting

ThinkNEO Gateway enforces multi-dimensional rate limits to protect against abuse and ensure fair usage.

## How It Works

Two layers of rate limiting, applied in order:

1. **Burst limit (in-memory)** — Sliding window counter per API key, per second. Prevents request floods.
2. **Per-minute limit (PostgreSQL)** — Tracked in `rate_limit_events` table. Prevents sustained overuse.

Both layers fail-open: if the database is temporarily unavailable, requests are allowed through to avoid blocking legitimate traffic.

## Tier Limits

| Tier | Burst (per second) | Per Minute | Monthly |
|------|-------------------|------------|---------|
| Free | 10 | 60 | 500 |
| Starter | 100 | 600 | 5,000 |
| Pro | 100 | 600 | 5,000 |
| Enterprise | 1,000 | 6,000 | Unlimited |

## HTTP Headers

Every authenticated response includes standard rate limit headers:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1714070400
```

When rate limit is exceeded:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 1
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1714070401

{
  "error": "rate_limit_exceeded",
  "type": "burst",
  "limit": 10,
  "current": 11,
  "message": "Burst rate limit exceeded (10/second for free tier). Retry in 1 second.",
  "retry_after": 1
}
```

## Client Implementation

```python
import time
import httpx

def call_with_backoff(url, payload, headers, max_retries=3):
    for attempt in range(max_retries):
        resp = httpx.post(url, json=payload, headers=headers)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "1"))
            time.sleep(retry_after)
            continue
        return resp
    raise Exception("Rate limit exceeded after retries")
```

## Architecture

```
Request → CORS → OTEL → RateLimitMiddleware → BearerToken → MCP App
                          ↓
                  Burst check (in-memory, <1ms)
                          ↓
                  Per-minute check (PostgreSQL)
                          ↓
                  Add X-RateLimit-* headers to response
```
