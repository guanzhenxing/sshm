"""session 模块单元测试。"""

import json
import time
from unittest.mock import MagicMock, patch

from sshm.session import clear_key, load_key, store_key


class TestStoreKey:
    @patch("sshm.session.subprocess.run")
    def test_stores_key_with_ttl(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        store_key("abcdef123456", ttl=3600)
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "add-generic-password" in args[0][0]
        payload = json.loads(args[1]["input"].decode("utf-8"))
        assert payload["key"] == "abcdef123456"
        assert payload["expires_at"] > time.time()


class TestLoadKey:
    @patch("sshm.session.subprocess.run")
    def test_load_valid_key(self, mock_run):
        payload = json.dumps({"key": "abcdef123456", "expires_at": time.time() + 3600})
        mock_run.return_value = MagicMock(returncode=0, stdout=payload)
        result = load_key()
        assert result == "abcdef123456"

    @patch("sshm.session.subprocess.run")
    def test_load_expired_key_returns_none(self, mock_run):
        payload = json.dumps({"key": "abcdef123456", "expires_at": time.time() - 100})
        mock_run.return_value = MagicMock(returncode=0, stdout=payload)
        result = load_key()
        assert result is None

    @patch("sshm.session.subprocess.run")
    def test_load_no_key_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=44)
        result = load_key()
        assert result is None


class TestClearKey:
    @patch("sshm.session.subprocess.run")
    def test_clear_calls_delete(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        clear_key()
        mock_run.assert_called_once()
        assert "delete-generic-password" in mock_run.call_args[0][0]
