"""SSH 连接模块 — 使用 pty 调用系统 ssh。"""

import os
import pty
import select
import signal
import subprocess
import sys
import termios
import time
import tty

from sshm.vault import ServerConfig

CONNECT_TIMEOUT = 10

# 需要 SSH 时自动接受的选项
_SSH_DEFAULT_OPTS = [
    "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
    "-o", "StrictHostKeyChecking=accept-new",
]

# 最大 host key 修复重试次数（避免死循环）
_MAX_HOST_KEY_RETRIES = 1


def ssh_connect(server: ServerConfig) -> int:
    """连接到 SSH 服务器，返回进程退出码。"""
    if server.auth_type == "key":
        return _ssh_with_key(server)
    else:
        return _ssh_with_password(server)


# ── host key 变更检测与修复 ──────────────────────────────


def _is_host_key_changed(banner: bytes) -> bool:
    """检测 SSH 输出中是否包含 host key 变更警告。"""
    lower = banner.lower()
    return (
        b"remote host identification has changed" in lower
        or b"warning: possible dns spoofing" in lower
        or b"host key verification failed" in lower
    )


def _handle_host_key_change(host: str) -> None:
    """删除 known_hosts 中指定主机的旧 key 并提示用户。"""
    print(f"\nHost key for {host} has changed (server may have been reinstalled).")
    print("Removing old key from known_hosts...")
    subprocess.run(
        ["ssh-keygen", "-R", host],
        capture_output=True,
        timeout=10,
    )
    print("Retrying connection...\n")


def _build_ssh_key_cmd(server: ServerConfig) -> list[str]:
    """构建密钥认证的 ssh 命令行（与 transfer._build_scp_cmd 对称，便于单测）。"""
    cmd = ["ssh", "-o", f"Port={server.port}"] + _SSH_DEFAULT_OPTS
    if server.key_path:
        cmd.extend(["-i", server.key_path])
    cmd.append(f"{server.user}@{server.host}")
    return cmd


def _ssh_with_key(server: ServerConfig) -> int:
    """密钥认证 SSH 连接。"""
    cmd = _build_ssh_key_cmd(server)

    for _attempt in range(_MAX_HOST_KEY_RETRIES + 1):
        print(f"Connecting to {server.user}@{server.host}:{server.port} ...")
        sys.stdout.flush()

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            return 0

        # 连接失败 — 输出 stderr
        stderr = (result.stderr or "").strip()
        if stderr:
            sys.stderr.write(stderr + "\n")
            sys.stderr.flush()

        # 检测 host key 变更并尝试修复
        if _is_host_key_changed(stderr.encode()):
            _handle_host_key_change(server.host)
            continue

        return result.returncode

    return 1


def _ssh_with_password(server: ServerConfig) -> int:
    """密码认证 SSH 连接，使用 pty。

    支持 host key 变更自动修复：检测到 WARNING 后删除旧 key 并重试。
    """
    for _attempt in range(_MAX_HOST_KEY_RETRIES + 1):
        if _attempt > 0:
            print(f"Retrying connection to {server.user}@{server.host}:{server.port} ...")
        rc, retry = _ssh_with_password_once(server)
        if rc == 0:
            return 0
        if not retry:
            return rc
    return 1


def _ssh_with_password_once(server: ServerConfig) -> tuple[int, bool]:
    """单次密码认证 SSH 连接。

    Returns (exit_code, should_retry_for_host_key).
    """
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("ssh", [
            "ssh", "-o", f"Port={server.port}",
        ] + _SSH_DEFAULT_OPTS + [
            f"{server.user}@{server.host}",
        ])
        os._exit(1)

    password = server.password or ""
    authenticated = False
    banner = b""
    host_key_retry_needed = False

    # 确保终端属性可获取
    try:
        old_attrs = termios.tcgetattr(sys.stdin)
    except termios.error:
        old_attrs = None

    try:
        if old_attrs is not None:
            tty.setraw(sys.stdin.fileno())

        def _sigwinch(*_):
            try:
                pty.tcsetwinsize(fd, termios.tcgetwinsize(sys.stdin))
            except Exception:
                pass

        signal.signal(signal.SIGWINCH, _sigwinch)

        while True:
            # 认证前也需要监听 stdin（用于处理 host key 等交互提示）
            sources = [fd]
            if authenticated or _needs_user_input(banner):
                sources.append(sys.stdin)

            rlist, _, _ = select.select(sources, [], [], 30)

            if not rlist:
                if not authenticated:
                    if banner:
                        os.write(sys.stdout.fileno(), banner)
                    raise TimeoutError(
                        f"No password prompt from {server.user}@{server.host} within 30s."
                    )
                continue

            if fd in rlist:
                try:
                    data = os.read(fd, 4096)
                except OSError:
                    break
                if not data:
                    break

                if not authenticated:
                    banner += data

                    # 检测 host key 变更
                    if _is_host_key_changed(banner):
                        os.write(sys.stdout.fileno(), banner)
                        banner = b""
                        _handle_host_key_change(server.host)
                        host_key_retry_needed = True
                        break

                    # 如果出现交互提示（host key 确认等），显示 banner 让用户输入
                    if _needs_user_input(banner):
                        os.write(sys.stdout.fileno(), banner)
                        banner = b""

                    if b"password:" in banner.lower():
                        os.write(fd, password.encode("utf-8") + b"\n")

                        # 检测密码是否被拒绝
                        time.sleep(0.3)
                        r2, _, _ = select.select([fd], [], [], 0.5)
                        if r2:
                            check = os.read(fd, 1024)
                            banner += check
                            rejected = (
                                b"password:" in check.lower()
                                or b"denied" in check.lower()
                                or b"failed" in check.lower()
                            )
                            if rejected:
                                os.write(sys.stdout.fileno(), banner)
                                raise PermissionError(
                                    f"Authentication failed for {server.user}@{server.host}"
                                )

                        authenticated = True
                        os.write(sys.stdout.fileno(), banner)
                else:
                    os.write(sys.stdout.fileno(), data)

            if sys.stdin in rlist:
                try:
                    key = os.read(sys.stdin.fileno(), 4096)
                except OSError:
                    break
                if not key:
                    break
                os.write(fd, key)

    except (TimeoutError, PermissionError) as e:
        sys.stdout.buffer.write(f"\r\n{e}\r\n".encode())
        sys.stdout.buffer.flush()
        os.waitpid(pid, os.WNOHANG)
        return 1, False
    finally:
        if old_attrs is not None:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attrs)
            except termios.error:
                pass
        _restore_terminal()

    # 连接失败但未能认证 — 刷出未显示的 banner（如 "Connection refused" 等）
    if not authenticated and not host_key_retry_needed and banner:
        os.write(sys.stdout.fileno(), banner)
        sys.stdout.flush()

    _, status = os.waitpid(pid, 0)
    return status, host_key_retry_needed


def _needs_user_input(banner: bytes) -> bool:
    """检测 banner 中是否包含需要用户输入的交互提示。"""
    lower = banner.lower()
    return (
        b"(yes/no" in lower
        or b"(yes/no/[fingerprint])" in lower
        or b"are you sure" in lower
    )


def _restore_terminal() -> None:
    """确保终端恢复正常模式（兜底）。"""
    try:
        attrs = termios.tcgetattr(sys.stdin)
        attrs[3] |= termios.ECHO | termios.ICANON
        attrs[3] &= ~termios.OPOST
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, attrs)
    except Exception:
        pass
