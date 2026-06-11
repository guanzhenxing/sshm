<div align="center">
  <h1>sshm</h1>
  <p><strong>S</strong>SH <strong>S</strong>erver <strong>M</strong>anager for macOS</p>
  <p>Encrypted, interactive CLI for managing and connecting to SSH servers — built for the Mac terminal.</p>
</div>

<p align="center">
  <code>sshm</code> &nbsp;·&nbsp;
  <code>sshm ls</code> &nbsp;·&nbsp;
  <code>sshm connect &lt;server&gt;</code> &nbsp;·&nbsp;
  <code>sshm upload &lt;server&gt; &lt;local&gt; &lt;remote&gt;</code>
</p>

---

## Overview

sshm is a macOS-native SSH server management CLI. It fills the gap for developers who manage a handful of servers with mixed key/password authentication and want an experience similar to WinTerm on Windows — but with **encrypted credential storage**.

### Features

- **Encrypted vault** — Server credentials are encrypted at rest with AES-256-GCM.
- **Interactive TUI** — Browse, search, filter, and connect to servers with arrow keys (powered by [Rich](https://github.com/Textualize/rich)).
- **System SSH** — Uses macOS's native `ssh` and `scp` commands. Full terminal emulation, SSH agent forwarding, and `~/.ssh/config` support work out of the box.
- **Mixed auth** — Supports both key-based and password-based authentication per server. Password auth uses Python's `pty` module — no external tools like `sshpass` needed.
- **Session caching** — AES key cached in macOS Keychain after first unlock; subsequent invocations skip the password prompt.
- **File transfer** — Upload and download files via SCP.

## Quick Start

```bash
# Install
git clone https://github.com/your-org/sshm.git && cd sshm
pip3 install -r requirements.txt

# Initialize the vault (you'll be prompted for a master password)
python3 -m sshm init

# Add your first server
python3 -m sshm add

# Launch the interactive TUI (master password cached in Keychain after first use)
python3 -m sshm
```

For convenience, add an alias to your shell:

```bash
echo 'alias sshm="python3 /path/to/sshm"' >> ~/.zshrc
```

## Requirements

- macOS (tested on Ventura / Sonoma / Sequoia)
- Python 3.10+
- `ssh` and `scp` (pre-installed on macOS)

No other external dependencies. `sshpass` is **not** required — password-based auth uses Python's built-in `pty` module.

## Project Status

Active development. The project is in its initial implementation phase.

## License

MIT
