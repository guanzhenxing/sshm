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
