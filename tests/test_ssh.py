"""ssh 模块单元测试。

仅覆盖纯逻辑（交互提示检测、host key 变更检测、密钥认证命令构建）——真实 ssh
连接需要系统 sshd，见 CONTRIBUTING.md 的「手动冒烟清单」。
"""

from sshm.ssh import (
    CONNECT_TIMEOUT,
    _build_ssh_key_cmd,
    _is_host_key_changed,
    _needs_user_input,
)
from sshm.vault import ServerConfig


def _key_server(port: int = 22, key_path: str = "/home/u/.ssh/id_ed25519") -> ServerConfig:
    return ServerConfig(
        name="s", host="1.2.3.4", port=port, user="admin",
        auth_type="key", key_path=key_path,
    )


class TestNeedsUserInput:
    def test_hostkey_yesno_prompt_is_user_input(self):
        banner = (
            b"The authenticity of host '1.2.3.4' can't be established.\n"
            b"Are you sure you want to continue connecting (yes/no/[fingerprint])? "
        )
        assert _needs_user_input(banner) is True

    def test_short_yesno_form(self):
        assert _needs_user_input(b"Please type (yes/no)? ") is True

    def test_password_prompt_is_not_flagged_as_user_input(self):
        # password 提示由密码注入逻辑处理，不应被当作"需要用户输入"
        assert _needs_user_input(b"admin@1.2.3.4's password: ") is False

    def test_empty_banner(self):
        assert _needs_user_input(b"") is False

    def test_plain_banner_without_prompt(self):
        assert _needs_user_input(b"Last login: Fri Jun 13 10:00:00 2026 from 10.0.0.1") is False


class TestIsHostKeyChanged:
    def test_detects_remote_host_identification_changed(self):
        banner = b"""@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
IT IS POSSIBLE THAT SOMEONE IS DOING SOMETHING NASTY!
"""
        assert _is_host_key_changed(banner) is True

    def test_detects_possible_dns_spoofing(self):
        banner = (
            b"WARNING: POSSIBLE DNS SPOOFING DETECTED!\n"
            b"The RSA host key for example.com has changed."
        )
        assert _is_host_key_changed(banner) is True

    def test_detects_host_key_verification_failed(self):
        assert _is_host_key_changed(b"Host key verification failed.") is True

    def test_normal_banner_is_not_host_key_change(self):
        assert _is_host_key_changed(
            b"Last login: Fri Jun 13 10:00:00 2026 from 10.0.0.1"
        ) is False

    def test_password_prompt_is_not_host_key_change(self):
        assert _is_host_key_changed(b"admin@1.2.3.4's password: ") is False

    def test_connection_refused_is_not_host_key_change(self):
        assert _is_host_key_changed(
            b"ssh: connect to host 1.2.3.4 port 22: Connection refused"
        ) is False

    def test_empty_banner(self):
        assert _is_host_key_changed(b"") is False


class TestBuildSshKeyCmd:
    def test_includes_port_timeout_hostkey_accept_and_identity(self):
        cmd = _build_ssh_key_cmd(_key_server())
        assert cmd == [
            "ssh",
            "-o", "Port=22",
            "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
            "-o", "StrictHostKeyChecking=accept-new",
            "-i", "/home/u/.ssh/id_ed25519",
            "admin@1.2.3.4",
        ]

    def test_custom_port(self):
        cmd = _build_ssh_key_cmd(_key_server(port=2222))
        assert "Port=2222" in cmd

    def test_omits_identity_when_no_key_path(self):
        # ServerConfig 要求 key 必须有 key_path；构造后清空以测防御分支
        server = _key_server()
        server.key_path = None
        cmd = _build_ssh_key_cmd(server)
        assert "-i" not in cmd
        assert cmd[-1] == "admin@1.2.3.4"
