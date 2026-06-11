# sshm 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 实现一个 macOS 原生的 SSH 服务器管理 CLI，支持加密凭据存储和交互式 TUI。

**架构：** 自底向上 7 层实现。crypto → vault → session → ssh → transfer → cli → tui。每层独立可测，核心逻辑使用 TDD。

**技术栈：** Python 3.10+、Textual（TUI）、cryptography（加密）、pytest（测试）

**设计文档：** `docs/superpowers/specs/2026-06-11-sshm-implementation-design.md`

---

## 文件结构

| 文件 | 职责 | 创建/修改 |
|------|------|-----------|
| `pyproject.toml` | 包配置和依赖声明 | 创建 |
| `requirements.txt` | 开发依赖（从 pyproject.toml 生成） | 创建 |
| `src/sshm/__init__.py` | 包标记，版本号 | 创建 |
| `src/sshm/__main__.py` | 入口：`python -m sshm` | 创建 |
| `src/sshm/crypto.py` | AES-256-GCM 加解密 + PBKDF2 密钥派生 | 创建 |
| `src/sshm/vault.py` | ServerConfig 数据类 + Vault 文件读写 + 文件锁 | 创建 |
| `src/sshm/session.py` | macOS Keychain 会话缓存 | 创建 |
| `src/sshm/ssh.py` | pty 方式 SSH 连接 | 创建 |
| `src/sshm/transfer.py` | SCP 文件传输 | 创建 |
| `src/sshm/cli.py` | argparse 命令解析和路由 | 创建 |
| `src/sshm/tui.py` | Textual 交互式 TUI | 创建 |
| `tests/__init__.py` | 测试包标记 | 创建 |
| `tests/test_crypto.py` | crypto 模块单元测试 | 创建 |
| `tests/test_vault.py` | vault 模块单元测试 | 创建 |
| `tests/test_session.py` | session 模块单元测试 | 创建 |
| `tests/test_cli.py` | cli 模块单元测试 | 创建 |

---

## Task 1: 项目初始化

**文件：**
- 创建：`pyproject.toml`
- 创建：`requirements.txt`
- 创建：`src/sshm/__init__.py`
- 创建：`src/sshm/__main__.py`
- 创建：`tests/__init__.py`

- [ ] **Step 1: 初始化 git 仓库**

```bash
cd /Users/jesen/WorkSpace/MyProjects/sshm
git init
```

- [ ] **Step 2: 创建 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "sshm"
version = "0.1.0"
description = "SSH Server Manager for macOS — encrypted, interactive CLI"
requires-python = ">=3.10"
license = "MIT"

