# 架构与设计

本文档面向想读懂或修改 sshm 代码的贡献者。用户视角的用法见 [usage.md](usage.md)。

## 模块划分

运行期数据目录：

```
~/.sshm/
└── vault.enc        # 单文件：salt || IV || ciphertext || auth tag
```

源码包 `src/sshm/`：

| 文件 | 职责 |
|---|---|
| [`__main__.py`](../src/sshm/__main__.py) | 入口：`python -m sshm` → `cli.main` |
| [`cli.py`](../src/sshm/cli.py) | argparse 命令解析与路由；`run_tui()` 启动 TUI 并按返回值分发 |
| [`crypto.py`](../src/sshm/crypto.py) | AES-256-GCM 加解密 + PBKDF2 派生密钥 |
| [`vault.py`](../src/sshm/vault.py) | `ServerConfig` 数据类 + 加密 vault 读写 + fcntl 文件锁 |
| [`session.py`](../src/sshm/session.py) | Keychain 会话缓存（存/取/清主密码，TTL） |
| [`ssh.py`](../src/sshm/ssh.py) | 基于 pty 的 SSH 连接（密钥 / 密码认证） |
| [`transfer.py`](../src/sshm/transfer.py) | SCP 上传 / 下载 |
| [`tui.py`](../src/sshm/tui.py) | Textual 交互式 TUI（见下文「TUI 架构」） |

## 技术选型

| 方案 | 加密 | 交互 UI | 开发速度 | 适用 |
|---|---|---|---|---|
| Shell + fzf | 别扭（openssl） | 依赖 fzf | 中 | 无加密需求 |
| **Python + Textual** | **成熟（cryptography）** | **内置、零额外依赖** | **高** | **加密 + ≤ 几十台服务器** |
| Go + BubbleTea | 需额外实现 | 内置 | 中 | 大规模 / 商用 |

Python 在「必须加密」这一硬需求下综合最佳；macOS 自带 `python3`，无需额外运行时。TUI 选 Textual 而非纯 Rich——Rich 无法实现键盘导航和实时搜索。

## SSH 连接策略

**为何用系统 ssh 而非 paramiko：** 直接 shell out 到系统 `ssh`/`scp`，获得完整终端仿真（颜色、`htop`/`vim` 等 TUI 程序）、SSH agent 转发、对 `~/.ssh/config` 的尊重，且无需重造 SSH 协议。

**密码认证用 pty 而非 sshpass：** 用 Python 标准库 `pty` 消除 sshpass 依赖。实现（[`ssh.py`](../src/sshm/ssh.py)）处理三个阶段：监听 SSH 输出检测 `password:` 提示 → 注入密码并验证未被拒 → 认证后双向中继用户终端与 SSH 会话。关键约束：

- 认证前只监听 SSH 输出 fd，不监听 stdin（否则用户误按键会让 `select` 空转）。
- 远端 MOTD/banner 在认证期间缓冲，登录成功后一并刷出，避免空白屏。
- 密码提示检测 30 秒超时；超时则输出缓冲内容 + 诊断信息。
- 发出密码后短暂 peek（0.3s sleep + 0.5s select）判断是立即重提示（密码错）还是继续（认证成功）。

已知限制：仅支持 keyboard-interactive 且提示非标准的服务器会超时，错误信息会引导用户手动测试连通性。

## 加密方案

**单文件 vault：** salt 直接嵌在 vault 文件头。

```
vault.enc = Salt(16B) || IV(12B) || ciphertext(变长) || auth tag(16B)
主密码 --PBKDF2-SHA256(600k 轮)--> 256-bit AES 密钥
```

| 组件 | 细节 | 理由 |
|---|---|---|
| 加密 | AES-256-GCM | 带认证的加密——机密性 + 完整性 |
| KDF | PBKDF2-SHA256，600k 轮 | OWASP 2023 推荐下限 |
| Salt | 随机 16 字节，嵌在 vault | 防彩虹表；单文件 |
| IV | 随机 12 字节，每次加密新生成 | GCM 标准 nonce 长度 |
| 认证标签 | 16 字节（GCM 默认） | 检测任何篡改 |

**安全：** 密文离开主密码不可读；GCM 标签检测篡改；解密后数据仅存在于进程内存、退出即弃（Python 字符串无法可靠清零，对本地 CLI 可接受）。解出的 JSON 含 `version` 字段，版本号超出支持范围时拒绝解密。实现见 [`crypto.py`](../src/sshm/crypto.py)。

