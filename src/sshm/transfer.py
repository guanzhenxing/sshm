"""文件传输模块 — SCP 上传/下载。"""

import os
import pty
import select
import subprocess
import sys
import termios
import time
import tty

from sshm.vault import ServerConfig


def scp_upload(server: ServerConfig, local_path: str, remote_path: str) -> int:
    """通过 SCP 上传文件，返回进程退出码。"""
    cmd = _build_scp_cmd(server, local_path, f"{server.user}@{server.host}:{remote_path}")
    return _run_scp_with_auth(server, cmd)


def scp_download(server: ServerConfig, remote_path: str, local_path: str) -> int:
    """通过 SCP 下载文件，返回进程退出码。"""
    cmd = _build_scp_cmd(server, f"{server.user}@{server.host}:{remote_path}", local_path)
    return _run_scp_with_auth(server, cmd)


def _build_scp_cmd(server: ServerConfig, source: str, destination: str) -> list[str]:
    """构建 scp 命令行。注意 scp 使用大写 -P 指定端口。"""
    cmd = ["scp"]
    cmd.extend(["-P", str(server.port)])
    if server.auth_type == "key" and server.key_path:
        cmd.extend(["-i", server.key_path])
    cmd.extend([source, destination])
    return cmd


def _run_scp_with_auth(server: ServerConfig, cmd: list[str]) -> int:
    """执行 scp 命令。"""
    if server.auth_type == "key":
        result = subprocess.run(cmd)
        return result.returncode
    else:
        return _scp_with_password(server, cmd)


def _scp_with_password(server: ServerConfig, cmd: list[str]) -> int:
    """密码认证的 SCP 传输。"""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("scp", cmd)
        os._exit(1)

    password = server.password or ""
    authenticated = False
    output = b""

    try:
        old_attrs = termios.tcgetattr(sys.stdin)
    except termios.error:
        old_attrs = None

    try:
        if old_attrs is not None:
            tty.setraw(sys.stdin.fileno())

        while True:
            sources = [fd]
            if authenticated:
                sources.append(sys.stdin)

            rlist, _, _ = select.select(sources, [], [], 60)

            if not rlist:
                if not authenticated:
                    raise TimeoutError(f"SCP timed out for {server.user}@{server.host}")
                continue

            if fd in rlist:
                try:
                    data = os.read(fd, 4096)
                except OSError:
                    break
                if not data:
                    break

                if not authenticated:
                    output += data
                    if b"password:" in output.lower():
                        os.write(fd, password.encode("utf-8") + b"\n")
                        time.sleep(0.3)
                        r2, _, _ = select.select([fd], [], [], 0.5)
                        if r2:
                            check = os.read(fd, 1024)
                            output += check
                            if b"denied" in check.lower() or b"failed" in check.lower():
                                os.write(sys.stdout.fileno(), output)
                                raise PermissionError(
                                    f"Authentication failed for {server.user}@{server.host}"
                                )
                        authenticated = True
                        os.write(sys.stdout.fileno(), output)
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
