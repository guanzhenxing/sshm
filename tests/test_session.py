"""session 模块单元测试。"""

import json
import time
from unittest.mock import MagicMock, patch

from sshm.session import clear_password, load_password, store_password


class TestStorePassword:
    @patch("sshm.session.subprocess.run")
    def test_stores_password_with_ttl(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        store_password("my-master-password", ttl=3600)
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "add-generic-password" in args[0][0]
        payload = json.loads(args[1]["input"].decode("utf-8"))
        assert payload["password"] == "my-master-password"
        assert payload["expires_at"] > time.time()


class TestLoadPassword:
    @patch("sshm.session.subprocess.run")
    def test_load_valid_password(self, mock_run):
        payload = json.dumps({"password": "my-master-password", "expires_at": time.time() + 3600})
        mock_run.return_value = MagicMock(returncode=0, stdout=payload)
        result = load_password()
        assert result == "my-master-password"

    @patch("sshm.session.subprocess.run")
    def test_load_expired_password_returns_none(self, mock_run):
        payload = json.dumps({"password": "my-master-password", "expires_at": time.time() - 100})
        mock_run.return_value = MagicMock(returncode=0, stdout=payload)
        result = load_password()
        assert result is None

    @patch("sshm.session.subprocess.run")
    def test_load_no_password_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=44)
        result = load_password()
        assert result is None


class TestClearPassword:
    @patch("sshm.session.subprocess.run")
    def test_clear_calls_delete(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        clear_password()
        mock_run.assert_called_once()
        assert "delete-generic-password" in mock_run.call_args[0][0]