**配置格式（解密后的 JSON）：**

```json
{
  "version": 1,
  "servers": [
    {"name": "staging-db", "host": "10.0.0.50", "port": 2222, "user": "deploy",
     "auth_type": "password", "password": "...", "group": "staging", "notes": ""}
  ]
}
```

整个 JSON 加密进 `vault.enc`。`password` 字段存服务器明文密码——由 vault 级 AES-256-GCM 保护落盘，不做二次加密。字段校验（必填、端口范围、`auth_type` 取值、`~` 展开）在 `ServerConfig.__post_init__` 完成，见 [`vault.py`](../src/sshm/vault.py)。

## Vault 并发

多个 `sshm` 实例不能损坏 vault。写操作用 POSIX 建议锁：读用共享锁 `LOCK_SH`、写用独占锁 `LOCK_EX`，写后 `fsync`。实现见 [`vault.py`](../src/sshm/vault.py)。

## 会话缓存（Keychain）

主密码缓存进 macOS Keychain，带 TTL（固定 3600 秒）：

```
首次运行:   主密码 -> (vault.load 校验通过) -> 存 {password, expires_at} 进 Keychain
后续运行:   查 Keychain -> 未过期且能解 vault? 跳过提示. 失效? 清掉、重新提示.
sshm lock:  从 Keychain 删除
```

写入只发生在认证成功之后（CLI 的 `get_vault_password` 用 `vault.load` 校验通过后、TUI 的 `do_authenticate` 列出服务器成功后），所以误输的密码不会被缓存；缓存失效（密码已改）时会在下一次成功认证时自愈覆盖。

**为何缓存主密码而非派生 AES 密钥：** vault 每次操作都从「主密码 + vault 内 salt」现派生密钥，应用全程持有主密码——缓存主密码与现有架构一致、消费方零改动。同用户进程能免认证读 Keychain，故二者在本工具的本地威胁模型下等价：拿到派生密钥可直接解密 vault；拿到主密码 + vault 文件头里的 salt 同样能派生出来。安全说明与 SSH agent / GPG agent 的信任模型一致。实现见 [`session.py`](../src/sshm/session.py)。

## TUI 架构

TUI 基于 [Textual](https://github.com/Textualize/textual)，采用**多 Screen** 模型。`SSHManagerApp` 只做**协调者**——持有状态（vault、密码、servers 列表）并管理 Screen 栈，**自身没有 `BINDINGS`、没有 `compose`、没有状态栏**。所有快捷键绑定在各 Screen 上，每个 Screen 自己 `yield Footer()`——Footer 自动渲染「当前活动 Screen」的绑定，所以底部提示行始终随页面变化、且只有一行（不会重复）。

四个 Screen（[`tui.py`](../src/sshm/tui.py)）：

- `PasswordScreen` —— 主密码输入 / 重试。
- `MainScreen` —— 服务器列表 + 搜索（keystone）。
- `ServerForm` —— 添加 / 编辑服务器。
- `TransferForm` —— 上传 / 下载路径输入。

**关键设计（勿回归）：**

- `MainScreen.AUTO_FOCUS = ""`：故意为空，使焦点保持 `None`。这让本屏绑定直接生效，又避免未聚焦的 `DataTable` 用其 `enter→select_cursor` 吞掉回车。不要「改进」成聚焦表格。
- **退出绑定是 `app.quit` 而非裸 `quit`**：`action_quit` 定义在 App 上，Textual 不会从 Screen 命名空间上溯到 App 找方法，裸 `quit` 在 Screen 上会静默失效。其余主屏动作（`add_server` 等）能工作，是因为每个都在本屏有对应的 `action_*`。
- **搜索框是过滤的唯一真相源**：`_refresh_table()` 读搜索框当前值；渲染列表镜像到 `_filtered_servers`，`_get_selected_server` 据此映射 `cursor_row`（而非未过滤的 `app.servers`）。搜索框内 **Enter 提交**查询（保留过滤、焦点还给主屏），**Esc** 清空回到全量。

**退出契约**（`cli.run_tui` 按 `app.run()` 返回值分发）：`ServerConfig` → SSH 连接；`("transfer", server, mode, local, remote)` 五元组 → SCP 上传/下载；`None` → 落空。
