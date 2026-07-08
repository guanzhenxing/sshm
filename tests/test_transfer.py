"""transfer 模块单元测试。

仅覆盖纯逻辑（scp 命令行构建）——真实 scp 传输需要系统 sshd，
见 CONTRIBUTING.md 的「手动冒烟清单」。
"""

from sshm.ssh import CONNECT_TIMEOUT
from sshm.transfer import _SCP_SSH_OPTS, _build_scp_cmd
from sshm.vault import ServerConfig


def _key_server(port: int = 22, key_path: str = "/home/u/.ssh/id_ed25519") -> ServerConfig:
    return ServerConfig(
        name="s", host="1.2.3.4", port=port, user="admin",
        auth_type="key", key_path=key_path,
    )


def _password_server(port: int = 22) -> ServerConfig:
    return ServerConfig(
        name="s", host="1.2.3.4", port=port, user="admin",
        auth_type="password", password="x",
    )


class TestBuildScpCmd:
    def test_password_auth_includes_ssh_options(self):
        cmd = _build_scp_cmd(_password_server(), "local.txt", "admin@1.2.3.4:/tmp/")
        assert cmd[:3] == ["scp", "-P", "22"]
        assert _SCP_SSH_OPTS[0] in cmd and _SCP_SSH_OPTS[1] in cmd
        assert cmd[-2:] == ["local.txt", "admin@1.2.3.4:/tmp/"]

    def test_key_auth_includes_identity_flag(self):
        cmd = _build_scp_cmd(_key_server(), "local.txt", "admin@1.2.3.4:/tmp/")
        assert "-i" in cmd
        assert "/home/u/.ssh/id_ed25519" in cmd
        assert cmd[-2:] == ["local.txt", "admin@1.2.3.4:/tmp/"]

    def test_custom_port_reflected_as_capital_P(self):
        cmd = _build_scp_cmd(_password_server(port=2222), "a", "b")
        assert "2222" in cmd

    def test_includes_connect_timeout(self):
        cmd = _build_scp_cmd(_password_server(), "a", "b")
        assert "-o" in cmd
        assert f"ConnectTimeout={CONNECT_TIMEOUT}" in cmd

    def test_includes_strict_host_key_checking(self):
        cmd = _build_scp_cmd(_password_server(), "a", "b")
        assert "StrictHostKeyChecking=accept-new" in cmd

    def test_download_order_source_remote_destination_local(self):
        cmd = _build_scp_cmd(_password_server(), "admin@1.2.3.4:/var/log/x", "./x")
        assert cmd[-2] == "admin@1.2.3.4:/var/log/x"
        assert cmd[-1] == "./x"

    def test_key_auth_without_key_path_omits_identity(self):
        server = _key_server()
        server.key_path = None
        cmd = _build_scp_cmd(server, "a", "b")
        assert "-i" not in cmd
