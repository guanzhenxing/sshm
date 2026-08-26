"""文件传输模块 — SCP 上传/下载。

密钥与密码认证统一复用 ssh.pty_connect 的 pty 中继：进度实时可见、
host key 变更自动清 key 重试。此前密钥认证用 subprocess 捕获输出，
scp 的加密私钥 passphrase 提示不可见（挂死）、成功时进度也看不到。
"""

from sshm.ssh import CONNECT_TIMEOUT, pty_connect
from sshm.vault import ServerConfig

# scp 共用的 SSH 选项
_SCP_SSH_OPTS = [
    "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
    "-o", "StrictHostKeyChecking=accept-new",
]


def scp_upload(server: ServerConfig, local_path: str, remote_path: str) -> int:
    """通过 SCP 上传文件，返回进程退出码。"""
    cmd = _build_scp_cmd(server, local_path, f"{server.user}@{server.host}:{remote_path}")
    return _run_scp(server, cmd)


def scp_download(server: ServerConfig, remote_path: str, local_path: str) -> int:
    """通过 SCP 下载文件，返回进程退出码。"""
    cmd = _build_scp_cmd(server, f"{server.user}@{server.host}:{remote_path}", local_path)
    return _run_scp(server, cmd)


def _build_scp_cmd(server: ServerConfig, source: str, destination: str) -> list[str]:
    """构建 scp 命令行。注意 scp 使用大写 -P 指定端口。"""
    cmd = ["scp", "-P", str(server.port)]
    cmd.extend(_SCP_SSH_OPTS)
    if server.auth_type == "key" and server.key_path:
        cmd.extend(["-i", server.key_path])
    cmd.extend([source, destination])
    return cmd


def _run_scp(server: ServerConfig, cmd: list[str]) -> int:
    """执行 scp 命令（pty 中继；host key 变更自动重试）。"""
    return pty_connect(
        cmd,
        password=server.password if server.auth_type == "password" else None,
        timeout=60,
        host=server.host,
        desc=f"scp {server.user}@{server.host}",
    )