dependencies = [
    "textual>=3.0",
    "cryptography>=42.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[project.scripts]
sshm = "sshm.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: 创建 requirements.txt**

```
textual>=3.0
cryptography>=42.0
pytest>=8.0
```

- [ ] **Step 4: 创建包目录结构**

```bash
mkdir -p src/sshm tests
```

- [ ] **Step 5: 创建 src/sshm/__init__.py**

```python
"""sshm — SSH Server Manager for macOS."""

__version__ = "0.1.0"
```

- [ ] **Step 6: 创建 src/sshm/__main__.py**

```python
"""入口：python -m sshm"""

from sshm.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 7: 创建 tests/__init__.py**

空文件。

```bash
touch tests/__init__.py
```

- [ ] **Step 8: 安装依赖并验证**

```bash
pip3 install -e ".[dev]"
python3 -m sshm --help
```

预期：报错退出（cli.py 还不存在），但包结构应可识别。

- [ ] **Step 9: 创建 .gitignore**

```
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.eggs/
*.egg
.pytest_cache/
.mypy_cache/
.venv/
venv/
```

- [ ] **Step 10: 提交**

```bash
git add -A
git commit -m "chore: 初始化项目结构 (pyproject.toml, src layout)"
```

---

## Task 2: crypto.py — 加解密模块

**文件：**
- 创建：`src/sshm/crypto.py`
- 创建：`tests/test_crypto.py`

- [ ] **Step 1: 编写测试 — derive_key**

创建 `tests/test_crypto.py`：

```python
"""crypto 模块单元测试。"""

import os
from sshm.crypto import derive_key, encrypt, decrypt, SALT_SIZE, IV_SIZE, KDF_ITERATIONS


class TestDeriveKey:
    def test_returns_32_bytes(self):
        salt = os.urandom(SALT_SIZE)
        key = derive_key("test-password", salt)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_same_input_same_output(self):
        salt = os.urandom(SALT_SIZE)
        key1 = derive_key("test-password", salt)
        key2 = derive_key("test-password", salt)
        assert key1 == key2

    def test_different_password_different_key(self):
        salt = os.urandom(SALT_SIZE)
        key1 = derive_key("password-a", salt)
        key2 = derive_key("password-b", salt)
        assert key1 != key2

    def test_different_salt_different_key(self):
        key1 = derive_key("test-password", os.urandom(SALT_SIZE))
        key2 = derive_key("test-password", os.urandom(SALT_SIZE))
        assert key1 != key2
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_crypto.py -v
```

预期：FAIL — `ModuleNotFoundError: No module named 'sshm.crypto'`

- [ ] **Step 3: 实现 derive_key**

创建 `src/sshm/crypto.py`：

```python
"""加密/解密模块 — AES-256-GCM + PBKDF2-SHA256。"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

SALT_SIZE = 16
IV_SIZE = 12
KDF_ITERATIONS = 600_000


def derive_key(password: str, salt: bytes) -> bytes:
    """使用 PBKDF2-SHA256 从密码派生 256 位 AES 密钥。"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_crypto.py::TestDeriveKey -v
```

预期：4 个测试全部 PASS

- [ ] **Step 5: 编写测试 — encrypt / decrypt**

追加到 `tests/test_crypto.py`：

```python

class TestEncryptDecrypt:
    def test_roundtrip(self):
        """加密后解密应得到原始数据。"""
        plaintext = b'{"version": 1, "servers": []}'
        password = "my-master-password"
        encrypted = encrypt(plaintext, password)
        decrypted = decrypt(encrypted, password)
        assert decrypted == plaintext

    def test_encrypted_not_plaintext(self):
        """密文不应等于明文。"""
        plaintext = b"hello world"
        encrypted = encrypt(plaintext, "password")
        assert encrypted != plaintext

    def test_different_password_decrypt_fails(self):
        """用错误密码解密应抛出异常。"""
        import pytest
        encrypted = encrypt(b"secret data", "correct-password")
        with pytest.raises(Exception):
            decrypt(encrypted, "wrong-password")

    def test_ciphertext_starts_with_salt_and_iv(self):
        """密文前缀应为 salt (16B) + IV (12B)。"""
        encrypted = encrypt(b"test", "password")
        assert len(encrypted) > SALT_SIZE + IV_SIZE
        # salt 和 IV 部分每次都不同（随机），但长度固定

    def test_different_calls_different_ciphertext(self):
        """相同输入每次加密产生不同密文（因 salt 和 IV 随机）。"""
        plaintext = b"same data"
        password = "same-password"
        enc1 = encrypt(plaintext, password)
        enc2 = encrypt(plaintext, password)
        assert enc1 != enc2
        # 但两者都能正确解密
        assert decrypt(enc1, password) == plaintext
        assert decrypt(enc2, password) == plaintext

    def test_tampered_ciphertext_decrypt_fails(self):
        """篡改密文后解密应失败（GCM 完整性校验）。"""
        import pytest
        encrypted = encrypt(b"important data", "password")
        tampered = bytearray(encrypted)
        tampered[-1] ^= 0xFF  # 翻转最后一个字节
        with pytest.raises(Exception):
            decrypt(bytes(tampered), "password")

    def test_empty_plaintext(self):
        """空数据加解密。"""
        encrypted = encrypt(b"", "password")
        assert decrypt(encrypted, "password") == b""
```

- [ ] **Step 6: 运行测试确认失败**

```bash
pytest tests/test_crypto.py::TestEncryptDecrypt -v
```

预期：FAIL — `NameError: name 'encrypt' is not defined`（尚未实现）

- [ ] **Step 7: 实现 encrypt 和 decrypt**

追加到 `src/sshm/crypto.py`：

```python

def encrypt(plaintext: bytes, password: str) -> bytes:
    """加密数据，返回 salt + IV + ciphertext（含 auth tag）。"""
    salt = os.urandom(SALT_SIZE)
    key = derive_key(password, salt)
    iv = os.urandom(IV_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext, None)
    return salt + iv + ciphertext


def decrypt(data: bytes, password: str) -> bytes:
    """解密数据（salt + IV + ciphertext），返回明文。"""
    salt = data[:SALT_SIZE]
    iv = data[SALT_SIZE : SALT_SIZE + IV_SIZE]
    ciphertext = data[SALT_SIZE + IV_SIZE :]
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext, None)
```

- [ ] **Step 8: 运行全部 crypto 测试**

```bash
pytest tests/test_crypto.py -v
```

预期：11 个测试全部 PASS

- [ ] **Step 9: 提交**

```bash
git add src/sshm/crypto.py tests/test_crypto.py
git commit -m "feat: 实现 crypto 模块 (AES-256-GCM + PBKDF2)"
```

---

## Task 3: vault.py — ServerConfig 数据类

**文件：**
- 创建：`src/sshm/vault.py`（ServerConfig 部分）
- 创建：`tests/test_vault.py`（ServerConfig 测试部分）

- [ ] **Step 1: 编写测试 — ServerConfig 验证**

创建 `tests/test_vault.py`：

```python
"""vault 模块单元测试。"""

import pytest
from sshm.vault import ServerConfig


