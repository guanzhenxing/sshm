"""ssh 模块单元测试。

纯逻辑部分（交互提示检测、host key 变更检测、命令构建）+ pty_connect 的
行为级冒烟（真实子进程跑在 pty 里，不依赖 sshd）。真实 ssh 连接的手动
冒烟清单见 CONTRIBUTING.md。
"""

import os
import sys

from sshm.ssh import (
    CONNECT_TIMEOUT,
    _build_ssh_key_cmd,
    _is_host_key_changed,
    _needs_user_input,
    pty_connect,
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


class TestPtyConnect:
    """pty_connect 冒烟：密钥认证路径（password=None）的实时中继与退出码。

    回归：密钥认证此前用 subprocess 捕获 stdout/stderr，会话输出全程被吞——
    用户只能盲打。现在统一 pty 中继：输出实时透传、退出码原样返回。
    """

    def _fake_stdin(self, monkeypatch):
        """stdin 换成保持打开的管道读端：select 不会 EOF，不干扰中继循环。"""
        r, w = os.pipe()
        monkeypatch.setattr(sys, "stdin", os.fdopen(r, "rb"))
        return w

    def test_exit_zero(self, monkeypatch):
        w = self._fake_stdin(monkeypatch)
        try:
            rc = pty_connect(["/bin/sh", "-c", "exit 0"], password=None, timeout=5)
        finally:
            os.close(w)
        assert rc == 0

    def test_nonzero_exit_code_propagated(self, monkeypatch):
        """退出码应是 waitstatus_to_exitcode 的值（3），而非 waitpid 裸状态（768）。

        回归：此前返回裸 status，sys.exit(768) 截断后成 0——失败被当成成功。
        """
        w = self._fake_stdin(monkeypatch)
        try:
            rc = pty_connect(["/bin/sh", "-c", "exit 3"], password=None, timeout=5)
        finally:
            os.close(w)
        assert rc == 3

    def test_output_relayed_live(self, monkeypatch, capfd):
        """子进程输出实时透传到 stdout（不再被捕获丢弃）。"""
        w = self._fake_stdin(monkeypatch)
        try:
            rc = pty_connect(["/bin/echo", "hello-relay"], password=None, timeout=5)
        finally:
            os.close(w)
        assert rc == 0
        assert "hello-relay" in capfd.readouterr().out

    def test_stdin_eof_does_not_hang_waitpid(self, monkeypatch, capfd):
        """stdin EOF（如 sshm 被 `</dev/null` 调用）不提前结束会话。

        回归：macOS 上 pty master 未读空前子进程无法完成退出——此前在
        stdin EOF 时直接 break 去 waitpid，子进程卡死在 exiting 状态、
        waitpid 永久阻塞。现在 EOF 只停止监听 stdin，中继继续到子进程退出。
        """
        devnull = os.open(os.devnull, os.O_RDONLY)
        monkeypatch.setattr(sys, "stdin", os.fdopen(devnull, "rb"))
        rc = pty_connect(["/bin/sh", "-c", "echo still-alive; exit 5"],
                         password=None, timeout=5)
        assert rc == 5
        assert "still-alive" in capfd.readouterr().out
