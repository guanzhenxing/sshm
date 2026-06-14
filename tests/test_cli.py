"""cli 模块单元测试。"""

import argparse
import os
import tempfile
from unittest.mock import patch

import pytest

from sshm.cli import get_password, get_vault_password, main
from sshm.vault import ServerConfig, Vault

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

    def test_version_flag_prints_version(self, capsys):
        from sshm import __version__

        with patch("sys.argv", ["sshm", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert __version__ in (captured.out + captured.err)


class TestExportImport:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.tmpdir, "vault.enc")
        self.vault = Vault(self.vault_path)
        self.vault.init(MASTER_PW)
        self.vault.add_server(
            ServerConfig(name="alpha", host="1.1.1.1", port=22, user="root",
                         auth_type="password", password="x"),
            MASTER_PW,
        )

    def test_export_to_file(self):
        out = os.path.join(self.tmpdir, "exp.json")
        with patch("sshm.cli.getpass.getpass", return_value=MASTER_PW):
            with patch("sys.argv", [
                "sshm", "--vault", self.vault_path, "--no-cache",
                "export", "-o", out,
            ]):
                main()
        from sshm.io import read_export
        loaded = read_export(out)
        assert any(s.name == "alpha" for s in loaded)

    def test_export_encrypt_to_file(self):
        out = os.path.join(self.tmpdir, "exp.enc.json")
        # getpass 依次返回：主密码、导出密码、确认密码
        with patch("sshm.cli.getpass.getpass",
                   side_effect=[MASTER_PW, "expw", "expw"]):
            with patch("sys.argv", [
                "sshm", "--vault", self.vault_path, "--no-cache",
                "export", "-o", out, "--encrypt",
            ]):
                main()
        from sshm.io import read_export
        loaded = read_export(out, decrypt_password="expw")
        assert any(s.name == "alpha" for s in loaded)
        # 加密信封无顶层 servers 键（藏进 data 里）→ 证明确实加密了
        with open(out, encoding="utf-8") as f:
            raw = f.read()
        assert '"servers"' not in raw
        assert '"encrypted": true' in raw

    def test_export_default_stdout(self, capsys):
        with patch("sshm.cli.getpass.getpass", return_value=MASTER_PW):
            with patch("sys.argv", [
                "sshm", "--vault", self.vault_path, "--no-cache", "export",
            ]):
                main()
        captured = capsys.readouterr()
        assert "sshm-export" in captured.out
        assert "alpha" in captured.out

    def test_import_skip_adds_new(self):
        # 先导出一份（含 alpha），再追加 beta 后导第二份；导入第二份 → beta 新增
        exp_with_beta = os.path.join(self.tmpdir, "beta.json")
        self.vault.add_server(
            ServerConfig(name="beta", host="2.2.2.2", port=22, user="root",
                         auth_type="password", password="y"),
            MASTER_PW,
        )
        from sshm.io import write_export
        write_export(self.vault.list_servers(MASTER_PW), exp_with_beta)
        # 把 beta 从 vault 删掉，模拟"目标机只有 alpha"
        self.vault.remove_server("beta", MASTER_PW)

        with patch("sshm.cli.getpass.getpass", return_value=MASTER_PW):
            with patch("sys.argv", [
                "sshm", "--vault", self.vault_path, "--no-cache",
                "import", exp_with_beta, "--skip",
            ]):
                main()
        names = [s.name for s in self.vault.list_servers(MASTER_PW)]
        assert names == ["alpha", "beta"]

    def test_import_overwrite_replaces(self):
        exp = os.path.join(self.tmpdir, "ow.json")
        from sshm.io import write_export
        write_export([
            ServerConfig(name="alpha", host="5.5.5.5", port=2222, user="admin",
                         auth_type="password", password="new"),
        ], exp)
        with patch("sshm.cli.getpass.getpass", return_value=MASTER_PW):
            with patch("sys.argv", [
                "sshm", "--vault", self.vault_path, "--no-cache",
                "import", exp, "--overwrite",
            ]):
                main()
        servers = self.vault.list_servers(MASTER_PW)
        assert len(servers) == 1
        assert servers[0].host == "5.5.5.5"
        assert servers[0].port == 2222

    def test_import_dry_run_does_not_persist(self, capsys):
        exp = os.path.join(self.tmpdir, "dr.json")
        from sshm.io import write_export
        write_export([
            ServerConfig(name="beta", host="2.2.2.2", port=22, user="root",
                         auth_type="password", password="y"),
        ], exp)
        with patch("sshm.cli.getpass.getpass", return_value=MASTER_PW):
            with patch("sys.argv", [
                "sshm", "--vault", self.vault_path, "--no-cache",
                "import", exp, "--dry-run",
            ]):
                main()
        captured = capsys.readouterr()
        assert "dry-run" in captured.out
        # 未落盘
        names = [s.name for s in self.vault.list_servers(MASTER_PW)]
        assert names == ["alpha"]

    def test_import_wrong_explicit_password_friendly_error(self, capsys):
        """加密文件 + 错的 --password → 提示'解密失败，密码错误'并退出，不留 traceback、不落盘。"""
        exp = os.path.join(self.tmpdir, "enc.json")
        from sshm.io import write_export
        write_export(
            [ServerConfig(name="beta", host="2.2.2.2", port=22, user="root",
                          auth_type="password", password="y")],
            exp, encrypt_password="correct-pw",
        )
        with patch("sshm.cli.getpass.getpass", return_value=MASTER_PW):
            with patch("sys.argv", [
                "sshm", "--vault", self.vault_path, "--no-cache",
                "import", exp, "--password", "wrong-pw",
            ]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert "解密失败" in captured.out
        # 未导入任何东西
        names = [s.name for s in self.vault.list_servers(MASTER_PW)]
        assert names == ["alpha"]

    def test_import_wrong_prompted_password_friendly_error(self, capsys):
        """加密文件、未给 --password → 交互提示后输错 → 同样友好提示而非 traceback。"""
        exp = os.path.join(self.tmpdir, "enc2.json")
        from sshm.io import write_export
        write_export(
            [ServerConfig(name="beta", host="2.2.2.2", port=22, user="root",
                          auth_type="password", password="y")],
            exp, encrypt_password="correct-pw",
        )
        # getpass 依次返回：主密码（get_vault_password）、解密密码（prompted，输错）
        with patch("sshm.cli.getpass.getpass",
                   side_effect=[MASTER_PW, "wrong-pw"]):
            with patch("sys.argv", [
                "sshm", "--vault", self.vault_path, "--no-cache",
                "import", exp,
            ]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert "解密失败" in captured.out
        names = [s.name for s in self.vault.list_servers(MASTER_PW)]
        assert names == ["alpha"]
