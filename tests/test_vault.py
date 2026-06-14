"""vault 模块单元测试。"""

import os
import tempfile

import pytest
from cryptography.exceptions import InvalidTag

from sshm.vault import ServerConfig, Vault


class TestServerConfig:
    def test_valid_key_auth(self):
        server = ServerConfig(
            name="prod-web", host="192.168.1.100", user="admin",
            auth_type="key", key_path="/home/user/.ssh/id_rsa",
        )
        assert server.name == "prod-web"
        assert server.port == 22

    def test_valid_password_auth(self):
        server = ServerConfig(
            name="staging", host="10.0.0.50", user="deploy",
            auth_type="password", password="secret123", port=2222, group="staging",
        )
        assert server.auth_type == "password"
        assert server.port == 2222

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="name is required"):
            ServerConfig(
                name="", host="1.2.3.4", user="root",
                auth_type="key", key_path="/key",
            )

    def test_missing_host_raises(self):
        with pytest.raises(ValueError, match="host is required"):
            ServerConfig(
                name="test", host="", user="root",
                auth_type="key", key_path="/key",
            )

    def test_invalid_port_raises(self):
        with pytest.raises(ValueError, match="invalid port"):
            ServerConfig(
                name="test", host="1.2.3.4", user="root",
                auth_type="key", key_path="/key", port=99999,
            )

    def test_key_auth_without_key_path_raises(self):
        with pytest.raises(ValueError, match="key_path required"):
            ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="key")

    def test_password_auth_without_password_raises(self):
        with pytest.raises(ValueError, match="password required"):
            ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="password")

    def test_invalid_auth_type_raises(self):
        with pytest.raises(ValueError, match="invalid auth_type"):
            ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="token")

    def test_tilde_expansion(self):
        server = ServerConfig.from_dict({
            "name": "test", "host": "1.2.3.4", "user": "root",
            "auth_type": "key", "key_path": "~/.ssh/id_rsa",
        })
        assert "~" not in server.key_path
        assert server.key_path.startswith("/")

    def test_from_dict_does_not_mutate_input(self):
        raw = {
            "name": "test", "host": "1.2.3.4", "user": "root",
            "auth_type": "key", "key_path": "~/.ssh/id_rsa",
        }
        raw_copy = raw.copy()
        ServerConfig.from_dict(raw)
        assert raw == raw_copy

    def test_to_dict(self):
        server = ServerConfig(
            name="test", host="1.2.3.4", user="root",
            auth_type="key", key_path="/key",
        )
        d = server.to_dict()
        assert d["name"] == "test"
        assert d["port"] == 22
        assert isinstance(d, dict)


