"""
Outcome Benchmarking — Quality-Based Routing

Aggregates verification results by provider+task_type to feed the Smart Router
with real outcome quality data instead of static estimates.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .database import _get_conn, hash_key

logger = logging.getLogger(__name__)

_tables_checked = False


def _ensure_tables() -> None:
    global _tables_checked
    if _tables_checked:
        return
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'outcome_benchmarks')")
                if not cur.fetchone()["exists"]:
                    import pathlib
                    for p in ["/app/migrations/007_outcome_benchmarking.sql",
                              "/opt/thinkneo-mcp-server/migrations/007_outcome_benchmarking.sql"]:
                        path = pathlib.Path(p)
                        if path.exists():
                            cur.execute(path.read_text())
                            logger.info("Outcome benchmarking tables created")
                            break
        _tables_checked = True
    except Exception as exc:
        logger.warning("Benchmark table check failed: %s", exc)


# ---------------------------------------------------------------------------
# Record quality feedback
# ---------------------------------------------------------------------------

def record_feedback(
    api_key: str,
    provider: str,
    model: str,
    task_type: str,
    quality_signal: str,
    quality_score: Optional[float] = None,
    claim_id: Optional[str] = None,
    session_id: Optional[str] = None,
    feedback_source: str = "user_feedback",
) -> Dict[str, Any]:
    """Record a quality feedback signal and update the benchmark."""
    _ensure_tables()
    key_h = hash_key(api_key)

    valid_signals = {"verified", "failed", "thumbs_up", "thumbs_down"}
    if quality_signal not in valid_signals:
        raise ValueError(f"Invalid quality_signal. Must be one of: {sorted(valid_signals)}")

    # Auto-assign quality score based on signal
    if quality_score is None:
        score_map = {"verified": 100, "thumbs_up": 90, "thumbs_down": 20, "failed": 0}
        quality_score = score_map.get(quality_signal, 50)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO outcome_feedback
                        (api_key_hash, provider, model, task_type, quality_signal,
                         quality_score, claim_id, session_id, feedback_source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, recorded_at
                    """,
                    (key_h, provider, model, task_type, quality_signal,
                     quality_score, claim_id, session_id, feedback_source),
                )
                row = cur.fetchone()

                # Update benchmark aggregate
                _update_benchmark(cur, key_h, provider, model, task_type)

                return {
                    "feedback_id": row["id"],
                    "provider": provider,
                    "model": model,
                    "task_type": task_type,
                    "quality_signal": quality_signal,
                    "quality_score": quality_score,
                    "recorded_at": row["recorded_at"].isoformat(),
                }
    except ValueError:
        raise
    except Exception as exc:
        logger.error("record_feedback failed: %s", exc)
        raise


def _update_benchmark(cur, key_h: str, provider: str, model: str, task_type: str) -> None:
    """Re-aggregate benchmark from feedback data (last 30 days)."""
    cur.execute(
        """
        SELECT
            COUNT(*) AS sample_count,
            COALESCE(AVG(quality_score), 0) AS avg_quality,
            COUNT(*) FILTER (WHERE quality_signal = 'verified') AS verified,
            COUNT(*) FILTER (WHERE quality_signal = 'failed') AS failed
        FROM outcome_feedback
        WHERE api_key_hash = %s AND provider = %s AND model = %s AND task_type = %s
          AND recorded_at >= NOW() - INTERVAL '30 days'
        """,
        (key_h, provider, model, task_type),
    )
    row = cur.fetchone()

    cur.execute(
        """
        INSERT INTO outcome_benchmarks
            (api_key_hash, provider, model, task_type,
             quality_score, sample_count, verified_count, failed_count, last_updated)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (api_key_hash, provider, model, task_type)
        DO UPDATE SET
            quality_score = EXCLUDED.quality_score,
            sample_count = EXCLUDED.sample_count,
            verified_count = EXCLUDED.verified_count,
            failed_count = EXCLUDED.failed_count,
            last_updated = NOW()
        """,
        (
            key_h, provider, model, task_type,
            round(float(row["avg_quality"]), 2),
            row["sample_count"],
            row["verified"],
            row["failed"],
        ),
    )


# ---------------------------------------------------------------------------
# Benchmark reports
# ---------------------------------------------------------------------------

def get_benchmark_report(api_key: str, task_type: Optional[str] = None) -> Dict[str, Any]:
    """Get the full benchmark matrix for all providers/models."""
    _ensure_tables()
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                where = "api_key_hash = %s"
                params = [key_h]
                if task_type:
                    where += " AND task_type = %s"
                    params.append(task_type)

                cur.execute(
                    f"""
                    SELECT * FROM outcome_benchmarks
                    WHERE {where}
                    ORDER BY task_type, quality_score DESC
                    """,
                    params,
                )
                rows = cur.fetchall()

                benchmarks = []
                for r in rows:
                    decidable = r["verified_count"] + r["failed_count"]
                    verification_rate = round(
                        r["verified_count"] / decidable * 100 if decidable > 0 else 0, 1
                    )
                    benchmarks.append({
                        "provider": r["provider"],
                        "model": r["model"],
                        "task_type": r["task_type"],
                        "quality_score": float(r["quality_score"]),
                        "sample_count": r["sample_count"],
                        "verified_count": r["verified_count"],
                        "failed_count": r["failed_count"],
                        "verification_rate_pct": verification_rate,
                        "last_updated": r["last_updated"].isoformat(),
                    })

                # Group by task_type for easy consumption
                by_task = {}
                for b in benchmarks:
                    tt = b["task_type"]
                    if tt not in by_task:
                        by_task[tt] = []
                    by_task[tt].append(b)

                return {
                    "total_benchmarks": len(benchmarks),
                    "task_types": list(by_task.keys()),
                    "benchmarks_by_task_type": by_task,
                    "benchmarks": benchmarks,
                }
    except Exception as exc:
        logger.error("get_benchmark_report failed: %s", exc)
        raise


