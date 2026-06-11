"""会话缓存模块 — macOS Keychain 存储 AES 密钥。"""

import json
import subprocess
import time

DEFAULT_TTL = 3600
SERVICE_NAME = "sshm-session-key"
ACCOUNT_NAME = "sshm"


def store_key(key_hex: str, ttl: int = DEFAULT_TTL) -> None:
    """将 AES 密钥（hex）缓存到 macOS Keychain。"""
    payload = json.dumps({"key": key_hex, "expires_at": time.time() + ttl})
    subprocess.run(
        [
            "security", "add-generic-password",
            "-a", ACCOUNT_NAME, "-s", SERVICE_NAME,
            "-w", payload, "-U",
        ],
        input=payload.encode("utf-8"),
        check=True,
    )


def load_key() -> str | None:
    """从 Keychain 读取缓存的 AES 密钥。过期则返回 None。"""
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
            return data["key"]
    except (json.JSONDecodeError, KeyError):
        pass
    clear_key()
    return None


def clear_key() -> None:
    """清除 Keychain 中的缓存密钥。"""
    subprocess.run(
        [
            "security", "delete-generic-password",
            "-a", ACCOUNT_NAME, "-s", SERVICE_NAME,
        ],
        capture_output=True,
    )