class TestVault:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.tmpdir, "vault.enc")
        self.vault = Vault(self.vault_path)
        self.password = "test-master-password"

    def test_init_creates_vault_file(self):
        self.vault.init(self.password)
        assert os.path.exists(self.vault_path)

    def test_init_refuses_if_exists(self):
        self.vault.init(self.password)
        with pytest.raises(FileExistsError):
            self.vault.init(self.password)

    def test_init_force_overwrites(self):
        self.vault.init(self.password)
        self.vault.init("new-password", force=True)
        data = self.vault.load("new-password")
        assert data["servers"] == []

    def test_load_returns_dict(self):
        self.vault.init(self.password)
        data = self.vault.load(self.password)
        assert data["version"] == 1
        assert data["servers"] == []

    def test_wrong_password_load_fails(self):
        self.vault.init(self.password)
        with pytest.raises(InvalidTag):
            self.vault.load("wrong-password")

    def test_add_and_list_servers(self):
        self.vault.init(self.password)
        server = ServerConfig(
            name="test", host="1.2.3.4", user="root",
            auth_type="password", password="pass",
        )
        self.vault.add_server(server, self.password)
        servers = self.vault.list_servers(self.password)
        assert len(servers) == 1
        assert servers[0].name == "test"

    def test_remove_server_by_name(self):
        self.vault.init(self.password)
        s = ServerConfig(
            name="to-delete", host="1.2.3.4", user="root",
            auth_type="password", password="pass",
        )
        self.vault.add_server(s, self.password)
        self.vault.remove_server("to-delete", self.password)
        assert len(self.vault.list_servers(self.password)) == 0

    def test_remove_server_by_index(self):
        self.vault.init(self.password)
        s = ServerConfig(
            name="first", host="1.2.3.4", user="root",
            auth_type="password", password="pass",
        )
        self.vault.add_server(s, self.password)
        self.vault.remove_server("1", self.password)
        assert len(self.vault.list_servers(self.password)) == 0

    def test_remove_nonexistent_raises(self):
        self.vault.init(self.password)
        with pytest.raises(ValueError):
            self.vault.remove_server("nonexistent", self.password)

    def test_edit_server(self):
        self.vault.init(self.password)
        s = ServerConfig(
            name="edit-me", host="1.2.3.4", user="root",
            auth_type="password", password="pass",
        )
        self.vault.add_server(s, self.password)
        self.vault.edit_server("edit-me", {"host": "5.6.7.8", "port": 2222}, self.password)
        servers = self.vault.list_servers(self.password)
        assert servers[0].host == "5.6.7.8"
        assert servers[0].port == 2222

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            self.vault.load(self.password)

    def test_vault_file_is_not_plaintext(self):
        self.vault.init(self.password)
        s = ServerConfig(
            name="secret-server", host="10.0.0.1", user="admin",
            auth_type="password", password="hunter2",
        )
        self.vault.add_server(s, self.password)
        with open(self.vault_path, "rb") as f:
            raw = f.read()
        assert b"secret-server" not in raw
        assert b"hunter2" not in raw


class TestMergeServers:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.tmpdir, "vault.enc")
        self.vault = Vault(self.vault_path)
        self.password = "test-master-password"
        self.vault.init(self.password)
        self.vault.add_server(
            ServerConfig(name="alpha", host="1.1.1.1", user="root",
                         auth_type="password", password="x"),
            self.password,
        )

    def _import_list(self, names):
        return [
            ServerConfig(name=n, host="9.9.9.9", user="root",
                         auth_type="password", password="x")
            for n in names
        ]

    def test_skip_strategy_keeps_existing(self):
        report = self.vault.merge_servers(
            self._import_list(["alpha", "beta"]), "skip", self.password,
        )
        assert report.added == ["beta"]
        assert report.skipped == ["alpha"]
        names = [s.name for s in self.vault.list_servers(self.password)]
        assert names == ["alpha", "beta"]

    def test_overwrite_strategy_replaces(self):
        incoming = [
            ServerConfig(name="alpha", host="5.5.5.5", port=2222, user="admin",
                         auth_type="password", password="new"),
        ]
        report = self.vault.merge_servers(incoming, "overwrite", self.password)
        assert report.overwritten == ["alpha"]
        servers = self.vault.list_servers(self.password)
        assert len(servers) == 1
        assert servers[0].host == "5.5.5.5"
        assert servers[0].port == 2222

    def test_rename_strategy_avoids_collision(self):
        incoming = self._import_list(["alpha", "alpha"])
        report = self.vault.merge_servers(incoming, "rename", self.password)
        # 第一台 alpha 碰撞 → alpha-2；第二台 alpha 碰撞 → alpha-3
        assert report.renamed == [("alpha", "alpha-2"), ("alpha", "alpha-3")]
        names = sorted(s.name for s in self.vault.list_servers(self.password))
        assert names == ["alpha", "alpha-2", "alpha-3"]

    def test_dry_run_does_not_persist(self):
        report = self.vault.merge_servers(
            self._import_list(["beta"]), "skip", self.password, dry_run=True,
        )
        assert report.added == ["beta"]
        # dry-run 不落盘：vault 里仍只有 alpha
        names = [s.name for s in self.vault.list_servers(self.password)]
        assert names == ["alpha"]

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="未知合并策略"):
            self.vault.merge_servers(
                self._import_list(["beta"]), "bogus", self.password,
            )
