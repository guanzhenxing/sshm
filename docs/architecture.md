# Architecture

## Directory Layout

```
~/.sshm/                    # Runtime data directory
└── vault.enc               # Single file: salt || IV || ciphertext || auth tag

sshm/                       # Application package
├── __main__.py             # Entry point (python -m sshm)
├── cli.py                  # Command parsing and routing
├── crypto.py               # Encryption/decryption (AES-256-GCM + PBKDF2)
├── vault.py                # Configuration file read/write with validation + file locking
├── ui.py                   # Rich interactive interface with search
├── ssh.py                  # SSH connection via pty (no sshpass)
├── transfer.py             # SCP file transfer
├── session.py              # macOS Keychain session cache with TTL
└── requirements.txt        # Dependencies: rich, cryptography
```

## Tech Stack Rationale

| Approach | Encryption | Interactive UI | Dev Speed | Best For |
|---|---|---|---|---|
| Shell + fzf | Awkward (openssl) | Depends on fzf | Medium | No encryption needs |
| **Python + Rich** | **Mature (cryptography)** | **Built-in, no deps** | **High** | **Encrypted + <= 30 servers** |
| Go + BubbleTea | Extra impl needed | Built-in | Medium | Large-scale / commercial |

Python was chosen as the best balance given the hard requirement for encrypted storage. macOS ships with `python3`, so no extra runtime is needed.

## SSH Connection Strategy

### Why system ssh

sshm shells out to the system `ssh` and `scp` commands instead of using a Python SSH library (paramiko). This gives:

- Full terminal emulation (colors, interactive commands, TUI programs like `htop`/`vim`)
- SSH agent forwarding works without extra configuration
- Existing `~/.ssh/config` entries are respected
- No need to reimplement SSH protocol handling

### Key-based auth

```python
subprocess.run(["ssh", "-o", f"Port={port}", "-i", key_path, f"{user}@{host}"])
```

### Password-based auth (pty)

Using Python's stdlib `pty` module eliminates the `sshpass` dependency. The implementation handles three phases:

1. **Password prompt detection** — relay SSH output, watch for `password:` prompt
2. **Password injection** — send password when prompt detected, verify it wasn't rejected
3. **Interactive relay** — bidirectional I/O between user terminal and SSH session

Key constraints:
- Before auth: only listen to SSH output (fd), not stdin. If stdin were monitored before auth and the user accidentally pressed a key, select would spin in a busy loop.
- Remote MOTD/banner is buffered during auth, then flushed to stdout after successful login. This prevents the user from seeing a blank screen.
- 30-second timeout on password prompt detection. If it expires, the buffered output is displayed along with a diagnostic message.
- After password is sent, a brief peek (0.3s sleep + 0.5s select) detects whether SSH immediately re-prompts (wrong password) or continues (auth OK).

```python
import pty, os, select, sys, signal, termios, tty, time

def ssh_with_password(host: str, port: int, user: str, password: str) -> int:
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("ssh", [
            "ssh", "-o", f"Port={port}", f"{user}@{host}",
        ])
        os._exit(1)

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
                        f"No password prompt from {user}@{host} within 30s."
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

                        # Peek for immediate re-prompt (wrong password)
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
                                    f"Authentication failed for {user}@{host}"
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

Known limitation: servers that exclusively use keyboard-interactive authentication with a non-standard prompt will time out. The error message guides the user to test connectivity manually.

### SCP port parameter

`ssh` uses lowercase `-p`, `scp` uses uppercase `-P`. The code must handle both:

```python
def build_scp_cmd(server, src, dst):
    cmd = ["scp"]
    cmd.extend(["-P", str(server.port)])
    # ...
```

## Encryption Scheme

### Single-file vault

Salt is embedded directly into the vault file:

```
vault.enc layout:
+----------+----------+--------------+------------+
| Salt     | IV       | Ciphertext   | Auth Tag   |
| 16 bytes | 12 bytes | variable     | 16 bytes   |
+----------+----------+--------------+------------+
```

### Algorithm

```
Master Password -> PBKDF2-SHA256 (600,000 iterations) -> 256-bit AES Key
```

| Component | Detail | Rationale |
|---|---|---|
| Cipher | AES-256-GCM | Authenticated encryption -- confidentiality + integrity |
| KDF | PBKDF2-SHA256, 600K iterations | OWASP 2023 recommended minimum |
| Salt | Random 16 bytes, embedded in vault | Prevents rainbow tables; single-file |
| IV | Random 12 bytes, per encryption | GCM standard nonce size |
| Auth tag | 16 bytes (GCM default) | Detects any tampering |

### Code structure

```python
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

SALT_SIZE = 16
IV_SIZE = 12
KDF_ITERATIONS = 600_000

def derive_key(password: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    ).derive(password.encode("utf-8"))

def encrypt(plaintext: bytes, password: str) -> bytes:
    salt = os.urandom(SALT_SIZE)
    key = derive_key(password, salt)
    iv = os.urandom(IV_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext, None)
    return salt + iv + ciphertext

