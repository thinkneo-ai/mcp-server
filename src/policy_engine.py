"""
Policy Engine — Governance-as-Code for AI Agents

Declarative policy definitions with condition evaluation and enforcement.
Supports conditions on: model, provider, cost, task_type, agent_name,
data_classification, action, and custom fields.

Effects: block, warn, require_approval, log
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .database import _get_conn, hash_key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table bootstrap
# ---------------------------------------------------------------------------

_tables_checked = False


def _ensure_tables() -> None:
    global _tables_checked
    if _tables_checked:
        return
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'policies'
                    )
                """)
                if not cur.fetchone()["exists"]:
                    import pathlib
                    for p in ["/app/migrations/006_policy_engine.sql",
                              "/opt/thinkneo-mcp-server/migrations/006_policy_engine.sql"]:
                        path = pathlib.Path(p)
                        if path.exists():
                            cur.execute(path.read_text())
                            logger.info("Policy engine tables created")
                            break
        _tables_checked = True
    except Exception as exc:
        logger.warning("Policy table check failed: %s", exc)


# ---------------------------------------------------------------------------
# Seed policies
# ---------------------------------------------------------------------------

SEED_POLICIES = [
    {
        "name": "approval_over_10k",
        "description": "Require human approval for any action with cost > $10,000",
        "scope": {"agents": ["*"], "actions": ["approve_payment", "create_invoice", "transfer_funds"]},
        "conditions": [{"field": "cost", "operator": ">", "value": 10000}],
        "effect": "require_approval",
    },
    {
        "name": "pii_blocked_models",
        "description": "Block PII-containing requests from being sent to non-approved models",
        "scope": {"agents": ["*"], "actions": ["*"]},
        "conditions": [
            {"field": "data_classification", "operator": "==", "value": "pii"},
            {"field": "provider", "operator": "not_in", "value": ["anthropic", "openai"]},
        ],
        "effect": "block",
    },
    {
        "name": "hitl_legal_domain",
        "description": "Require human-in-the-loop for legal domain tasks",
        "scope": {"agents": ["*"], "actions": ["*"]},
        "conditions": [{"field": "task_type", "operator": "==", "value": "legal_analysis"}],
        "effect": "require_approval",
    },
]


def seed_policies(api_key: str) -> int:
    """Insert seed policies if they don't exist. Returns count of inserted."""
    _ensure_tables()
    key_h = hash_key(api_key)
    inserted = 0

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                for p in SEED_POLICIES:
                    cur.execute(
                        "SELECT COUNT(*) AS cnt FROM policies WHERE api_key_hash = %s AND name = %s",
                        (key_h, p["name"]),
                    )
                    if cur.fetchone()["cnt"] == 0:
                        cur.execute(
                            """
                            INSERT INTO policies
                                (api_key_hash, name, description, scope, conditions, effect)
                            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
                            """,
                            (
                                key_h, p["name"], p["description"],
                                json.dumps(p["scope"]),
                                json.dumps(p["conditions"]),
                                p["effect"],
                            ),
                        )
                        inserted += 1
    except Exception as exc:
        logger.error("seed_policies failed: %s", exc)

    return inserted


# ---------------------------------------------------------------------------
# Policy CRUD
# ---------------------------------------------------------------------------

