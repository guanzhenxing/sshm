"""SSH 连接模块 — 使用 pty 调用系统 ssh。"""

import os
import pty
import select
import signal
import sys
import termios
import time
import tty

from sshm.vault import ServerConfig


def ssh_connect(server: ServerConfig) -> int:
    """连接到 SSH 服务器，返回进程退出码。"""
    if server.auth_type == "key":
        return _ssh_with_key(server)
    else:
        return _ssh_with_password(server)


def _ssh_with_key(server: ServerConfig) -> int:
    """密钥认证 SSH 连接。"""
    cmd = ["ssh", "-o", f"Port={server.port}"]
    if server.key_path:
        cmd.extend(["-i", server.key_path])
    cmd.append(f"{server.user}@{server.host}")
    os.execvp("ssh", cmd)
    return 1  # 不会到达


def _ssh_with_password(server: ServerConfig) -> int:
    """密码认证 SSH 连接，使用 pty。"""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("ssh", [
            "ssh", "-o", f"Port={server.port}",
            f"{server.user}@{server.host}",
        ])
        os._exit(1)

    password = server.password or ""
    authenticated = False
    banner = b""

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
            sources = [fd]
            if authenticated:
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

            if sys.stdin in rlist and authenticated:
                try:
                    key = os.read(sys.stdin.fileno(), 4096)
                except OSError:
                    break
                if not key:
                    break
                os.write(fd, key)

    except (TimeoutError, PermissionError):
        os.waitpid(pid, os.WNOHANG)
        return 1
    finally:
        if old_attrs is not None:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attrs)
            except termios.error:
                pass

    _, status = os.waitpid(pid, 0)
    return status
