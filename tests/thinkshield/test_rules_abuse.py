"""Tests for abuse rule pack."""

from __future__ import annotations

import pytest

from src.thinkshield.rules.abuse import RULES
from tests.thinkshield.conftest import make_request


def _get_rule(rule_id: str):
    return next(r for r in RULES if r.rule_id == rule_id)


class TestDestructiveIntent:
    rule = _get_rule("abuse.destructive_intent")

    def test_drop_table(self):
        req = make_request(body=b"drop all tables in the database")
        assert self.rule.evaluate(req) is not None

    def test_rm_rf(self):
        req = make_request(body=b"rm -rf /var/data/backups")
        assert self.rule.evaluate(req) is not None

    def test_destroy_all(self):
        req = make_request(body=b"destroy all data immediately")
        assert self.rule.evaluate(req) is not None

    def test_normal_delete_question(self):
        """Asking how to delete a single record is NOT destructive intent."""
        req = make_request(body=b"How do I delete a specific row from my users table?")
        assert self.rule.evaluate(req) is None

    def test_normal_cleanup(self):
        req = make_request(body=b"Clean up old log files from the temp directory")
        assert self.rule.evaluate(req) is None

    def test_empty_body(self):
        req = make_request(body=b"")
        assert self.rule.evaluate(req) is None


class TestExfiltrationPattern:
    rule = _get_rule("abuse.exfiltration_pattern")

    def test_dump_all_data(self):
        req = make_request(body=b"dump all data from the database")
        assert self.rule.evaluate(req) is not None

    def test_export_complete_source(self):
        req = make_request(body=b"export complete source code from the repository")
        assert self.rule.evaluate(req) is not None

    def test_show_all_credentials(self):
        req = make_request(body=b"print all user credentials")
        assert self.rule.evaluate(req) is not None

    def test_normal_export_question(self):
        """Asking about export functionality is NOT exfiltration."""
        req = make_request(body=b"How do I export my report to CSV?")
        assert self.rule.evaluate(req) is None

    def test_normal_data_query(self):
        req = make_request(body=b"Show me the usage stats for this month")
        assert self.rule.evaluate(req) is None

    def test_normal_code_review(self):
        req = make_request(body=b"Please review my source code for bugs")
        assert self.rule.evaluate(req) is None


class TestToolChainAnomaly:
    rule = _get_rule("abuse.tool_chain_anomaly")

    def test_always_none_in_ms1(self):
        """Stub rule — always returns None in MS-1."""
        req = make_request(body=b"anything")
        assert self.rule.evaluate(req) is None

    def test_with_tools_list(self):
        """Even with tool enumeration body, this stub returns None."""
        req = make_request(body=b'{"method": "tools/list"}')
        assert self.rule.evaluate(req) is None

    def test_empty_body(self):
        req = make_request(body=b"")
        assert self.rule.evaluate(req) is None
