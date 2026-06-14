# 安全策略

sshm 在本地存储**加密的** SSH 凭据（AES-256-GCM，密钥由主密码经 PBKDF2 派生），
派生密钥可缓存于 macOS Keychain。凭据安全是本项目的核心，欢迎安全研究者协助加固。

## 支持的版本

只对最新发布版本提供安全更新（见 [CHANGELOG](CHANGELOG.md)）。

## 报告漏洞

如果你发现安全漏洞，请**不要**开公开 Issue、不要发 Pull Request。

请通过 GitHub 的私密安全公告上报：

👉 **[Report a vulnerability](https://github.com/guanzhenxing/sshm/security/advisories/new)**

请在报告中说明：

- 受影响版本与复现步骤；
- 影响范围（本地提权 / 凭据泄露 / 加密绕过等）；
- 可能的修复方向（可选）。

## 响应

- 收到报告后 **48 小时内**确认；
- 评估后与上报人协调披露时间线；
- 修复发布后在 CHANGELOG 与 GitHub Security Advisories 致谢（除非你希望匿名）。

## 已知信任模型（非漏洞）

以下行为是**有意设计**，不属于漏洞：

- **Keychain 会话缓存**：缓存的派生 AES 密钥可被**同一 macOS 用户**下的进程读取。
  这是便利性与安全性的权衡——若你的用户账户已被攻陷，缓存也会被攻陷。需要更高保证时，
  用 `sshm lock` 清除缓存，或以 `--no-cache` 运行（每次都输入主密码）。
- **`sshm export`** 会以**明文 JSON** 打印所有凭据。若终端输出正被记录
  （`script(1)`、tmux logging 等），明文密码可能落盘。

详见 [架构与设计 · 加密方案](docs/architecture.md)。