class TestServerConfig:
    def test_valid_key_auth(self):
        """密钥认证的服务器配置应通过验证。"""
        server = ServerConfig(
            name="prod-web",
            host="192.168.1.100",
            user="admin",
            auth_type="key",
            key_path="/home/user/.ssh/id_rsa",
        )
        assert server.name == "prod-web"
        assert server.port == 22  # 默认值

    def test_valid_password_auth(self):
        """密码认证的服务器配置应通过验证。"""
        server = ServerConfig(
            name="staging",
            host="10.0.0.50",
            user="deploy",
            auth_type="password",
            password="secret123",
            port=2222,
            group="staging",
        )
        assert server.auth_type == "password"
        assert server.port == 2222

    def test_missing_name_raises(self):
        """缺少 name 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="name is required"):
            ServerConfig(name="", host="1.2.3.4", user="root", auth_type="key", key_path="/key")

    def test_missing_host_raises(self):
        """缺少 host 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="host is required"):
            ServerConfig(name="test", host="", user="root", auth_type="key", key_path="/key")

    def test_invalid_port_raises(self):
        """无效端口应抛出 ValueError。"""
        with pytest.raises(ValueError, match="invalid port"):
            ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="key", key_path="/key", port=99999)

    def test_key_auth_without_key_path_raises(self):
        """密钥认证但缺少 key_path 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="key_path required"):
            ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="key")

    def test_password_auth_without_password_raises(self):
        """密码认证但缺少 password 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="password required"):
            ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="password")

    def test_invalid_auth_type_raises(self):
        """无效的 auth_type 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="invalid auth_type"):
            ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="token")

    def test_tilde_expansion(self):
        """from_dict 应将 ~ 展开为绝对路径。"""
        server = ServerConfig.from_dict({
            "name": "test",
            "host": "1.2.3.4",
            "user": "root",
            "auth_type": "key",
            "key_path": "~/.ssh/id_rsa",
        })
        assert "~" not in server.key_path
        assert server.key_path.startswith("/")

    def test_from_dict_does_not_mutate_input(self):
        """from_dict 不应修改传入的字典。"""
        raw = {"name": "test", "host": "1.2.3.4", "user": "root", "auth_type": "key", "key_path": "~/.ssh/id_rsa"}
        raw_copy = raw.copy()
        ServerConfig.from_dict(raw)
        assert raw == raw_copy

    def test_to_dict(self):
        """to_dict 应返回可序列化的字典。"""
        server = ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="key", key_path="/key")
        d = server.to_dict()
        assert d["name"] == "test"
        assert d["port"] == 22
        assert isinstance(d, dict)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_vault.py -v
```

预期：FAIL — `ModuleNotFoundError: No module named 'sshm.vault'`

- [ ] **Step 3: 实现 ServerConfig**

创建 `src/sshm/vault.py`：

```python
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
        """从字典创建 ServerConfig，自动展开 ~ 路径。"""
        d = raw.copy()
        if d.get("key_path"):
            d["key_path"] = os.path.expanduser(d["key_path"])
        return cls(**d)

    def to_dict(self) -> dict:
        """转换为可序列化的字典。"""
        return asdict(self)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_vault.py::TestServerConfig -v
```

预期：11 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/sshm/vault.py tests/test_vault.py
git commit -m "feat: 实现 ServerConfig 数据类 (验证 + to_dict/from_dict)"
```

---

## Task 4: vault.py — Vault 类（文件读写 + 文件锁）

**文件：**
- 修改：`src/sshm/vault.py`
- 修改：`tests/test_vault.py`

- [ ] **Step 1: 编写测试 — Vault 类**

追加到 `tests/test_vault.py`：

```python
import json
import os
import tempfile
from sshm.vault import Vault


class TestVault:
    def setup_method(self):
        """每个测试用临时目录。"""
        self.tmpdir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.tmpdir, "vault.enc")
        self.vault = Vault(self.vault_path)
        self.password = "test-master-password"

    def test_init_creates_vault_file(self):
        """init 应创建 vault 文件。"""
        self.vault.init(self.password)
        assert os.path.exists(self.vault_path)

    def test_init_refuses_if_exists(self):
        """vault 已存在时 init 应拒绝。"""
        self.vault.init(self.password)
        with pytest.raises(FileExistsError):
            self.vault.init(self.password)

    def test_init_force_overwrites(self):
        """init --force 应覆盖已有 vault。"""
        self.vault.init(self.password)
        self.vault.init("new-password", force=True)
        # 用新密码能打开
        data = self.vault.load("new-password")
        assert data["servers"] == []

    def test_load_returns_dict(self):
        """load 应返回含 version 和 servers 的字典。"""
        self.vault.init(self.password)
        data = self.vault.load(self.password)
        assert data["version"] == 1
        assert data["servers"] == []

    def test_wrong_password_load_fails(self):
        """错误密码 load 应失败。"""
        self.vault.init(self.password)
        with pytest.raises(Exception):
            self.vault.load("wrong-password")

    def test_add_and_list_servers(self):
        """添加服务器后应能列出。"""
        self.vault.init(self.password)
        server = ServerConfig(name="test", host="1.2.3.4", user="root", auth_type="password", password="pass")
        self.vault.add_server(server, self.password)
        servers = self.vault.list_servers(self.password)
        assert len(servers) == 1
        assert servers[0].name == "test"

    def test_remove_server_by_name(self):
        """按名称删除服务器。"""
        self.vault.init(self.password)
        s = ServerConfig(name="to-delete", host="1.2.3.4", user="root", auth_type="password", password="pass")
        self.vault.add_server(s, self.password)
        self.vault.remove_server("to-delete", self.password)
        assert len(self.vault.list_servers(self.password)) == 0

    def test_remove_server_by_index(self):
        """按序号删除服务器（1-based）。"""
        self.vault.init(self.password)
        s = ServerConfig(name="first", host="1.2.3.4", user="root", auth_type="password", password="pass")
        self.vault.add_server(s, self.password)
        self.vault.remove_server("1", self.password)
        assert len(self.vault.list_servers(self.password)) == 0

    def test_remove_nonexistent_raises(self):
        """删除不存在的服务器应报错。"""
        self.vault.init(self.password)
        with pytest.raises(ValueError):
            self.vault.remove_server("nonexistent", self.password)

    def test_edit_server(self):
        """编辑服务器字段。"""
        self.vault.init(self.password)
        s = ServerConfig(name="edit-me", host="1.2.3.4", user="root", auth_type="password", password="pass")
        self.vault.add_server(s, self.password)
        self.vault.edit_server("edit-me", {"host": "5.6.7.8", "port": 2222}, self.password)
        servers = self.vault.list_servers(self.password)
        assert servers[0].host == "5.6.7.8"
        assert servers[0].port == 2222

    def test_load_nonexistent_raises(self):
        """加载不存在的 vault 应报错。"""
        with pytest.raises(FileNotFoundError):
            self.vault.load(self.password)

    def test_vault_file_is_not_plaintext(self):
        """vault 文件不应包含可读的明文 JSON。"""
        self.vault.init(self.password)
        s = ServerConfig(name="secret-server", host="10.0.0.1", user="admin", auth_type="password", password="hunter2")
        self.vault.add_server(s, self.password)
        with open(self.vault_path, "rb") as f:
            raw = f.read()
        assert b"secret-server" not in raw
        assert b"hunter2" not in raw
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_vault.py::TestVault -v
```

预期：FAIL — `TypeError: Vault() takes no arguments`（Vault 类尚未实现）

- [ ] **Step 3: 实现 Vault 类**

追加到 `src/sshm/vault.py`：

```python

VAULT_VERSION = 1

DEFAULT_VAULT_PATH = os.path.expanduser("~/.sshm/vault.enc")


class Vault:
    """加密 vault 文件管理。"""

    def __init__(self, path: str = DEFAULT_VAULT_PATH):
        self.path = os.path.expanduser(path)

    def init(self, password: str, force: bool = False) -> None:
        """初始化 vault。如果已存在且非 force，抛出 FileExistsError。"""
        if os.path.exists(self.path) and not force:
            raise FileExistsError(f"Vault already exists: {self.path}")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        empty_data = json.dumps({"version": VAULT_VERSION, "servers": []}).encode("utf-8")
        encrypted = encrypt(empty_data, password)
        with open(self.path, "wb") as f:
            f.write(encrypted)

    def load(self, password: str) -> dict:
        """加载并解密 vault，返回字典。"""
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
        """加密并写入 vault（使用排他文件锁）。"""
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
        """列出所有服务器配置。"""
        data = self.load(password)
        return [ServerConfig.from_dict(s) for s in data.get("servers", [])]

    def add_server(self, server: ServerConfig, password: str) -> None:
        """添加服务器到 vault。"""
        data = self.load(password)
        data["servers"].append(server.to_dict())
        self.save(data, password)

    def _find_server_index(self, data: dict, name_or_index: str) -> int:
        """按名称或序号查找服务器索引（0-based）。"""
        servers = data.get("servers", [])
        # 尝试按序号匹配（1-based）
        if name_or_index.isdigit():
            idx = int(name_or_index) - 1
            if 0 <= idx < len(servers):
                return idx
        # 按名称匹配
        for i, s in enumerate(servers):
            if s["name"] == name_or_index:
                return i
        raise ValueError(f"Server not found: {name_or_index}")

    def remove_server(self, name_or_index: str, password: str) -> None:
        """删除服务器。"""
        data = self.load(password)
        idx = self._find_server_index(data, name_or_index)
        data["servers"].pop(idx)
        self.save(data, password)

    def edit_server(self, name_or_index: str, updates: dict, password: str) -> None:
        """编辑服务器配置。updates 中的字段会覆盖现有值。"""
        data = self.load(password)
        idx = self._find_server_index(data, name_or_index)
        data["servers"][idx].update(updates)
        # 用 from_dict 验证更新后的配置
        ServerConfig.from_dict(data["servers"][idx])
        self.save(data, password)
```

- [ ] **Step 4: 运行全部 vault 测试**

```bash
pytest tests/test_vault.py -v
```

预期：22 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/sshm/vault.py tests/test_vault.py
git commit -m "feat: 实现 Vault 类 (文件读写 + 文件锁 + CRUD)"
```

---

## Task 5: session.py — macOS Keychain 会话缓存

**文件：**
- 创建：`src/sshm/session.py`
- 创建：`tests/test_session.py`

- [ ] **Step 1: 编写测试 — session 模块**

创建 `tests/test_session.py`：

```python
"""session 模块单元测试。

