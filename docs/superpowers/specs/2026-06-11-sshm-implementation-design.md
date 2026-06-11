# sshm 实现设计文档

**日期**: 2026-06-11
**状态**: 已确认
**实现方式**: 自底向上分层实现

## 概述

sshm（SSH Server Manager）是一个 macOS 原生的 SSH 服务器管理 CLI 工具，支持加密凭据存储。本文档在原有架构文档基础上，补充了头脑风暴阶段确认的实现决策。

## 决策记录

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 目标用户 | 个人开发者自用 | 实用优先，不需要过度工程化 |
| TUI 框架 | Textual（非纯 Rich） | Rich 无法实现键盘导航和实时搜索 |
| 包格式 | 标准 Python 包（pyproject.toml） | 规范的依赖管理，未来可发布到 PyPI |
| 测试策略 | pytest 单元测试（crypto、vault、session） | 核心逻辑需要自动化验证 |
| 实现顺序 | 自底向上，7 层 | 每层独立可测 |
| Python 版本 | 3.10+ | 使用现代语法（match、TypeAlias） |

## 项目结构

```
sshm/
├── pyproject.toml
├── requirements.txt
├── README.md
├── LICENSE
├── docs/
│   ├── architecture.md
│   ├── usage.md
│   └── superpowers/specs/
├── src/
│   └── sshm/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── crypto.py
│       ├── vault.py
│       ├── session.py
│       ├── ssh.py
│       ├── transfer.py
│       └── tui.py
└── tests/
    ├── __init__.py
    ├── test_crypto.py
    ├── test_vault.py
    ├── test_session.py
    └── test_cli.py
```

## 依赖

运行时（2 个）：
- `textual`（内含 `rich`，无需单独安装）
- `cryptography`

开发：
- `pytest`

## 实现分层

```
第 1 层: crypto.py      ← 无依赖，AES-256-GCM + PBKDF2-SHA256
第 2 层: vault.py       ← 依赖 crypto，ServerConfig + 文件锁
第 3 层: session.py     ← 依赖 crypto，macOS Keychain 缓存
第 4 层: ssh.py         ← 无内部依赖，pty 方式 SSH 连接
第 5 层: transfer.py    ← 依赖 vault，SCP 上传/下载
第 6 层: cli.py         ← 依赖 vault + session + ssh + transfer，argparse
第 7 层: tui.py         ← 依赖 vault + session + ssh + transfer，Textual 应用
```

每层的工作流：实现代码 → 编写单元测试 → 验证通过 → 进入下一层。

## 核心接口

### crypto.py — 加解密

```python
SALT_SIZE = 16
IV_SIZE = 12
KDF_ITERATIONS = 600_000

def derive_key(password: str, salt: bytes) -> bytes
def encrypt(plaintext: bytes, password: str) -> bytes
def decrypt(data: bytes, password: str) -> bytes
```

### vault.py — 数据管理

```python
@dataclass
class ServerConfig:
    name: str
    host: str
    user: str
    auth_type: Literal["key", "password"]
    port: int = 22
    key_path: Optional[str] = None
    password: Optional[str] = None
    group: str = ""
    notes: str = ""

class Vault:
    def __init__(self, path: str = "~/.sshm/vault.enc")
    def load(self, password: str) -> dict
    def save(self, data: dict, password: str) -> None
    def init(self, password: str, force: bool = False) -> None
    def add_server(self, server: ServerConfig, password: str) -> None
    def remove_server(self, name_or_index: str, password: str) -> None
    def edit_server(self, name_or_index: str, updates: dict, password: str) -> None
    def list_servers(self, password: str) -> list[ServerConfig]
```

### session.py — 会话缓存

```python
DEFAULT_TTL = 3600

def store_key(key_hex: str, ttl: int = DEFAULT_TTL) -> None
def load_key() -> str | None
def clear_key() -> None
```

### ssh.py — SSH 连接

```python
def ssh_connect(server: ServerConfig) -> int
```

### transfer.py — 文件传输

```python
def scp_upload(server: ServerConfig, local_path: str, remote_path: str) -> int
def scp_download(server: ServerConfig, remote_path: str, local_path: str) -> int
```

### cli.py — 命令入口

```python
def main() -> None  # argparse 入口
```

命令列表：init、add、ls、connect/ssh、edit、rm、upload、download、password、lock、export，无参数时启动 TUI。

### tui.py — 交互界面

```python
class SSHManagerApp(textual.app.App):
    # Textual TUI：DataTable 列表、Input 搜索、按键绑定
    pass
```

## 与原架构文档的差异

1. **ui.py → tui.py**：文件重命名，反映使用 Textual 框架
2. **Rich → Textual**：TUI 框架更换，支持键盘导航和实时搜索
3. **新增 tests/**：为 crypto、vault、session 编写 pytest 单元测试
4. **新增 pyproject.toml**：标准 Python 包布局，使用 src/ 目录
5. **依赖调整**：`rich` 替换为 `textual`（内含 rich）

## 保留原设计的部分

以下设计完全保留 `docs/architecture.md` 中的方案，不做修改：

- 加密方案（AES-256-GCM + PBKDF2 600K 迭代）
- Vault 文件格式（salt || IV || ciphertext || auth tag）
- pty 方式的 SSH 连接（密码检测、错误处理、30s 超时）
- SCP 文件传输
- macOS Keychain 会话缓存 + TTL
- ServerConfig 数据验证
- POSIX 文件锁并发控制
- 全部 11 个命令及其边界处理
