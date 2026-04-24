"""
Unit tests for prompt caching FinOps tracker.

Tests cache usage parsing, savings calculation, and report generation
for Anthropic, OpenAI, and Google providers.
"""

import pytest
from src.finops.caching import (
    parse_cache_usage,
    calculate_cache_savings,
    generate_cache_savings_report,
    BASE_INPUT_PRICES,
    CACHE_PRICING,
)


class TestParseAnthropicCache:
    def test_full_anthropic_usage(self):
        usage = {
            "input_tokens": 5000,
            "cache_read_input_tokens": 3000,
            "cache_creation_input_tokens": 500,
        }
        result = parse_cache_usage("anthropic", usage)
        assert result["cached_read_tokens"] == 3000
        assert result["cached_write_tokens"] == 500
        assert result["uncached_tokens"] == 1500
        assert result["total_input_tokens"] == 5000

    def test_no_cache_anthropic(self):
        usage = {"input_tokens": 2000}
        result = parse_cache_usage("anthropic", usage)
        assert result["cached_read_tokens"] == 0
        assert result["cached_write_tokens"] == 0
        assert result["uncached_tokens"] == 2000

    def test_all_cached_anthropic(self):
        usage = {"input_tokens": 4000, "cache_read_input_tokens": 4000}
        result = parse_cache_usage("anthropic", usage)
        assert result["cached_read_tokens"] == 4000
        assert result["uncached_tokens"] == 0


class TestParseOpenAICache:
    def test_openai_cached_tokens(self):
        usage = {
            "prompt_tokens": 3000,
            "prompt_tokens_details": {"cached_tokens": 2000},
        }
        result = parse_cache_usage("openai", usage)
        assert result["cached_read_tokens"] == 2000
        assert result["uncached_tokens"] == 1000
        assert result["total_input_tokens"] == 3000

    def test_openai_no_cache(self):
        usage = {"prompt_tokens": 1000}
        result = parse_cache_usage("openai", usage)
        assert result["cached_read_tokens"] == 0
        assert result["uncached_tokens"] == 1000


class TestParseGoogleCache:
    def test_google_context_cache(self):
        usage = {
            "prompt_token_count": 5000,
            "cached_content_token_count": 3500,
        }
        result = parse_cache_usage("google", usage)
        assert result["cached_read_tokens"] == 3500
        assert result["uncached_tokens"] == 1500


class TestCalculateSavings:
    def test_anthropic_cache_savings(self):
        result = calculate_cache_savings(
            provider="anthropic",
            model="claude-sonnet-4",
            cached_read_tokens=10000,
            uncached_tokens=2000,
        )
        assert result["savings_usd"] > 0
        assert result["savings_pct"] > 0
        assert result["cache_hit_rate_pct"] > 80

    def test_openai_cache_savings(self):
        result = calculate_cache_savings(
            provider="openai",
            model="gpt-4o",
            cached_read_tokens=5000,
            uncached_tokens=1000,
        )
        assert result["savings_usd"] > 0
        assert result["savings_pct"] > 0

    def test_no_cache_no_savings(self):
        result = calculate_cache_savings(
            provider="anthropic",
            model="claude-sonnet-4",
            cached_read_tokens=0,
            uncached_tokens=5000,
        )
        assert result["savings_usd"] == 0
        assert result["savings_pct"] == 0
        assert result["cache_hit_rate_pct"] == 0

    def test_all_cached_max_savings(self):
        result = calculate_cache_savings(
            provider="anthropic",
            model="claude-sonnet-4",
            cached_read_tokens=10000,
            uncached_tokens=0,
        )
        assert result["savings_pct"] > 80  # ~90% for Anthropic

    def test_unknown_model_uses_default(self):
        result = calculate_cache_savings(
            provider="anthropic",
            model="unknown-model-xyz",
            cached_read_tokens=1000,
            uncached_tokens=0,
        )
        assert result["savings_usd"] >= 0  # should not crash

    def test_zero_tokens_no_crash(self):
        result = calculate_cache_savings(
            provider="anthropic",
            model="claude-sonnet-4",
            cached_read_tokens=0,
            uncached_tokens=0,
        )
        assert result["savings_usd"] == 0
        assert result["cache_hit_rate_pct"] == 0


class TestGenerateReport:
    def test_empty_records(self):
        report = generate_cache_savings_report([])
        assert report["total_requests"] == 0
        assert report["total_savings_usd"] == 0

    def test_report_with_records(self):
        records = [
            {"provider": "anthropic", "model": "claude-sonnet-4", "cached_read_tokens": 5000, "cached_write_tokens": 100, "uncached_tokens": 1000},
            {"provider": "anthropic", "model": "claude-sonnet-4", "cached_read_tokens": 8000, "cached_write_tokens": 0, "uncached_tokens": 500},
            {"provider": "openai", "model": "gpt-4o", "cached_read_tokens": 3000, "uncached_tokens": 2000},
        ]
        report = generate_cache_savings_report(records, period="7d")
        assert report["total_requests"] == 3
        assert report["total_savings_usd"] > 0
        assert report["period"] == "7d"
        assert "by_model" in report
        assert "generated_at" in report

    def test_report_by_model_breakdown(self):
        records = [
            {"provider": "anthropic", "model": "claude-sonnet-4", "cached_read_tokens": 5000, "uncached_tokens": 1000},
            {"provider": "openai", "model": "gpt-4o", "cached_read_tokens": 3000, "uncached_tokens": 2000},
        ]
        report = generate_cache_savings_report(records)
        assert "claude-sonnet-4" in report["by_model"]
        assert "gpt-4o" in report["by_model"]
        assert report["by_model"]["claude-sonnet-4"]["requests"] == 1
        assert report["by_model"]["gpt-4o"]["requests"] == 1

    def test_cache_hit_rate_calculation(self):
        records = [
            {"provider": "anthropic", "model": "claude-sonnet-4", "cached_read_tokens": 9000, "uncached_tokens": 1000},
        ]
        report = generate_cache_savings_report(records)
        assert report["cache_hit_rate_pct"] == 90.0
