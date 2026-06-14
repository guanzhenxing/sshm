"""cli 模块单元测试。"""

import os
import tempfile
from unittest.mock import patch

import pytest

from sshm.cli import get_password, main


class TestGetPassword:
    @patch("sshm.cli.getpass.getpass")
    def test_returns_input(self, mock_getpass):
        mock_getpass.return_value = "my-password"
        result = get_password("Enter password: ")
        assert result == "my-password"


class TestCLIParsing:
    def test_help_exits(self):
        with patch("sys.argv", ["sshm", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_init_creates_vault(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = os.path.join(tmpdir, "vault.enc")
            with patch("sshm.cli.getpass.getpass", return_value="test-password"):
                with patch("sys.argv", ["sshm", "--vault", vault_path, "init"]):
                    main()
            assert os.path.exists(vault_path)

    def test_ls_no_vault_shows_error(self):
        with patch("sys.argv", ["sshm", "ls", "--vault", "/nonexistent/vault.enc"]):
            with pytest.raises(SystemExit):
                main()

    def test_lock_runs(self):
        with patch("sshm.cli.clear_key") as mock_clear:
            with patch("sys.argv", ["sshm", "lock"]):
                main()
            mock_clear.assert_called_once()