def create_policy(
    api_key: str,
    name: str,
    conditions: List[Dict[str, Any]],
    effect: str,
    description: Optional[str] = None,
    scope: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create or update a policy."""
    _ensure_tables()
    key_h = hash_key(api_key)

    valid_effects = {"block", "warn", "require_approval", "log"}
    if effect not in valid_effects:
        raise ValueError(f"Invalid effect '{effect}'. Must be one of: {sorted(valid_effects)}")

    # Validate conditions
    for cond in conditions:
        if "field" not in cond or "operator" not in cond or "value" not in cond:
            raise ValueError("Each condition must have 'field', 'operator', and 'value'")

    scope = scope or {"agents": ["*"], "actions": ["*"]}

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Check if exists — bump version
                cur.execute(
                    "SELECT MAX(version) AS v FROM policies WHERE api_key_hash = %s AND name = %s",
                    (key_h, name),
                )
                row = cur.fetchone()
                version = (row["v"] or 0) + 1

                cur.execute(
                    """
                    INSERT INTO policies
                        (api_key_hash, name, description, version, scope, conditions, effect)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                    RETURNING policy_id, created_at
                    """,
                    (
                        key_h, name, description, version,
                        json.dumps(scope), json.dumps(conditions), effect,
                    ),
                )
                result = cur.fetchone()

                # Disable older versions
                if version > 1:
                    cur.execute(
                        """
                        UPDATE policies SET enabled = FALSE
                        WHERE api_key_hash = %s AND name = %s AND version < %s
                        """,
                        (key_h, name, version),
                    )

                return {
                    "policy_id": str(result["policy_id"]),
                    "name": name,
                    "version": version,
                    "effect": effect,
                    "conditions": conditions,
                    "scope": scope,
                    "enabled": True,
                    "created_at": result["created_at"].isoformat(),
                }
    except ValueError:
        raise
    except Exception as exc:
        logger.error("create_policy failed: %s", exc)
        raise


def list_policies(api_key: str, include_disabled: bool = False) -> List[Dict[str, Any]]:
    """List all policies for an org."""
    _ensure_tables()
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                if include_disabled:
                    cur.execute(
                        "SELECT * FROM policies WHERE api_key_hash = %s ORDER BY name, version DESC",
                        (key_h,),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM policies WHERE api_key_hash = %s AND enabled = TRUE ORDER BY name",
                        (key_h,),
                    )
                return [_format_policy(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.error("list_policies failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Policy evaluation engine
# ---------------------------------------------------------------------------

OPERATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: float(a) > float(b),
    ">=": lambda a, b: float(a) >= float(b),
    "<": lambda a, b: float(a) < float(b),
    "<=": lambda a, b: float(a) <= float(b),
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in str(a),
    "matches": lambda a, b: bool(re.search(b, str(a))),
}


def evaluate_policies(
    api_key: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Evaluate all active policies against a request context.
    Context fields: model, provider, cost, task_type, agent_name,
    data_classification, action, etc.

    Returns: {allowed: bool, effect: str, violations: [...], evaluated: int}
    """
    _ensure_tables()
    key_h = hash_key(api_key)

    agent_name = context.get("agent_name", "")
    action = context.get("action", "")

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM policies WHERE api_key_hash = %s AND enabled = TRUE ORDER BY name",
                    (key_h,),
                )
                policies = cur.fetchall()

                if not policies:
                    # Seed policies on first evaluation
                    seeded = seed_policies(api_key)
                    if seeded > 0:
                        cur.execute(
                            "SELECT * FROM policies WHERE api_key_hash = %s AND enabled = TRUE ORDER BY name",
                            (key_h,),
                        )
                        policies = cur.fetchall()

                violations = []
                evaluated = 0
                worst_effect = "allow"
                effect_severity = {"allow": 0, "log": 1, "warn": 2, "require_approval": 3, "block": 4}

                for policy in policies:
                    # Check scope
                    scope = policy["scope"] or {}
                    agents_scope = scope.get("agents", ["*"])
                    actions_scope = scope.get("actions", ["*"])

                    if "*" not in agents_scope and agent_name not in agents_scope:
                        matched = False
                        for pattern in agents_scope:
                            if pattern.endswith("*") and agent_name.startswith(pattern[:-1]):
                                matched = True
                                break
                        if not matched:
                            continue

                    if "*" not in actions_scope and action not in actions_scope:
                        continue

                    # Evaluate conditions
                    conditions = policy["conditions"] or []
                    all_match = True
                    matched_condition = None

                    for cond in conditions:
                        field = cond.get("field", "")
                        operator = cond.get("operator", "==")
                        expected = cond.get("value")

                        actual = context.get(field)
                        if actual is None:
                            all_match = False
                            break

                        op_fn = OPERATORS.get(operator)
                        if not op_fn:
                            all_match = False
                            break

                        try:
                            if not op_fn(actual, expected):
                                all_match = False
                                break
                        except (ValueError, TypeError):
                            all_match = False
                            break

                        matched_condition = f"{field} {operator} {expected}"

                    evaluated += 1

                    if all_match and conditions:
                        effect = policy["effect"]
                        violation = {
                            "policy_name": policy["name"],
                            "policy_id": str(policy["policy_id"]),
                            "effect": effect,
                            "matched_condition": matched_condition,
                            "description": policy["description"],
                        }
                        violations.append(violation)

                        # Log evaluation
                        cur.execute(
                            """
                            INSERT INTO policy_evaluations
                                (policy_id, api_key_hash, agent_name, action, context, effect, rule_matched)
                            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                            """,
                            (
                                policy["policy_id"], key_h, agent_name, action,
                                json.dumps(context, default=str),
                                effect, matched_condition,
                            ),
                        )

                        # Log violation
                        cur.execute(
                            """
                            INSERT INTO policy_violations
                                (policy_id, policy_name, api_key_hash, agent_name, action,
                                 context, effect, message)
                            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                            """,
                            (
                                policy["policy_id"], policy["name"], key_h,
                                agent_name, action,
                                json.dumps(context, default=str),
                                effect,
                                f"Policy '{policy['name']}' triggered: {matched_condition}",
                            ),
                        )

                        if effect_severity.get(effect, 0) > effect_severity.get(worst_effect, 0):
                            worst_effect = effect

                allowed = worst_effect not in ("block",)

                return {
                    "allowed": allowed,
                    "effect": worst_effect,
                    "violations_count": len(violations),
                    "violations": violations,
                    "policies_evaluated": evaluated,
                    "context_evaluated": context,
                }

    except Exception as exc:
        logger.error("evaluate_policies failed: %s", exc)
        raise


