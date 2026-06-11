"""vault 模块单元测试。"""

import pytest
from sshm.vault import ServerConfig


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
            ServerConfig(name="", host="1.2.3.4", user="root", auth_type="key", key_path="/key")

    def test_missing_host_raises(self):
        with pytest.raises(ValueError, match="host is required"):
            ServerConfig(name="test", host="", user="root", auth_type="key", key_path="/key")

    def test_invalid_port_raises(self):
        with pytest.raises(ValueError, match="invalid port"):
            ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="key", key_path="/key", port=99999)

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
        raw = {"name": "test", "host": "1.2.3.4", "user": "root", "auth_type": "key", "key_path": "~/.ssh/id_rsa"}
        raw_copy = raw.copy()
        ServerConfig.from_dict(raw)
        assert raw == raw_copy

    def test_to_dict(self):
        server = ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="key", key_path="/key")
        d = server.to_dict()
        assert d["name"] == "test"
        assert d["port"] == 22
        assert isinstance(d, dict)
