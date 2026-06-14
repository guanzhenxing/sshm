# 使用指南

## 全局选项

| 选项 | 说明 |
|---|---|
| `-v`, `--verbose` | 详细输出 |
| `--no-cache` | 跳过 Keychain 会话缓存，每次都提示输入主密码 |
| `-h`, `--help` | 显示帮助并退出 |

**会话缓存：** 主密码缓存在 macOS Keychain，TTL 固定 3600 秒（`session.py` 的 `DEFAULT_TTL`）。用 `sshm lock` 立即清除；用 `--no-cache` 跳过缓存、每次都提示。

## 交互式 TUI（`sshm`，无参数）

启动交互模式。输入主密码（或从 Keychain 缓存读取）后，进入可搜索的服务器列表：

```
  #  Name         Address          User     Auth  Group
  1  prod-web     192.168.1.100    admin    key   production
  2  prod-db      192.168.1.101    admin    key   production
  3  staging-app  10.0.0.50        deploy   pwd   staging

  / 搜索 · a 添加 · e 编辑 · d 删除 · Enter 连接 · u 上传 · x 下载 · q 退出 · Esc 取消搜索
```

**搜索：** 按 `/` 聚焦搜索框，按名称或地址实时过滤；**Enter 提交**查询（保留过滤结果、焦点回到列表，可直接对过滤结果操作）；**Esc 取消**（清空、回到全量）。

空状态（未配置任何服务器）：

```
  (empty — 按 a 添加你的第一台服务器)
```

## 命令参考

### `sshm init`

初始化加密 vault，提示设置主密码。已存在则拒绝；`sshm init --force` 覆盖（仅确认提示，无需旧密码）。

### `sshm add`

交互式添加一台服务器，依次提示：名称、地址、端口、用户、认证方式、密钥路径/密码、分组、备注。

### `sshm ls`

列出所有服务器（密码掩码为 `***`）。空时输出 `(no servers configured — use 'sshm add' to add one)`。

### `sshm connect <server>` / `sshm ssh <server>`

按名称或序号连接（两者互为别名）。

```bash
sshm connect prod-web
sshm ssh 1
```

空 vault：报错 "No servers configured. Add one with 'sshm add' first."

### `sshm edit <server>`

增量编辑：显示当前值，回车保留不变。认证方式从 key 改 password 会提示输入密码，反之亦然。

```bash
sshm edit 2
sshm edit staging-app
```

### `sshm rm <server>`

从 vault 删除一台服务器。

```bash
sshm rm 1
sshm rm staging-db
```

### `sshm upload <server> <local> <remote>`

通过 SCP 上传文件。

```bash
sshm upload prod-web ./deploy.sh /home/admin/deploy.sh
```

### `sshm download <server> <remote> <local>`

通过 SCP 下载文件。

```bash
sshm download prod-web /var/log/app.log ./app.log
```

### `sshm password`

修改主密码，用新密钥重新加密整个 vault。

### `sshm lock`

清除 Keychain 会话缓存，下次调用需重新输入主密码。

### `sshm export`

解密并以 JSON 明文打印服务器配置。

```bash
sshm export
```

**警告：** 若终端输出正被记录（`script(1)`、tmux logging 等），明文密码可能落盘。

## 安装命令

推荐用 pyproject 声明的 console script（`pip install -e .` 后直接 `sshm`），或运行 `./install.sh` 安装 wrapper 到 `/usr/local/bin`。详见 [README 快速开始](../README.md#快速开始)。`sshm` 等效于 `python -m sshm`。

## 示例

```bash
# 添加并连接一台服务器
sshm init
sshm add
sshm ls
sshm connect prod-web

# 传输文件
sshm upload prod-web ./backup.sql /var/backups/
sshm download staging-app /var/log/nginx/access.log ./access.log
```
