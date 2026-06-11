# Usage

## Global Options

| Option | Description |
|---|---|
| `-v`, `--verbose` | Enable verbose output |
| `--no-cache` | Skip Keychain session cache; always prompt for master password |
| `-h`, `--help` | Show help message and exit |

**Environment variables:**

| Variable | Default | Description |
|---|---|---|
| `SSHM_CACHE_TTL` | `3600` | Session cache TTL in seconds. Set to `0` to disable. |

## Commands

### `sshm` (no arguments)

Launch the interactive TUI mode. After authenticating with your master password (or from Keychain cache), you'll see a searchable server list.

Normal state:

```
  SSH Server List

  #  Name             Address              User      Auth    Group
 --- ---------------- -------------------- -------- -------- ---------
  1  prod-web         192.168.1.100        admin     key  production
  2  prod-db          192.168.1.101        admin     key  production
  3  staging-app      10.0.0.50            deploy    pwd  staging

  / search  up/down navigate  Enter connect  e edit  d delete  u upload  x download  q quit
```

Press `/` to search by name or host. Empty state (no servers):

```
  (empty -- use `sshm add` to add your first server)

  a add  q quit
```

### `sshm init`

Initialize the encrypted vault. You'll be prompted to set a master password.

```bash
sshm init
# -> Creates ~/.sshm/vault.enc (salt embedded in file header)
# -> Prompts for master password
```

If the vault already exists, the command refuses. Use `sshm init --force` to overwrite (just a confirmation prompt, no old password required).

### `sshm add`

Interactively add a new server to the vault. Prompts for: name, host, port, user, auth_type, key_path/password, group, notes.

```bash
sshm add
```

### `sshm ls`

List all servers. Passwords are masked (`***`).

```bash
sshm ls

# Output:
# 1  prod-web    192.168.1.100   admin   key     production
# 2  staging-db  10.0.0.50       deploy  pwd     staging
```

Empty state: outputs `(no servers configured -- use 'sshm add' to add one)`.

### `sshm connect <server>` / `sshm ssh <server>`

Connect to a server by name or index. `connect` and `ssh` are aliases.

```bash
sshm connect prod-web
sshm ssh 1
```

Empty vault: error "No servers configured. Add one with 'sshm add' first."

### `sshm edit <server>`

Edit a server's configuration incrementally. Current values are shown; press Enter to keep a field unchanged. Changing auth_type from key to password prompts for the password field, and vice versa.

```bash
sshm edit 2
sshm edit staging-app
```

### `sshm rm <server>`

Remove a server from the vault.

```bash
sshm rm 1
sshm rm staging-db
```

### `sshm upload <server> <local_path> <remote_path>`

Upload a file via SCP.

```bash
sshm upload prod-web ./deploy.sh /home/admin/deploy.sh
```

### `sshm download <server> <remote_path> <local_path>`

Download a file via SCP.

```bash
sshm download prod-web /var/log/app.log ./app.log
```

### `sshm password`

Change the master password. Re-encrypts the vault with the new key.

```bash
sshm password
# -> Prompts for current password
# -> Prompts for new password
# -> Re-encrypts vault.enc
```

### `sshm lock`

Clear the Keychain session cache. The master password will be required on the next invocation.

```bash
sshm lock
# -> Removes cached AES key from Keychain
```

### `sshm export`

Export the server configuration in plaintext. Requires master password confirmation.

```bash
sshm export
# -> Prompts for master password
# -> Prints JSON config to stdout
```

Warning: if your terminal output is being logged (script(1), tmux logging), plaintext passwords may be written to disk.

## Shell Alias

Add to `~/.zshrc` or `~/.bashrc`:

```bash
alias sshm="python3 /path/to/sshm"
```

## Examples

### Add and connect to a server

```bash
sshm init
sshm add
sshm ls
sshm connect prod-web
```

### Transfer files

```bash
sshm upload prod-web ./backup.sql /var/backups/
sshm download staging-app /var/log/nginx/access.log ./access.log
```
