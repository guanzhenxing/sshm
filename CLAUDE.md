# CLAUDE.md

Project guidance for Claude Code (and human contributors) working in this repo.

## What is sshm

`sshm` (SSH Server Manager) is a **macOS-native** CLI + interactive TUI for managing and connecting to SSH servers, with **encrypted credential storage** (AES-256-GCM). It shells out to the system `ssh`/`scp`; password auth uses Python's `pty` (no `sshpass`). The derived AES key can be cached in the macOS Keychain for the session.

## Tech stack

- **Python 3.10+** (uses modern typing: `X | None`, etc.)
- **Textual** — the interactive TUI (NOT Rich; early docs said Rich, that is stale)
- **cryptography** — AES-256-GCM + PBKDF2-SHA256 (600k iterations)
- **pytest** + **pytest-asyncio** (`asyncio_mode = "auto"`)
- macOS only — depends on the `security` CLI for Keychain access

## Common commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"          # or: pip install -r requirements.txt

# Run the app
sshm                            # console script (entry point: sshm.cli:main)
python -m sshm                  # equivalent
./install.sh                    # installs a wrapper to /usr/local/bin (uses .venv)

# Tests
pytest                          # full suite (59 tests)
pytest tests/test_tui.py -v     # TUI behavior tests via Textual Pilot
pytest -k search                # filter

# Subcommands
sshm init | add | ls | connect <name|#> | edit | rm | upload | download | password | lock | export
sshm                            # no args → interactive TUI
```

## Architecture (source of truth = `src/sshm/`)

```
src/sshm/
├── __main__.py     # `python -m sshm` → cli.main
├── cli.py          # argparse parsing/routing; run_tui() launches the app + dispatches its result
├── crypto.py       # AES-256-GCM encrypt/decrypt + PBKDF2 key derivation
├── vault.py        # ServerConfig dataclass + encrypted vault read/write + fcntl file locking
├── session.py      # Keychain session cache (store/load/clear derived key, TTL)
├── ssh.py          # ssh connect via pty (key or password auth)
├── transfer.py     # scp upload/download
└── tui.py          # Textual TUI (see below)
```

### TUI architecture (Textual) — `tui.py`

A **multi-Screen** app. `SSHManagerApp` is a *coordinator* only — it holds state (vault, password, servers) and manages the Screen stack. **It has no `BINDINGS`, no `compose`, no status bar.** All keybindings live on the individual Screens, each of which yields its own `Footer` (the Footer auto-renders the *current* Screen's bindings, so the hint line is always context-correct and never duplicated).

Four Screens:
- `PasswordScreen` — master-password entry / retry.
- `MainScreen` — server list + search. This is the keystone.
- `ServerForm` — add/edit server.
- `TransferForm` — upload/download path entry.

### Critical TUI gotchas (do not regress)

- **`MainScreen.AUTO_FOCUS = ""`** — deliberately falsy so focus stays `None`. This is what lets the Screen's own bindings fire directly *and* prevents an unfocused `DataTable` from swallowing `enter` via its `enter→select_cursor` binding. Do not "improve" by focusing the table.
- **Quit binding is `app.quit`, not bare `quit`.** `action_quit` lives on `App`, and Textual does **not** walk Screen→App to resolve an action method. A bare `"quit"` binding on a Screen silently no-ops. The other MainScreen actions (`add_server`, etc.) work because each has a matching `action_*` method *on the Screen*.
- **Search box is the single source of truth for filtering.** `_refresh_table()` reads the search input's value; the rendered list is mirrored in `_filtered_servers`, which `_get_selected_server` indexes (not the unfiltered `app.servers`). `Enter` in the search box *commits* the query (keep filter, return focus to None so main bindings act on the filtered list); `Esc` *cancels* (clear + focus None).
- **Exit contract** (`cli.run_tui` dispatches `app.run()`'s return value):
  - `ServerConfig` → `ssh_connect`
  - `("transfer", server, mode, local, remote)` 5-tuple → `scp_upload`/`scp_download`
  - `None` → fall through

## Testing conventions

- TUI tests use the **Textual Pilot** (`app.run_test(size=(80, 50))`). The large size keeps `ServerForm` controls inside the viewport (`max-height: 80vh` + scroll).
- After auth, the main table has **focus = None** and `cursor_row = 0`; do not focus the DataTable in tests (it would swallow `enter`).
- `_table(app)` scans `app.screen_stack` for the `MainScreen` (not `app.query_one`, which only sees the active screen).
- Follow TDD for bug fixes: write the failing test, watch it fail, then fix.

## Conventions

- **Commit style:** Conventional Commits in Chinese — `feat:` / `fix:` / `refactor:` / `chore:` / `test:` / `docs:` / `chore(tui):`.
- **Branching:** develop on a feature branch; fast-forward merge into `main` (linear history).
- **Docs are partially stale** (Rich→Textual, `ui.py`→`tui.py`, a documented `SSHM_CACHE_TTL` env var that is not implemented). Trust the source over the docs until the doc cleanup lands.
