"""transfer 模块单元测试。

仅覆盖纯逻辑（scp 命令行构建）——真实 scp 传输需要系统 sshd，
见 CONTRIBUTING.md 的「手动冒烟清单」。
"""

from sshm.transfer import _build_scp_cmd
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
    def test_password_auth_uses_capital_P_port_no_identity(self):
        cmd = _build_scp_cmd(_password_server(), "local.txt", "admin@1.2.3.4:/tmp/")
        assert cmd == ["scp", "-P", "22", "local.txt", "admin@1.2.3.4:/tmp/"]

    def test_key_auth_includes_identity_flag(self):
        cmd = _build_scp_cmd(_key_server(), "local.txt", "admin@1.2.3.4:/tmp/")
        assert cmd == [
            "scp", "-P", "22", "-i", "/home/u/.ssh/id_ed25519",
            "local.txt", "admin@1.2.3.4:/tmp/",
        ]

    def test_custom_port_reflected_as_capital_P(self):
        cmd = _build_scp_cmd(_password_server(port=2222), "a", "b")
        assert cmd[:3] == ["scp", "-P", "2222"]

    def test_download_order_source_remote_destination_local(self):
        # scp_download 把远程放 source、本地放 destination
        cmd = _build_scp_cmd(_password_server(), "admin@1.2.3.4:/var/log/x", "./x")
        assert cmd[-2] == "admin@1.2.3.4:/var/log/x"
        assert cmd[-1] == "./x"

    def test_key_auth_without_key_path_omits_identity(self):
        # ServerConfig 要求 key 必须有 key_path；构造后清空以测防御分支
        server = _key_server()
        server.key_path = None
        cmd = _build_scp_cmd(server, "a", "b")
        assert "-i" not in cmd
        assert cmd == ["scp", "-P", "22", "a", "b"]
