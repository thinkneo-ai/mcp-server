"""Auth bypass tests — protected tools must reject unauthorized access."""

import pytest
from src.auth import _bearer_token, is_authenticated, require_auth
from unittest.mock import patch, MagicMock


@pytest.mark.security
class TestAuthBypass:
    def test_no_token_not_authenticated(self):
        ctx = _bearer_token.set(None)
        try:
            assert is_authenticated() is False
        finally:
            _bearer_token.reset(ctx)

    def test_empty_string_not_authenticated(self):
        ctx = _bearer_token.set("")
        try:
            assert is_authenticated() is False
        finally:
            _bearer_token.reset(ctx)

    def test_invalid_token_not_authenticated(self):
        ctx = _bearer_token.set("invalid-key-12345")
        try:
            with patch("src.auth.get_settings") as ms:
                s = MagicMock()
                s.valid_api_keys = {"real-key-only"}
                s.require_auth = True
                ms.return_value = s
                assert is_authenticated() is False
        finally:
            _bearer_token.reset(ctx)

    def test_require_auth_raises_without_token(self):
        ctx = _bearer_token.set(None)
        try:
            with pytest.raises(ValueError, match="Authentication required"):
                require_auth()
        finally:
            _bearer_token.reset(ctx)

    def test_valid_token_is_authenticated(self):
        ctx = _bearer_token.set("valid-master-key")
        try:
            with patch("src.auth.get_settings") as ms:
                s = MagicMock()
                s.valid_api_keys = {"valid-master-key"}
                s.require_auth = True
                ms.return_value = s
                assert is_authenticated() is True
        finally:
            _bearer_token.reset(ctx)

    def test_require_auth_returns_token(self):
        ctx = _bearer_token.set("valid-master-key")
        try:
            with patch("src.auth.get_settings") as ms:
                s = MagicMock()
                s.valid_api_keys = {"valid-master-key"}
                s.require_auth = True
                ms.return_value = s
                token = require_auth()
                assert token == "valid-master-key"
        finally:
            _bearer_token.reset(ctx)