注意：macOS Keychain 交互通过 subprocess 调用 security 命令。
测试中 mock subprocess.run 以避免实际操作 Keychain。
"""

import json
import time
from unittest.mock import patch, MagicMock
import pytest
from sshm.session import store_key, load_key, clear_key, DEFAULT_TTL


class TestStoreKey:
    @patch("sshm.session.subprocess.run")
    def test_stores_key_with_ttl(self, mock_run):
        """store_key 应调用 security 命令存储密钥。"""
        mock_run.return_value = MagicMock(returncode=0)
        store_key("abcdef123456", ttl=3600)
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "add-generic-password" in args[0][0]
        # 验证 payload 包含 key 和 expires_at
        payload = json.loads(args[1]["input"].decode("utf-8"))
        assert payload["key"] == "abcdef123456"
        assert payload["expires_at"] > time.time()


class TestLoadKey:
    @patch("sshm.session.subprocess.run")
    def test_load_valid_key(self, mock_run):
        """未过期的缓存应返回密钥。"""
        payload = json.dumps({"key": "abcdef123456", "expires_at": time.time() + 3600})
        mock_run.return_value = MagicMock(returncode=0, stdout=payload)
        result = load_key()
        assert result == "abcdef123456"

    @patch("sshm.session.subprocess.run")
    def test_load_expired_key_returns_none(self, mock_run):
        """已过期的缓存应返回 None 并清除。"""
        payload = json.dumps({"key": "abcdef123456", "expires_at": time.time() - 100})
        mock_run.return_value = MagicMock(returncode=0, stdout=payload)
        result = load_key()
        assert result is None

    @patch("sshm.session.subprocess.run")
    def test_load_no_key_returns_none(self, mock_run):
        """Keychain 中无缓存应返回 None。"""
        mock_run.return_value = MagicMock(returncode=44)  # security 命令找不到时返回 44
        result = load_key()
        assert result is None


class TestClearKey:
    @patch("sshm.session.subprocess.run")
    def test_clear_calls_delete(self, mock_run):
        """clear_key 应调用 delete-generic-password。"""
        mock_run.return_value = MagicMock(returncode=0)
        clear_key()
        mock_run.assert_called_once()
        assert "delete-generic-password" in mock_run.call_args[0][0]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_session.py -v
```

预期：FAIL — `ModuleNotFoundError: No module named 'sshm.session'`

- [ ] **Step 3: 实现 session.py**

创建 `src/sshm/session.py`：

```python
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
```

- [ ] **Step 4: 运行全部 session 测试**

```bash
pytest tests/test_session.py -v
```

预期：5 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/sshm/session.py tests/test_session.py
git commit -m "feat: 实现 session 模块 (macOS Keychain 缓存)"
```

---

## Task 6: ssh.py — SSH 连接

**文件：**
- 创建：`src/sshm/ssh.py`

> ssh.py 使用 pty 与系统 ssh 交互，难以单元测试，通过手动验证。

- [ ] **Step 1: 实现 ssh.py**

创建 `src/sshm/ssh.py`：

```python
"""SSH 连接模块 — 使用 pty 调用系统 ssh。"""

import os
import pty
import select
import signal
import sys
import termios
import time
import tty
from typing import Optional

from sshm.vault import ServerConfig


def ssh_connect(server: ServerConfig) -> int:
    """连接到 SSH 服务器，返回进程退出码。

    密钥认证：直接调用 ssh -i。
    密码认证：使用 pty 检测密码提示并自动输入。
    """
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
    result = os.execvp("ssh", cmd)
    return result  # 不会到达这里，execvp 替换当前进程


def _ssh_with_password(server: ServerConfig) -> int:
    """密码认证 SSH 连接，使用 pty。"""
    pid, fd = pty.fork()
    if pid == 0:
        # 子进程：执行 ssh
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
```

- [ ] **Step 2: 手动验证（需要真实 SSH 服务器）**

```bash
python3 -m sshm init
python3 -m sshm add  # 添加一台密码认证的服务器
python3 -m sshm connect <server-name>
```

验证：
- 连接成功后能正常交互
- Ctrl+C 能正确传递到远程
- 终端窗口大小调整能传递
- 错误密码提示认证失败
- 无法连接时 30s 超时

- [ ] **Step 3: 提交**

```bash
git add src/sshm/ssh.py
git commit -m "feat: 实现 SSH 连接模块 (pty 密码认证 + 密钥认证)"
```

---

## Task 7: transfer.py — SCP 文件传输

**文件：**
- 创建：`src/sshm/transfer.py`

- [ ] **Step 1: 实现 transfer.py**

创建 `src/sshm/transfer.py`：

```python
"""文件传输模块 — SCP 上传/下载。"""

import subprocess
import sys

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
    """执行 scp 命令。密码认证时使用 pty 注入密码。"""
    if server.auth_type == "key":
        result = subprocess.run(cmd)
        return result.returncode
    else:
        return _scp_with_password(server, cmd)


def _scp_with_password(server: ServerConfig, cmd: list[str]) -> int:
    """密码认证的 SCP 传输。"""
    import os
    import pty
    import select
    import time
    import termios
    import tty
    import signal

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
```

- [ ] **Step 2: 手动验证**

```bash
python3 -m sshm upload <server> ./testfile.txt /tmp/testfile.txt
python3 -m sshm download <server> /tmp/testfile.txt ./downloaded.txt
diff testfile.txt downloaded.txt
```

- [ ] **Step 3: 提交**

```bash
git add src/sshm/transfer.py
git commit -m "feat: 实现 SCP 文件传输模块 (上传/下载)"
```

---

## Task 8: cli.py — 命令行入口

**文件：**
- 创建：`src/sshm/cli.py`
- 创建：`tests/test_cli.py`

- [ ] **Step 1: 编写测试 — cli 模块**

创建 `tests/test_cli.py`：

```python
"""cli 模块单元测试。"""

import os
import tempfile
from unittest.mock import patch, MagicMock
import pytest
from sshm.cli import main, get_password, get_vault_password


class TestGetPassword:
    @patch("sshm.cli.getpass.getpass")
    def test_returns_input(self, mock_getpass):
        """get_password 应返回用户输入。"""
        mock_getpass.return_value = "my-password"
        result = get_password("Enter password: ")
        assert result == "my-password"


class TestCLIParsing:
    def test_no_args_launches_tui(self):
        """无参数应调用 TUI。"""
        with patch("sshm.cli.run_tui") as mock_tui:
            with patch("sys.argv", ["sshm"]):
                main()
            mock_tui.assert_called_once()

    def test_help_exits(self):
        """--help 应正常退出。"""
        with patch("sys.argv", ["sshm", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_init_creates_vault(self):
        """sshm init 应创建 vault 文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = os.path.join(tmpdir, "vault.enc")
            with patch("sshm.cli.getpass.getpass", return_value="test-password"):
                with patch("sys.argv", ["sshm", "init", "--vault", vault_path]):
                    main()
            assert os.path.exists(vault_path)

    def test_ls_no_vault_shows_error(self):
        """vault 不存在时 ls 应报错。"""
        with patch("sys.argv", ["sshm", "ls", "--vault", "/nonexistent/vault.enc"]):
            with pytest.raises(SystemExit):
                main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_cli.py -v
