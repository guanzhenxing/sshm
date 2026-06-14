"""cli 模块单元测试。"""

import argparse
import os
import tempfile
from unittest.mock import patch

import pytest

from sshm.cli import get_password, get_vault_password, main
from sshm.vault import Vault

MASTER_PW = "test-master-password"


def _args(no_cache: bool = False) -> argparse.Namespace:
    return argparse.Namespace(no_cache=no_cache)


@pytest.fixture
def fresh_vault():
    """临时 vault（已 init、含一台服务器），用于 get_vault_password 校验。"""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "vault.enc")
        vault = Vault(path)
        vault.init(MASTER_PW)
        yield vault


class TestGetPassword:
    @patch("sshm.cli.getpass.getpass")
    def test_returns_input(self, mock_getpass):
        mock_getpass.return_value = "my-password"
        result = get_password("Enter password: ")
        assert result == "my-password"


class TestGetVaultPassword:
    """会话缓存读写契约：缓存未写入是本项目曾经的真实 bug，这些用例锁定修复。"""

    @patch("sshm.cli.store_password")
    @patch("sshm.cli.get_password")
    @patch("sshm.cli.load_password")
    def test_valid_cache_skips_prompt(self, mock_load, mock_prompt, mock_store, fresh_vault):
        """缓存命中且有效 → 直接返回缓存，不提示、不写入。"""
        mock_load.return_value = MASTER_PW
        result = get_vault_password(_args(), fresh_vault)
        assert result == MASTER_PW
        mock_prompt.assert_not_called()
        mock_store.assert_not_called()

    @patch("sshm.cli.store_password")
    @patch("sshm.cli.get_password")
    @patch("sshm.cli.load_password")
    def test_cache_miss_prompts_and_caches(self, mock_load, mock_prompt, mock_store, fresh_vault):
        """缓存缺失 → 提示输入；校验通过后写入缓存，下次免输。"""
        mock_load.return_value = None
        mock_prompt.return_value = MASTER_PW
        result = get_vault_password(_args(), fresh_vault)
        assert result == MASTER_PW
        mock_store.assert_called_once_with(MASTER_PW)

    @patch("sshm.cli.clear_password")
    @patch("sshm.cli.store_password")
    @patch("sshm.cli.get_password")
    @patch("sshm.cli.load_password")
    def test_stale_cache_cleared_then_reprompt(self, mock_load, mock_prompt, mock_store,
                                               mock_clear, fresh_vault):
        """缓存命中但已失效（密码已改）→ 清掉失效缓存，回落到提示并写入新密码。"""
        mock_load.return_value = "stale-wrong-password"
        mock_prompt.return_value = MASTER_PW
        result = get_vault_password(_args(), fresh_vault)
        assert result == MASTER_PW
        mock_clear.assert_called_once()
        mock_store.assert_called_once_with(MASTER_PW)

    @patch("sshm.cli.store_password")
    @patch("sshm.cli.get_password")
    @patch("sshm.cli.load_password")
    def test_wrong_password_retries_until_correct(self, mock_load, mock_prompt, mock_store,
                                                  fresh_vault):
        """输错密码应重试（而非缓存错误密码或抛栈）。"""
        mock_load.return_value = None
        mock_prompt.side_effect = ["wrong-once", MASTER_PW]
        result = get_vault_password(_args(), fresh_vault)
        assert result == MASTER_PW
        assert mock_prompt.call_count == 2
        mock_store.assert_called_once_with(MASTER_PW)

    @patch("sshm.cli.store_password")
    @patch("sshm.cli.get_password")
    @patch("sshm.cli.load_password")
    def test_no_cache_neither_reads_nor_writes(self, mock_load, mock_prompt, mock_store,
                                               fresh_vault):
        """--no-cache：既不读也不写 Keychain，每次提示。"""
        mock_prompt.return_value = MASTER_PW
        result = get_vault_password(_args(no_cache=True), fresh_vault)
        assert result == MASTER_PW
        mock_load.assert_not_called()
        mock_store.assert_not_called()


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
        with patch("sshm.cli.clear_password") as mock_clear:
            with patch("sys.argv", ["sshm", "lock"]):
                main()
            mock_clear.assert_called_once()
