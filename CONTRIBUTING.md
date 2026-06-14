# 贡献指南

感谢参与 sshm！本文档说明如何搭建开发环境、跑测试、提交改动。

## 开发环境

```bash
git clone <repo> && cd sshm
pip install -e ".[dev]"      # 可编辑安装 + 开发依赖（pytest、pytest-asyncio）
```

要求 macOS、Python 3.10+、系统 `ssh`/`scp`（Keychain 缓存依赖 macOS 的 `security` CLI）。

## 跑测试

```bash
pytest                       # 全部（59 个）
pytest tests/test_tui.py -v  # TUI 行为测试（Textual Pilot）
pytest -k search             # 按名筛选
```

测试要点：

- TUI 测试用 Textual Pilot，`run_test(size=(80, 50))`（大尺寸保证表单控件落在可见区）。
- 认证后主表格焦点为 `None`、`cursor_row=0`；测试里**不要**给 DataTable focus（它会吞掉 `enter`）。
- 用 `app.screen_stack` 找 `MainScreen`，而非 `app.query_one`（后者只看活动 screen）。

## 修 bug 的流程（TDD）

1. 先写一个**失败测试**复现 bug，跑一次确认它按预期失败。
2. 写最小修复让测试通过。
3. 跑全量，确保不回归。
4. 提交。详见 [CLAUDE.md](CLAUDE.md) 的「Critical TUI gotchas」，避免踩已知坑。

## 提交规范

Conventional Commits，中文描述：

- `feat:` 新功能 · `fix:` 修 bug · `refactor:` 重构 · `test:` 测试 · `docs:` 文档 · `chore:` 杂项
- 可加作用域，如 `feat(tui):`、`fix(ssh):`。

## 分支

在 feature 分支开发，fast-forward 合入 `main`（保持线性历史）。

## 手动冒烟清单（测试覆盖不到的）

自动化测试不连真实主机，发布前手动验证：

- 真实**密钥认证** SSH 连接：颜色、交互命令（`htop`/`vim`）、`~/.ssh/config` 生效。
- 真实**密码认证** SSH 连接：pty 注入、`Ctrl+C` 中断、窗口缩放（SIGWINCH）透传。
- **错误密码**：检测到重提示，终端恢复正常。
- **keyboard-interactive** 服务器：30s 超时 + 诊断信息。
- **并发写 vault**：两个终端同时操作不损坏数据。
- SCP 上传/下载文件内容一致。

## 相关文档

- [架构与设计](docs/architecture.md)
- [CLAUDE.md](CLAUDE.md)（项目事实与坑）
