"""Vault 数据管理 — ServerConfig 数据类 + Vault 文件读写。"""

import json
import os
import fcntl
from dataclasses import dataclass, asdict
from typing import Literal, Optional

from sshm.crypto import encrypt, decrypt


@dataclass
class ServerConfig:
    """SSH 服务器配置。"""

    name: str
    host: str
    user: str
    auth_type: Literal["key", "password"]
    port: int = 22
    key_path: Optional[str] = None
    password: Optional[str] = None
    group: str = ""
    notes: str = ""

    def __post_init__(self):
        errors = []
        if not self.name or not self.name.strip():
            errors.append("name is required")
        if not self.host or not self.host.strip():
            errors.append("host is required")
        if not (1 <= self.port <= 65535):
            errors.append(f"invalid port: {self.port}")
        if self.auth_type not in ("key", "password"):
            errors.append(f"invalid auth_type: {self.auth_type}")
        if self.auth_type == "key" and not self.key_path:
            errors.append("key_path required for key auth")
        if self.auth_type == "password" and not self.password:
            errors.append("password required for password auth")
        if errors:
            raise ValueError(f"Server '{self.name}': " + "; ".join(errors))

    @classmethod
    def from_dict(cls, raw: dict) -> "ServerConfig":
        d = raw.copy()
        if d.get("key_path"):
            d["key_path"] = os.path.expanduser(d["key_path"])
        return cls(**d)

    def to_dict(self) -> dict:
        return asdict(self)


VAULT_VERSION = 1

DEFAULT_VAULT_PATH = os.path.expanduser("~/.sshm/vault.enc")


class Vault:
    """加密 vault 文件管理。"""

    def __init__(self, path: str = DEFAULT_VAULT_PATH):
        self.path = os.path.expanduser(path)

    def path_exists(self) -> bool:
        """vault 文件是否存在。"""
        return os.path.exists(self.path)

    def init(self, password: str, force: bool = False) -> None:
        """初始化 vault。"""
        if os.path.exists(self.path) and not force:
            raise FileExistsError(f"Vault already exists: {self.path}")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        empty_data = json.dumps({"version": VAULT_VERSION, "servers": []}).encode("utf-8")
        encrypted = encrypt(empty_data, password)
        with open(self.path, "wb") as f:
            f.write(encrypted)

    def load(self, password: str) -> dict:
        """加载并解密 vault。"""
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"Vault not found: {self.path}")
        with open(self.path, "rb") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = f.read()
            fcntl.flock(f, fcntl.LOCK_UN)
        plaintext = decrypt(data, password)
        result = json.loads(plaintext.decode("utf-8"))
        if result.get("version", 0) > VAULT_VERSION:
            raise ValueError("Vault version is newer than this tool supports. Please update sshm.")
        return result

    def save(self, data: dict, password: str) -> None:
        """加密并写入 vault（排他锁）。"""
        plaintext = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        encrypted = encrypt(plaintext, password)
        with open(self.path, "r+b") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            f.truncate()
            f.write(encrypted)
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f, fcntl.LOCK_UN)

    def list_servers(self, password: str) -> list[ServerConfig]:
        data = self.load(password)
        return [ServerConfig.from_dict(s) for s in data.get("servers", [])]

    def add_server(self, server: ServerConfig, password: str) -> None:
        data = self.load(password)
        data["servers"].append(server.to_dict())
        self.save(data, password)

    def _find_server_index(self, data: dict, name_or_index: str) -> int:
        servers = data.get("servers", [])
        if name_or_index.isdigit():
            idx = int(name_or_index) - 1
            if 0 <= idx < len(servers):
                return idx
        for i, s in enumerate(servers):
            if s["name"] == name_or_index:
                return i
        raise ValueError(f"Server not found: {name_or_index}")

    def remove_server(self, name_or_index: str, password: str) -> None:
        data = self.load(password)
        idx = self._find_server_index(data, name_or_index)
        data["servers"].pop(idx)
        self.save(data, password)

    def edit_server(self, name_or_index: str, updates: dict, password: str) -> None:
        data = self.load(password)
        idx = self._find_server_index(data, name_or_index)
        data["servers"][idx].update(updates)
        ServerConfig.from_dict(data["servers"][idx])
        self.save(data, password)