def decrypt(data: bytes, password: str) -> bytes:
    salt = data[:SALT_SIZE]
    iv = data[SALT_SIZE:SALT_SIZE + IV_SIZE]
    ciphertext = data[SALT_SIZE + IV_SIZE:]
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext, None)
```

### Security

- Confidentiality: Ciphertext is opaque without the master password.
- Integrity: GCM authentication tag detects tampering.
- Decrypted data lives only in process memory, discarded on exit. Python strings cannot be reliably zeroed; this risk is acceptable for a local CLI tool.
- Vault format versioning: decoded JSON contains a "version" field. If the version exceeds what the tool supports, decryption is refused.

### Configuration Format (decrypted JSON)

```json
{
  "version": 1,
  "servers": [
    {
      "name": "staging-db",
      "host": "10.0.0.50",
      "port": 2222,
      "user": "deploy",
      "auth_type": "password",
      "password": "my-secret-password",
      "group": "staging",
      "notes": ""
    }
  ]
}
```

The entire JSON is encrypted inside vault.enc. The `password` field stores the server's plaintext password -- vault-level AES-256-GCM protects it at rest. No double encryption.

### Field Reference

| Field | Required | Description |
|---|---|---|
| `name` | yes | Human-readable server label |
| `host` | yes | Hostname or IP address |
| `port` | no | SSH port (default: 22) |
| `user` | yes | Login username |
| `auth_type` | yes | "key" or "password" |
| `key_path` | if key | Path to private key file (`~` auto-expanded) |
| `password` | if password | Server password (plaintext inside encrypted vault) |
| `group` | no | Logical grouping for display |
| `notes` | no | Free-text notes |

## Vault Concurrency

Multiple `sshm` instances must not corrupt the vault. Writes use POSIX advisory file locks:

```python
import fcntl

def _write_locked(path: str, fn):
    with open(path, "r+b") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        data = f.read()
        result = fn(data)
        f.seek(0)
        f.truncate()
        f.write(result)
        f.flush()
        os.fsync(f.fileno())
```

Reads use shared locks (`LOCK_SH`); writes use exclusive locks (`LOCK_EX`).

## Session Cache (macOS Keychain)

The derived AES key is cached in the macOS Keychain with a TTL:

```
First run:       master password -> derive key -> store {key, expires_at} in Keychain
Subsequent runs: check Keychain -> within TTL? skip prompt. Expired? re-prompt.
sshm lock:       delete key from Keychain
```

Security note: Keychain items are readable by the user's processes without re-authentication. Any program running as the same user can run `security find-generic-password -a sshm -w` to read the cached AES key. This matches the trust model of SSH agent or GPG agent.

```python
import time, json, subprocess

DEFAULT_TTL = 3600

def store_key(key_hex: str, ttl: int = DEFAULT_TTL) -> None:
    payload = json.dumps({"key": key_hex, "expires_at": time.time() + ttl})
    subprocess.run([
        "security", "add-generic-password",
        "-a", "sshm", "-s", "sshm-session-key", "-w", "-U",
    ], input=payload.encode("utf-8"), check=True)

def load_key() -> str | None:
    result = subprocess.run([
        "security", "find-generic-password",
        "-a", "sshm", "-s", "sshm-session-key", "-w",
    ], capture_output=True, text=True)
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
    subprocess.run([
        "security", "delete-generic-password",
        "-a", "sshm", "-s", "sshm-session-key",
    ], capture_output=True)
```

## Data Validation

Server config is validated at load and save time via a dataclass:

1. `~` expansion: `key_path: "~/.ssh/id_rsa"` is expanded to an absolute path via `os.path.expanduser()`.
2. Type coercion: port is validated as integer, `auth_type` checked against allowed values.
3. `from_dict` copies the input dict to avoid mutating the caller's data.

```python
import os
from dataclasses import dataclass
from typing import Literal, Optional

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
```

## Interactive TUI

The TUI is built with [Rich](https://github.com/Textualize/rich) and supports real-time search/filter. Press `/` to search by name or host.

Normal state:

```
  #  Name       Address           User      Auth    Group
 --- ---------- ----------------- -------- -------- ---------
  1  prod-web   192.168.1.100     admin     key  production
  2  prod-db    192.168.1.101     admin     key  production
  3  staging    10.0.0.50         deploy    pwd  staging

  / search  up/down navigate  Enter connect  e edit  d delete
  u upload  x download  q quit
```

Empty state (no servers configured):

```
  (empty -- use `sshm add` to add your first server)

  a add  q quit
```

## Edge Cases

### `sshm init` on existing vault

If vault.enc exists, `sshm init` refuses. `sshm init --force` overwrites after a confirmation prompt -- the old password is not required because anyone with filesystem access can delete the vault anyway.

### `sshm edit <server>`

Incremental edit: current values are shown, user presses Enter to keep a field unchanged. Changing `auth_type` from `"key"` to `"password"` prompts for the new required field (`password`), and vice versa.

### `sshm export`

Prints decrypted JSON to stdout. Warning: if terminal output is being logged (by `script(1)`, tmux logging, etc.), plaintext passwords will be written to disk.

### `sshm ls` with no servers

Outputs: `(no servers configured -- use 'sshm add' to add one)`

### `sshm connect` with no servers

Error: "No servers configured. Add one with 'sshm add' first."

## Verification Plan

1. Encryption: vault.enc is not human-readable; wrong master password yields decrypt error.
2. Connection (key): normal SSH behavior with key-based servers.
3. Connection (password): pty-based interactive SSH works -- commands, Ctrl+C, terminal resize all pass through correctly.
4. Connection (wrong password): pty detects re-prompt, raises PermissionError, restores terminal.
5. Connection (keyboard-interactive server): times out with diagnostic message guiding manual SSH test.
6. Transfer: upload and download files via SCP, verify content.
7. Session cache: cached -> no prompt. Expired -> re-prompt. --no-cache works.
8. Vault concurrency: simultaneous writes from two terminals do not corrupt data.
9. Validation: malformed input rejected at add/edit time.
10. Edge cases: sshm init --force confirmation, ~ expansion, empty vault behavior.
11. Terminal: raw mode restored on Ctrl+C, SIGWINCH forwarded.
