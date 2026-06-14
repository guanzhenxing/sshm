"""会话缓存模块 — macOS Keychain 缓存主密码。

缓存的不是派生 AES 密钥，而是主密码本身：消费方（cli.get_vault_password /
tui.on_mount）都用它当主密码去解锁 vault。同用户进程能免认证读取 Keychain，
故缓存主密码与缓存派生密钥在本工具的本地威胁模型下等价（都能开 vault）；
见 docs/architecture.md 的安全说明。
"""

import json
import subprocess
import time

DEFAULT_TTL = 3600
SERVICE_NAME = "sshm-session-key"
ACCOUNT_NAME = "sshm"


def store_password(password: str, ttl: int = DEFAULT_TTL) -> None:
    """将主密码缓存到 macOS Keychain，带 TTL。"""
    payload = json.dumps({"password": password, "expires_at": time.time() + ttl})
    subprocess.run(
        [
            "security", "add-generic-password",
            "-a", ACCOUNT_NAME, "-s", SERVICE_NAME,
            "-w", payload, "-U",
        ],
        input=payload.encode("utf-8"),
        check=True,
    )


def load_password() -> str | None:
    """从 Keychain 读取缓存的主密码。过期或缺失则返回 None（并顺手清掉过期项）。"""
    result = subprocess.run(
        [
            "security", "find-generic-password",
            "-a", ACCOUNT_NAME, "-s", SERVICE_NAME,
            "-w",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout.strip())
        if data["expires_at"] > time.time():
            return data["password"]
    except (json.JSONDecodeError, KeyError):
        pass
    clear_password()
    return None


def clear_password() -> None:
    """清除 Keychain 中的缓存主密码（即 `sshm lock`）。"""
    subprocess.run(
        [
            "security", "delete-generic-password",
            "-a", ACCOUNT_NAME, "-s", SERVICE_NAME,
        ],
        capture_output=True,
    )
