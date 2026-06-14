# 更新日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-06

首个可用版本。

### 新增

- **加密 vault**：AES-256-GCM + PBKDF2-SHA256（600k 轮），单文件 `~/.sshm/vault.enc`（salt/IV/密文/认证标签）。
- **CLI**（argparse）：`init` / `add` / `ls` / `connect`(=`ssh`) / `edit` / `rm` / `upload` / `download` / `password` / `lock` / `export`。
- **SSH 连接**：基于 pty，密钥与密码认证；密码认证无需 sshpass；自动接受首次 host key、ConnectTimeout、终端状态恢复。
- **SCP 文件传输**：上传 / 下载。
- **会话缓存**：派生 AES 密钥存 macOS Keychain，TTL 3600s；`sshm lock` 清除。
- **交互式 TUI**（Textual）：服务器列表、实时搜索、快捷键操作、内置添加/编辑/传输表单。
- **数据校验**：`ServerConfig` 必填/端口范围/认证方式校验 + `~` 展开；fcntl 文件锁防并发损坏。
- **安装脚本** `install.sh`（wrapper / 卸载）。

### 修复

- 错误密码显示友好提示而非堆栈；密码输入改用 Textual 原生组件（修复 getpass 卡死）。
- 表单：小窗口滚动、Enter 跳字段、Escape 取消、CSS `%` 字符导致的 ValueError。
- TUI：进入表单隐藏误导性 Footer；**主屏 `q` 退出**（`quit` → `app.quit`）；**搜索过滤后选中错位**与**搜索框焦点陷阱**。

### 重构

- TUI 从单 mount 迁移到**多 Screen 架构**：`PasswordScreen` / `MainScreen` / `ServerForm` / `TransferForm`，`SSHManagerApp` 退化为协调者；每屏自带 Footer+BINDINGS（消除重复提示行）。

[0.1.0]: https://github.com/USERNAME/sshm/releases/tag/v0.1.0
