"""SSH 连接模块 — 使用 pty 调用系统 ssh。

密钥与密码认证统一走 pty 中继（`pty_connect`）：终端实时可见、可交互
（包括加密私钥的 passphrase 提示）。此前密钥认证用 subprocess 捕获
stdout/stderr，会话输出全程被吞、直到退出才（在成功时被直接丢弃）——
用户只能盲打。
"""

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

# 实时中继时 host key 检测的滚动窗口：须容纳 "REMOTE HOST IDENTIFICATION
# HAS CHANGED" 警告块及其后的 "Host key verification failed."（约 700B）。
_DETECT_WINDOW = 1024


def ssh_connect(server: ServerConfig) -> int:
    """连接到 SSH 服务器，返回进程退出码。"""
    return pty_connect(
        _build_ssh_key_cmd(server),
        password=server.password if server.auth_type == "password" else None,
        timeout=30,
        host=server.host,
        desc=f"{server.user}@{server.host}",
    )


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


def _needs_user_input(banner: bytes) -> bool:
    """检测 banner 中是否包含需要用户输入的交互提示。"""
    lower = banner.lower()
    return (
        b"(yes/no" in lower
        or b"(yes/no/[fingerprint])" in lower
        or b"are you sure" in lower
    )


def pty_connect(
    cmd: list[str],
    *,
    password: str | None = None,
    timeout: int = 30,
    host: str = "",
    desc: str = "",
) -> int:
    """在 pty 中运行 cmd 并中继终端 I/O，host key 变更时自动清 key 重试一次。

    password=None（密钥认证等无密码提示场景）：输出全程实时中继、输入随时
    可写，体验与直接运行命令一致。password 非空（密码认证）：提示出现前
    缓冲输出，见到 password: 后注入密码并校验未被拒。

    返回进程退出码。
    """
    for _attempt in range(_MAX_HOST_KEY_RETRIES + 1):
        if _attempt > 0:
            print(f"Retrying connection to {host} ...")
        rc, retry = _pty_connect_once(
            cmd, password=password, timeout=timeout, host=host, desc=desc,
        )
        if rc == 0:
            return 0
        if not retry:
            return rc
    return 1


def _pty_connect_once(
    cmd: list[str],
    *,
    password: str | None,
    timeout: int,
    host: str,
    desc: str,
) -> tuple[int, bool]:
    """单次 pty 连接。Returns (exit_code, should_retry_for_host_key)."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp(cmd[0], cmd)
        os._exit(1)

    authenticated = password is None
    banner = b""
    tail = b""  # 实时中继时的滚动窗口：进程退出后据此判断 host key 变更
    host_key_retry_needed = False
    stdin_open = True

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
            # 密码注入完成（或无需密码）前不监听 stdin，避免误按键被发给 ssh；
            # 但出现 yes/no 等交互提示时放行，让用户能确认。
            sources = [fd]
            if stdin_open and (authenticated or _needs_user_input(banner)):
                sources.append(sys.stdin)

            rlist, _, _ = select.select(sources, [], [], timeout)

            if not rlist:
                if not authenticated:
                    if banner:
                        os.write(sys.stdout.fileno(), banner)
                    raise TimeoutError(
                        f"No password prompt from {desc} within {timeout}s. "
                        "请确认服务器支持密码认证，或手动运行 ssh 排查。"
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
                        _handle_host_key_change(host)
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
                                    f"Authentication failed for {desc}"
                                )

                        authenticated = True
                        os.write(sys.stdout.fileno(), banner)
                else:
                    os.write(sys.stdout.fileno(), data)
                    tail = (tail + data)[-_DETECT_WINDOW:]

            if sys.stdin in rlist:
                try:
                    key = os.read(sys.stdin.fileno(), 4096)
                except OSError:
                    stdin_open = False
                else:
                    if key:
                        os.write(fd, key)
                    else:
                        # stdin EOF：只是不再监听输入，会话必须继续——macOS 上
                        # master 未读空前子进程无法完成退出，若在此 break 去
                        # waitpid 会永久阻塞（子进程卡在 exiting 状态）。
                        stdin_open = False

    except (TimeoutError, PermissionError) as e:
        sys.stdout.buffer.write(f"\r\n{e}\r\n".encode())
        sys.stdout.buffer.flush()
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)
        return 1, False
    finally:
        if old_attrs is not None:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attrs)
            except termios.error:
                pass

    _, status = os.waitpid(pid, 0)
    try:
        os.close(fd)  # 及时释放 pty master
    except OSError:
        pass
    exit_code = os.waitstatus_to_exitcode(status)

    # 密钥认证时 host key 变更由 ssh 自行报错退出（255），从滚动窗口判断是否重试
    if exit_code != 0 and authenticated and _is_host_key_changed(tail):
        _handle_host_key_change(host)
        host_key_retry_needed = True

    # 连接失败但未能认证 — 刷出未显示的 banner（如 "Connection refused" 等）
    if not authenticated and not host_key_retry_needed and banner:
        os.write(sys.stdout.fileno(), banner)
        sys.stdout.flush()

    return exit_code, host_key_retry_needed