```

预期：FAIL — `ModuleNotFoundError: No module named 'sshm.cli'`

- [ ] **Step 3: 实现 cli.py**

创建 `src/sshm/cli.py`：

```python
"""命令行入口 — argparse 命令解析和路由。"""

import argparse
import getpass
import os
import sys

from sshm.vault import Vault, ServerConfig
from sshm.session import store_key, load_key, clear_key


def get_password(prompt: str = "Master password: ") -> str:
    """安全地获取密码输入。"""
    return getpass.getpass(prompt)


def get_vault_password(args) -> str:
    """获取 vault 密码：优先从 Keychain 缓存读取，否则提示输入。"""
    if not args.no_cache:
        cached = load_key()
        if cached:
            return cached
    return get_password()


def cmd_init(args):
    """处理 init 命令。"""
    vault = Vault(args.vault)
    if vault.path_exists() and not args.force:
        print(f"Vault already exists: {vault.path}")
        print("Use --force to overwrite.")
        sys.exit(1)
    password = get_password("Set master password: ")
    confirm = get_password("Confirm master password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)
    vault.init(password, force=args.force)
    print(f"Vault created: {vault.path}")


def cmd_add(args):
    """处理 add 命令。"""
    vault = Vault(args.vault)
    password = get_vault_password(args)
    print("Adding a new server:")
    name = input("  Name: ")
    host = input("  Host: ")
    port_str = input("  Port [22]: ")
    port = int(port_str) if port_str else 22
    user = input("  User: ")
    auth_type = input("  Auth type (key/password): ")
    key_path = None
    pwd = None
    if auth_type == "key":
        key_path = input("  Key path [~/.ssh/id_rsa]: ") or "~/.ssh/id_rsa"
    else:
        pwd = get_password("  Server password: ")
    group = input("  Group: ")
    notes = input("  Notes: ")
    server = ServerConfig(
        name=name, host=host, port=port, user=user,
        auth_type=auth_type, key_path=key_path, password=pwd,
        group=group, notes=notes,
    )
    vault.add_server(server, password)
    print(f"Server '{name}' added.")


def cmd_ls(args):
    """处理 ls 命令。"""
    vault = Vault(args.vault)
    password = get_vault_password(args)
    servers = vault.list_servers(password)
    if not servers:
        print("(no servers configured — use 'sshm add' to add one)")
        return
    print(f"  {'#':<4} {'Name':<16} {'Address':<20} {'User':<10} {'Auth':<6} {'Group'}")
    print(f"  {'---':<4} {'---':<16} {'---':<20} {'---':<10} {'---':<6} {'---'}")
    for i, s in enumerate(servers, 1):
        auth_label = "key" if s.auth_type == "key" else "pwd"
        pwd_display = "***" if s.password else ""
        print(f"  {i:<4} {s.name:<16} {s.host:<20} {s.user:<10} {auth_label:<6} {s.group}")


def cmd_connect(args):
    """处理 connect/ssh 命令。"""
    from sshm.ssh import ssh_connect
    vault = Vault(args.vault)
    password = get_vault_password(args)
    servers = vault.list_servers(password)
    if not servers:
        print("No servers configured. Add one with 'sshm add' first.")
        sys.exit(1)
    server = _find_server(servers, args.server)
    sys.exit(ssh_connect(server))


def cmd_edit(args):
    """处理 edit 命令。"""
    vault = Vault(args.vault)
    password = get_vault_password(args)
    servers = vault.list_servers(password)
    server = _find_server(servers, args.server)
    print(f"Editing '{server.name}' (press Enter to keep current value):")
    updates = {}
    new_host = input(f"  Host [{server.host}]: ")
    if new_host:
        updates["host"] = new_host
    new_port = input(f"  Port [{server.port}]: ")
    if new_port:
        updates["port"] = int(new_port)
    new_user = input(f"  User [{server.user}]: ")
    if new_user:
        updates["user"] = new_user
    new_group = input(f"  Group [{server.group}]: ")
    if new_group:
        updates["group"] = new_group
    new_notes = input(f"  Notes [{server.notes}]: ")
    if new_notes:
        updates["notes"] = new_notes
    if updates:
        vault.edit_server(server.name, updates, password)
        print(f"Server '{server.name}' updated.")
    else:
        print("No changes.")


def cmd_rm(args):
    """处理 rm 命令。"""
    vault = Vault(args.vault)
    password = get_vault_password(args)
    vault.remove_server(args.server, password)
    print(f"Server '{args.server}' removed.")


def cmd_upload(args):
    """处理 upload 命令。"""
    from sshm.transfer import scp_upload
    vault = Vault(args.vault)
    password = get_vault_password(args)
    servers = vault.list_servers(password)
    server = _find_server(servers, args.server)
    sys.exit(scp_upload(server, args.local, args.remote))


def cmd_download(args):
    """处理 download 命令。"""
    from sshm.transfer import scp_download
    vault = Vault(args.vault)
    password = get_vault_password(args)
    servers = vault.list_servers(password)
    server = _find_server(servers, args.server)
    sys.exit(scp_download(server, args.remote, args.local))


def cmd_password(args):
    """处理 password 命令（修改主密码）。"""
    vault = Vault(args.vault)
    old_password = get_password("Current master password: ")
    data = vault.load(old_password)
    new_password = get_password("New master password: ")
    confirm = get_password("Confirm new master password: ")
    if new_password != confirm:
        print("Passwords do not match.")
        sys.exit(1)
    vault.save(data, new_password)
    clear_key()
    print("Master password changed.")


def cmd_lock(args):
    """处理 lock 命令。"""
    clear_key()
    print("Session locked. Master password will be required on next use.")


def cmd_export(args):
    """处理 export 命令。"""
    import json
    vault = Vault(args.vault)
    password = get_vault_password(args)
    data = vault.load(password)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _find_server(servers: list[ServerConfig], name_or_index: str) -> ServerConfig:
    """按名称或序号查找服务器。"""
    if name_or_index.isdigit():
        idx = int(name_or_index) - 1
        if 0 <= idx < len(servers):
            return servers[idx]
    for s in servers:
        if s.name == name_or_index:
            return s
    print(f"Server not found: {name_or_index}")
    sys.exit(1)


def run_tui():
    """启动 Textual TUI。"""
    from sshm.tui import SSHManagerApp
    app = SSHManagerApp()
    app.run()


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。"""
    parser = argparse.ArgumentParser(
        prog="sshm",
        description="SSH Server Manager — encrypted, interactive CLI",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    parser.add_argument("--no-cache", action="store_true", help="跳过 Keychain 缓存")
    parser.add_argument("--vault", default="~/.sshm/vault.enc", help="vault 文件路径")

    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="初始化加密 vault")
    p_init.add_argument("--force", action="store_true", help="覆盖已有 vault")

    # add
    sub.add_parser("add", help="添加服务器")

    # ls
    sub.add_parser("ls", help="列出所有服务器")

    # connect / ssh
    p_conn = sub.add_parser("connect", help="连接到服务器")
    p_conn.add_argument("server", help="服务器名称或序号")
    p_ssh = sub.add_parser("ssh", help="连接到服务器 (connect 别名)")
    p_ssh.add_argument("server", help="服务器名称或序号")

    # edit
    p_edit = sub.add_parser("edit", help="编辑服务器配置")
    p_edit.add_argument("server", help="服务器名称或序号")

    # rm
    p_rm = sub.add_parser("rm", help="删除服务器")
    p_rm.add_argument("server", help="服务器名称或序号")

    # upload
    p_up = sub.add_parser("upload", help="上传文件 (SCP)")
    p_up.add_argument("server", help="服务器名称或序号")
    p_up.add_argument("local", help="本地文件路径")
    p_up.add_argument("remote", help="远程文件路径")

    # download
    p_dl = sub.add_parser("download", help="下载文件 (SCP)")
    p_dl.add_argument("server", help="服务器名称或序号")
    p_dl.add_argument("remote", help="远程文件路径")
    p_dl.add_argument("local", help="本地文件路径")

    # password
    sub.add_parser("password", help="修改主密码")

    # lock
    sub.add_parser("lock", help="清除 Keychain 会话缓存")

    # export
    sub.add_parser("export", help="导出服务器配置 (JSON)")

    return parser


def main():
    """主入口。"""
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        os.environ["SSHM_VERBOSE"] = "1"

    if not args.command:
        run_tui()
        return

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "ls": cmd_ls,
        "connect": cmd_connect,
        "ssh": cmd_connect,
        "edit": cmd_edit,
        "rm": cmd_rm,
        "upload": cmd_upload,
        "download": cmd_download,
        "password": cmd_password,
        "lock": cmd_lock,
        "export": cmd_export,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
```

- [ ] **Step 4: 在 Vault 类中补充 path_exists 方法**

在 `src/sshm/vault.py` 的 Vault 类中添加：

```python
    def path_exists(self) -> bool:
        """vault 文件是否存在。"""
        return os.path.exists(self.path)
```

- [ ] **Step 5: 运行 cli 测试**

```bash
pytest tests/test_cli.py -v
```

预期：5 个测试 PASS

- [ ] **Step 6: 手动验证完整命令流程**

```bash
python3 -m sshm init
python3 -m sshm add
python3 -m sshm ls
python3 -m sshm lock
python3 -m sshm --help
```

- [ ] **Step 7: 提交**

```bash
git add src/sshm/cli.py tests/test_cli.py src/sshm/vault.py
git commit -m "feat: 实现 CLI 命令入口 (argparse + 全部子命令)"
```

---

## Task 9: tui.py — Textual 交互式 TUI

**文件：**
- 创建：`src/sshm/tui.py`

- [ ] **Step 1: 实现 tui.py**

创建 `src/sshm/tui.py`：

```python
"""交互式 TUI — 基于 Textual。"""

import getpass
import os
import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static

from sshm.vault import Vault, ServerConfig
from sshm.session import load_key, clear_key


class SSHManagerApp(App):
    """sshm 交互式服务器管理界面。"""

    TITLE = "sshm — SSH Server Manager"
    CSS = """
    #search-bar {
        height: 3;
        margin: 0 1;
    }
    #search-input {
        width: 100%;
    }
    #status-bar {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    #main-table {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("slash", "focus_search", "搜索", key_display="/"),
        Binding("a", "add_server", "添加"),
        Binding("e", "edit_server", "编辑"),
        Binding("d", "delete_server", "删除"),
        Binding("enter", "connect_server", "连接"),
        Binding("u", "upload_file", "上传"),
        Binding("x", "download_file", "下载"),
        Binding("escape", "unfocus_search", "取消搜索"),
    ]

    def __init__(self, vault_path: str = "~/.sshm/vault.enc"):
        super().__init__()
        self.vault = Vault(vault_path)
        self.password = ""
        self.servers: list[ServerConfig] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(id="search-bar"):
                yield Input(placeholder="搜索 (/)", id="search-input")
            yield DataTable(id="main-table")
            yield Static(
                "/ 搜索  ↑↓ 导航  Enter 连接  e 编辑  d 删除  u 上传  x 下载  q 退出",
                id="status-bar",
            )
        yield Footer()

    def on_mount(self) -> None:
        """启动时加载 vault 数据。"""
        self._setup_table()
        self._authenticate_and_load()

    def _setup_table(self) -> None:
        """配置表格列。"""
        table = self.query_one("#main-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("#", "Name", "Address", "User", "Auth", "Group")

    def _authenticate_and_load(self) -> None:
        """认证并加载服务器列表。"""
        cached = load_key()
        if cached:
            self.password = cached
        else:
            self.password = getpass.getpass("Master password: ")

        try:
            self.servers = self.vault.list_servers(self.password)
        except Exception:
            self.password = getpass.getpass("Master password (retry): ")
            try:
                self.servers = self.vault.list_servers(self.password)
            except Exception as e:
                self.exit(message=f"Authentication failed: {e}")
                return

        self._refresh_table()

    def _refresh_table(self, filter_text: str = "") -> None:
        """刷新表格显示。"""
        table = self.query_one("#main-table", DataTable)
        table.clear()

        filtered = self.servers
        if filter_text:
            ft = filter_text.lower()
            filtered = [
                s for s in self.servers
                if ft in s.name.lower() or ft in s.host.lower()
            ]

        if not filtered:
            if not self.servers:
                table.add_row("", "(empty — use 'sshm add' to add your first server)", "", "", "", "")
            else:
                table.add_row("", "(no match)", "", "", "", "")
            return

        for i, s in enumerate(filtered, 1):
            auth_label = "key" if s.auth_type == "key" else "pwd"
            table.add_row(str(i), s.name, s.host, s.user, auth_label, s.group)

    def on_input_changed(self, event: Input.Changed) -> None:
        """搜索输入变化时过滤表格。"""
        if event.input.id == "search-input":
            self._refresh_table(event.value)

    def action_focus_search(self) -> None:
        """聚焦搜索框。"""
        search = self.query_one("#search-input", Input)
        search.focus()

    def action_unfocus_search(self) -> None:
        """取消搜索，清空搜索框。"""
        search = self.query_one("#search-input", Input)
        search.value = ""
        table = self.query_one("#main-table", DataTable)
        table.focus()

    def _get_selected_server(self) -> ServerConfig | None:
        """获取当前选中的服务器。"""
        table = self.query_one("#main-table", DataTable)
        row = table.cursor_row
        if row is None or row >= len(self.servers):
            return None
        return self.servers[row]

    def action_connect_server(self) -> None:
        """连接到选中的服务器。"""
        server = self._get_selected_server()
        if not server:
            return
        self.exit(result=server)

    def action_add_server(self) -> None:
        """添加服务器（跳转到 CLI add）。"""
        self.exit(message="Use 'sshm add' to add a new server.")

    def action_edit_server(self) -> None:
        """编辑选中的服务器（跳转到 CLI edit）。"""
        server = self._get_selected_server()
        if not server:
            return
        self.exit(message=f"Use 'sshm edit {server.name}' to edit this server.")

    def action_delete_server(self) -> None:
        """删除选中的服务器。"""
        server = self._get_selected_server()
        if not server:
            return
        try:
            self.vault.remove_server(server.name, self.password)
            self.servers = self.vault.list_servers(self.password)
            self._refresh_table()
        except Exception as e:
            self.exit(message=f"Delete failed: {e}")

    def action_upload_file(self) -> None:
        """上传文件。"""
        server = self._get_selected_server()
        if not server:
            return
        self.exit(message=f"Use 'sshm upload {server.name} <local> <remote>' to upload.")

    def action_download_file(self) -> None:
        """下载文件。"""
        server = self._get_selected_server()
        if not server:
            return
        self.exit(message=f"Use 'sshm download {server.name} <remote> <local>' to download.")
```

- [ ] **Step 2: 更新 cli.py 中的 run_tui 函数处理连接结果**

替换 `src/sshm/cli.py` 中的 `run_tui` 函数：

```python
def run_tui():
    """启动 Textual TUI。"""
    from sshm.tui import SSHManagerApp
    from sshm.ssh import ssh_connect

    parser = build_parser()
    args, _ = parser.parse_known_args()
    vault_path = getattr(args, "vault", "~/.sshm/vault.enc")

    app = SSHManagerApp(vault_path=vault_path)
    result = app.run()

    # 如果 TUI 返回了 ServerConfig，说明用户选择连接
    if isinstance(result, ServerConfig):
        sys.exit(ssh_connect(result))
```

- [ ] **Step 3: 手动验证 TUI**

```bash
python3 -m sshm
```

验证：
- 表格正确显示服务器列表
- `/` 键激活搜索框
- ↑↓ 键导航
- Enter 连接
- 空状态显示提示信息

- [ ] **Step 4: 提交**

```bash
git add src/sshm/tui.py src/sshm/cli.py
git commit -m "feat: 实现 Textual 交互式 TUI (搜索/导航/快捷键)"
```

---

## Task 10: 集成验证

**文件：**
- 无新文件

- [ ] **Step 1: 运行全部自动化测试**

```bash
pytest tests/ -v
```

预期：全部 PASS

- [ ] **Step 2: 端到端手动验证**

按 `docs/architecture.md` 的验证计划逐项检查：

```bash
# 1. 加密验证
python3 -m sshm init
cat ~/.sshm/vault.enc | xxd | head -5  # 应该看到乱码，不是明文

# 2. 添加服务器
python3 -m sshm add

# 3. 列出服务器
python3 -m sshm ls

# 4. 连接（密钥认证）
python3 -m sshm connect <key-server>

# 5. 连接（密码认证）
python3 -m sshm connect <password-server>

# 6. 文件传输
python3 -m sshm upload <server> ./test.txt /tmp/test.txt
python3 -m sshm download <server> /tmp/test.txt ./downloaded.txt

# 7. 会话缓存
python3 -m sshm ls   # 第二次不应提示密码（在 TTL 内）
python3 -m sshm lock
python3 -m sshm ls   # 应重新提示密码

# 8. 修改主密码
python3 -m sshm password

# 9. 导出
python3 -m sshm export

# 10. TUI 交互
python3 -m sshm
```

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "chore: 集成验证完成，v0.1.0 可用"
```