def get_violations(
    api_key: str,
    days: int = 30,
    unresolved_only: bool = False,
) -> Dict[str, Any]:
    """Get policy violation history."""
    _ensure_tables()
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                where = "api_key_hash = %s AND violated_at >= NOW() - INTERVAL '%s days'"
                params = [key_h, days]

                if unresolved_only:
                    where += " AND resolved = FALSE"

                cur.execute(
                    f"""
                    SELECT * FROM policy_violations
                    WHERE {where}
                    ORDER BY violated_at DESC
                    LIMIT 100
                    """,
                    params,
                )
                violations = []
                for r in cur.fetchall():
                    violations.append({
                        "violation_id": str(r["violation_id"]),
                        "policy_name": r["policy_name"],
                        "agent_name": r["agent_name"],
                        "action": r["action"],
                        "effect": r["effect"],
                        "message": r["message"],
                        "resolved": r["resolved"],
                        "violated_at": r["violated_at"].isoformat(),
                    })

                # Summary stats
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE effect = 'block') AS blocked,
                        COUNT(*) FILTER (WHERE effect = 'warn') AS warned,
                        COUNT(*) FILTER (WHERE effect = 'require_approval') AS approval_required,
                        COUNT(*) FILTER (WHERE effect = 'log') AS logged,
                        COUNT(*) FILTER (WHERE resolved = FALSE) AS unresolved
                    FROM policy_violations
                    WHERE api_key_hash = %s AND violated_at >= NOW() - INTERVAL '%s days'
                    """,
                    (key_h, days),
                )
                stats = cur.fetchone()

                return {
                    "period_days": days,
                    "total_violations": stats["total"],
                    "blocked": stats["blocked"],
                    "warned": stats["warned"],
                    "approval_required": stats["approval_required"],
                    "logged": stats["logged"],
                    "unresolved": stats["unresolved"],
                    "violations": violations,
                }

    except Exception as exc:
        logger.error("get_violations failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_policy(row) -> Dict[str, Any]:
    return {
        "policy_id": str(row["policy_id"]),
        "name": row["name"],
        "description": row["description"],
        "version": row["version"],
        "enabled": row["enabled"],
        "effect": row["effect"],
        "conditions": row["conditions"],
        "scope": row["scope"],
        "created_at": row["created_at"].isoformat(),
    }
