"""Vault 数据管理 — ServerConfig 数据类 + Vault 文件读写。"""

import fcntl
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Literal

from sshm.crypto import decrypt, encrypt


@dataclass
class ServerConfig:
    """SSH 服务器配置。"""

    name: str
    host: str
    user: str
    auth_type: Literal["key", "password"]
    port: int = 22
    key_path: str | None = None
    password: str | None = None
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


@dataclass
class MergeReport:
    """merge_servers 的合并结果摘要。"""
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    overwritten: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    total_in: int = 0

    def summary(self) -> str:
        return (
            f"新增 {len(self.added)}，跳过 {len(self.skipped)}，"
            f"覆盖 {len(self.overwritten)}，重命名 {len(self.renamed)}"
            f"（共 {self.total_in} 条）"
        )


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

    def merge_servers(
        self,
        incoming: list[ServerConfig],
        strategy: str,
        password: str,
        *,
        dry_run: bool = False,
    ) -> "MergeReport":
        """按策略合并 incoming 到当前 vault，单次 save（原子）。

        strategy ∈ {"skip","overwrite","rename"}；dry_run 不落盘。
        唯一业务键 = name。
        """
        if strategy not in ("skip", "overwrite", "rename"):
            raise ValueError(f"未知合并策略：{strategy}")
        data = self.load(password)
        final: list[dict] = list(data.get("servers", []))
        by_name: dict[str, dict] = {s["name"]: s for s in final}
        report = MergeReport(total_in=len(incoming))

        for inc in incoming:
            inc_d = inc.to_dict()
            name = inc_d["name"]
            if name not in by_name:
                final.append(inc_d)
                by_name[name] = inc_d
                report.added.append(name)
                continue

            if strategy == "skip":
                report.skipped.append(name)
            elif strategy == "overwrite":
                for i, s in enumerate(final):
                    if s["name"] == name:
                        final[i] = inc_d
                        break
                by_name[name] = inc_d
                report.overwritten.append(name)
            elif strategy == "rename":
                new_name = self._next_available_name(name, by_name)
                inc_d["name"] = new_name
                final.append(inc_d)
                by_name[new_name] = inc_d
                report.renamed.append((name, new_name))

        if not dry_run:
            data["servers"] = final
            self.save(data, password)
        return report

    @staticmethod
    def _next_available_name(name: str, by_name: dict[str, dict]) -> str:
        """碰撞时生成 name-2 / name-3 … 直到空出（含已重命名的占用）。"""
        i = 2
        while f"{name}-{i}" in by_name:
            i += 1
        return f"{name}-{i}"
