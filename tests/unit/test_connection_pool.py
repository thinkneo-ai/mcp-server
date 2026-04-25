"""
Tests for the ConnectionPool integration in database.py.
Addresses SEC-06: replaced per-query connections with pool.

Uses mocks — no real DB needed.
"""

import pytest
from unittest.mock import MagicMock

import sys
sys.path.insert(0, ".")

import src.database as db_mod


class TestPoolAPI:
    def test_get_pool_stats_returns_dict(self):
        """get_pool_stats() returns a dict with expected keys."""
        mock_pool = MagicMock()
        mock_pool.get_stats.return_value = {
            "pool_size": 5, "pool_available": 3,
            "requests_waiting": 0, "requests_num": 100,
            "requests_errors": 2, "connections_num": 50,
        }
        old = db_mod._pool
        db_mod._pool = mock_pool
        try:
            stats = db_mod.get_pool_stats()
            assert stats["pool_size"] == 5
            assert stats["pool_available"] == 3
            assert "requests_waiting" in stats
        finally:
            db_mod._pool = old

    def test_close_pool_calls_close(self):
        """close_pool() calls pool.close() and resets to None."""
        mock_pool = MagicMock()
        old = db_mod._pool
        db_mod._pool = mock_pool
        try:
            db_mod.close_pool()
            mock_pool.close.assert_called_once()
            assert db_mod._pool is None
        finally:
            db_mod._pool = old

    def test_get_conn_calls_pool_connection(self):
        """_get_conn() returns pool.connection() context manager."""
        mock_pool = MagicMock()
        mock_cm = MagicMock()
        mock_pool.connection.return_value = mock_cm
        old = db_mod._pool
        db_mod._pool = mock_pool
        try:
            result = db_mod._get_conn()
            mock_pool.connection.assert_called_once()
            assert result is mock_cm
        finally:
            db_mod._pool = old

    def test_hash_key_deterministic(self):
        """hash_key() returns consistent SHA-256."""
        h1 = db_mod.hash_key("test_key")
        h2 = db_mod.hash_key("test_key")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex
