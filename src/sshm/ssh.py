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


def ssh_connect(server: ServerConfig) -> int:
    """连接到 SSH 服务器，返回进程退出码。"""
    if server.auth_type == "key":
        return _ssh_with_key(server)
    else:
        return _ssh_with_password(server)


def _ssh_with_key(server: ServerConfig) -> int:
    """密钥认证 SSH 连接。"""
    cmd = [
        "ssh",
        "-o", f"Port={server.port}",
        "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
    ]
    if server.key_path:
        cmd.extend(["-i", server.key_path])
    cmd.append(f"{server.user}@{server.host}")

    print(f"Connecting to {server.user}@{server.host}:{server.port} ...")
    sys.stdout.flush()

    # 用 subprocess 而非 os.execvp，确保终端状态可控
    result = subprocess.run(cmd)
    return result.returncode


def _ssh_with_password(server: ServerConfig) -> int:
    """密码认证 SSH 连接，使用 pty。"""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("ssh", [
            "ssh",
            "-o", f"Port={server.port}",
            "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
            f"{server.user}@{server.host}",
        ])
        os._exit(1)

    password = server.password or ""
    authenticated = False
    banner = b""

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

    except (TimeoutError, PermissionError) as e:
        # 确保错误信息可见
        sys.stdout.buffer.write(f"\r\n{e}\r\n".encode())
        sys.stdout.buffer.flush()
        os.waitpid(pid, os.WNOHANG)
        return 1
    finally:
        if old_attrs is not None:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attrs)
            except termios.error:
                pass
        # 兜底：确保终端恢复正常
        _restore_terminal()

    _, status = os.waitpid(pid, 0)
    return status


def _restore_terminal() -> None:
    """确保终端恢复正常模式（兜底）。"""
    try:
        attrs = termios.tcgetattr(sys.stdin)
        attrs[3] |= termios.ECHO | termios.ICANON
        attrs[3] &= ~termios.OPOST
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, attrs)
    except Exception:
        pass