def compare_benchmarks(
    api_key: str,
    task_type: str,
    providers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compare provider benchmarks for a specific task type."""
    _ensure_tables()
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                where = "api_key_hash = %s AND task_type = %s"
                params = [key_h, task_type]

                if providers:
                    placeholders = ",".join(["%s"] * len(providers))
                    where += f" AND provider IN ({placeholders})"
                    params.extend(providers)

                cur.execute(
                    f"""
                    SELECT * FROM outcome_benchmarks
                    WHERE {where}
                    ORDER BY quality_score DESC
                    """,
                    params,
                )
                rows = cur.fetchall()

                results = []
                for r in rows:
                    decidable = r["verified_count"] + r["failed_count"]
                    results.append({
                        "provider": r["provider"],
                        "model": r["model"],
                        "quality_score": float(r["quality_score"]),
                        "sample_count": r["sample_count"],
                        "verification_rate_pct": round(
                            r["verified_count"] / decidable * 100 if decidable > 0 else 0, 1
                        ),
                        "rank": len(results) + 1,
                    })

                best = results[0] if results else None

                return {
                    "task_type": task_type,
                    "providers_compared": len(results),
                    "best_provider": best["provider"] if best else None,
                    "best_model": best["model"] if best else None,
                    "best_quality": best["quality_score"] if best else None,
                    "comparison": results,
                }
    except Exception as exc:
        logger.error("compare_benchmarks failed: %s", exc)
        raise


def explain_routing(
    api_key: str,
    task_type: str,
    quality_threshold: int = 85,
) -> Dict[str, Any]:
    """Explain why the router would choose a specific model, factoring in benchmarks."""
    _ensure_tables()
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Get benchmarks for this task type
                cur.execute(
                    """
                    SELECT * FROM outcome_benchmarks
                    WHERE api_key_hash = %s AND task_type = %s AND sample_count >= 3
                    ORDER BY quality_score DESC
                    """,
                    (key_h, task_type),
                )
                benchmarks = cur.fetchall()

                # Get static quality from Smart Router
                from .smart_router import MODEL_DB, TASK_TYPES

                explanation = {
                    "task_type": task_type,
                    "quality_threshold": quality_threshold,
                    "has_benchmark_data": len(benchmarks) > 0,
                    "benchmark_models": [],
                    "static_models": [],
                    "recommendation": None,
                    "reasoning": [],
                }

                # Benchmark-based recommendations
                if benchmarks:
                    for b in benchmarks:
                        quality = float(b["quality_score"])
                        if quality >= quality_threshold:
                            explanation["benchmark_models"].append({
                                "provider": b["provider"],
                                "model": b["model"],
                                "quality_score": quality,
                                "sample_count": b["sample_count"],
                                "source": "outcome_benchmark",
                            })

                    if explanation["benchmark_models"]:
                        best = explanation["benchmark_models"][0]
                        explanation["recommendation"] = {
                            "model": best["model"],
                            "provider": best["provider"],
                            "quality_score": best["quality_score"],
                            "source": "outcome_benchmark",
                        }
                        explanation["reasoning"].append(
                            f"Recommending {best['model']} based on {best['sample_count']} real outcome verifications "
                            f"with {best['quality_score']}% quality score"
                        )
                    else:
                        explanation["reasoning"].append(
                            f"No benchmark models meet threshold {quality_threshold}%"
                        )
                else:
                    explanation["reasoning"].append(
                        "No benchmark data available — using static quality estimates from Smart Router"
                    )

                # Static fallback from MODEL_DB (which is a List[ModelSpec])
                for spec in MODEL_DB:
                    static_quality = spec.quality.get(task_type, 0)
                    if static_quality >= quality_threshold:
                        explanation["static_models"].append({
                            "provider": spec.provider,
                            "model": spec.id,
                            "quality_score": static_quality,
                            "source": "static_estimate",
                        })

                if not explanation["recommendation"] and explanation["static_models"]:
                    best_static = explanation["static_models"][0]
                    explanation["recommendation"] = {
                        "model": best_static["model"],
                        "provider": best_static["provider"],
                        "quality_score": best_static["quality_score"],
                        "source": "static_estimate",
                    }
                    explanation["reasoning"].append(
                        f"Falling back to static estimate: {best_static['model']} "
                        f"with {best_static['quality_score']}% estimated quality"
                    )

                return explanation

    except Exception as exc:
        logger.error("explain_routing failed: %s", exc)
        raise
