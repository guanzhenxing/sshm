# 更新日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 修复

- **密钥认证 SSH 会话盲打**：`_ssh_with_key` 用 `subprocess` 捕获 stdout/stderr（0.2.0 为显示错误原因引入），会话输出全程被吞、成功退出时直接丢弃——用户只能盲打。密钥与密码认证统一走 pty 中继（`ssh.pty_connect`）：输出实时可见、加密私钥 passphrase 可输入、host key 变更自动清 key 重试；SCP 复用同一实现（密钥认证的 scp 进度可见、passphrase 不再挂死）。
- **退出码修正**：pty 路径返回 waitpid 裸状态码（如 768），`sys.exit` 截断后成 0——连接失败被脚本当成成功。改为 `waitstatus_to_exitcode`。
- **vault 不存在时死循环**：`get_vault_password` 把 `FileNotFoundError` 也当成「密码错误」无限重试（非 tty 下则是裸堆栈）。现在所有命令前置 `sshm init` 指引并退出码 1。
- **TUI 表单非法端口崩溃**：`int(port_str)` 未捕获，输入非数字直接让 Textual 崩溃。现表单内提示、应用存活。
- **CLI add/edit 裸异常**：非法端口、非法认证方式、重名等校验错误此前以 traceback 砸出；现友好提示 + 退出码 1。
- **TUI 编辑丢数据**：编辑此前用 remove+add 实现——条目被挪到列表末尾、`last_connected` 被清空。改用 `vault.edit_server` 原位更新。
- **TUI 行号与 CLI 编号错位**：分组重排展示顺序后按展示顺序重新编号，`#3` 与 `sshm connect 3` 可能指向不同机器。行号改为 vault 原始顺序。
- **终端恢复误清 ISIG**：`_restore_terminal` 在 lflag 上清 `OPOST`（属 oflag 的位），macOS 上实际关掉 Ctrl-C 信号生成；且在正确恢复之后执行、反而破坏恢复。删除该兜底。
- **vault 并发丢更新**：读-改-写此前 load（共享锁）与 save（独占锁）两次加锁，窗口内并发实例后写覆盖先写。`_mutate` 单把排他锁内完成整个事务。
- **stdin EOF 卡死**：pty 中继在 stdin 读到 EOF 时直接 break 去 `waitpid`——macOS 上 pty master 未读空前子进程无法完成退出，子进程会卡死在 exiting 状态、`waitpid` 永久阻塞（`sshm connect x </dev/null` 即可复现）。现在 EOF 只停止监听输入，中继继续到子进程退出；退出后及时关闭 master fd。

### 变更

- **vault 强制 name 唯一**：`add_server` 拒绝重名、`edit_server` 拒绝改名撞名（与导入去重的业务键一致）。
- **TUI 重复目标两步确认**：新增同 host:port:user 的服务器，首次提交只警告（「再按一次保存继续添加」），再次提交才落盘——与文案一致，用户真正有选择。
- **每条命令省一次 PBKDF2**：`vault.load` 按（密码 + 文件 stat）缓存解密结果，文件一变即失效；一条命令少约 0.3-0.5s。
- **去重**：时间格式化收敛到 `sshm.format.format_last_connected`；名称/序号查找收敛到 `vault.find_server`；`session.store_password` 删除无效的 `input=` 传参（security 经 `-w` argv 传值，已在注释说明可见性权衡）。

## [0.2.0] - 2026-06-15

### 新增

- **主屏列表按分组显示 + 备注列**：服务器列表按 `group` 字段分组，始终显示分组标题行（`── 组名 (N) ──`，空组标"未分组"）；方向键自动跳过分组标题行。列新增 `Notes`（备注）。
- **删除确认对话框**：TUI 按 `d` 弹出 `ConfirmScreen`（"确定删除「xxx」？" → 确认/取消），防止误操作。
- **install.sh PATH 检测**：安装后检测 `~/.local/bin` 是否在 PATH，不在则打印配置指引。

### 修复

- **TUI 列表编号与 CLI 一致**：列表保持 vault 原始顺序（不再按字母重排），`#1` `#2` 与 `sshm connect 3` 一致。
- **install.sh 安装路径**：默认安装到 `~/.local/bin`（无需 sudo）；sudo 运行时安装到 `/usr/local`。

### 文档

- README / usage.md / architecture.md 同步到当前架构（Screen 列表、列头、分组、安装路径）。

## [0.1.5] - 2026-06-15

### 新增

- **主屏列表按分组显示 + 备注列**：服务器列表按 `group` 字段分组（多分组时显示 `── 组名 (N) ──` 标题行，空组标"未分组"；单分组保持扁平）；方向键导航自动跳过分组标题行。列表新增 `Notes`（备注）列，原 `Group` 列由分组标题替代不再重复显示。

## [0.1.4] - 2026-06-15

### 修复

- **主屏无法选中/连接服务器**：进主屏默认选中第一台、底部有 `enter` 提示，但①方向键选不了别的服务器（`focus=None` 时方向键不被处理）；②鼠标点击后能选了，底部 `enter` 提示却消失、回车无效（点击让 DataTable 获得焦点，Footer 改显表格绑定、且 DataTable 的 `enter→select_cursor` 吞掉回车）。修复：DataTable 设 `can_focus=False`（点击只移动光标、不抢焦点，Footer 提示不再消失、回车由主屏处理）；MainScreen 加 `up/down` 绑定支持键盘导航。回车现在连接的是实际选中项。

## [0.1.3] - 2026-06-15

### 修复

- **导入表单「取消」按钮被裁**：ImportForm 的 4 个按钮（跳过/覆盖/重命名/取消）在 `width:70` 容器里总宽超出按钮行，"取消"被挤过右边框、终端稍窄即显示不全。根因是 Textual Button 默认 `min-width:16`；给按钮设 `width:13` + `min-width:0` 收窄，4 个均落在行内。

## [0.1.2] - 2026-06-14

### 新增

- **服务器列表导入/导出**：`sshm export`（明文 JSON 自描述信封，可选 `--encrypt` 用独立密码二次 AES-256-GCM 加密）/ `sshm import <file>`（三策略 `--skip`(默认) / `--overwrite` / `--rename`、`--dry-run`、stdin `-`）；TUI 主屏 `o` 导出 / `i` 导入。原子导入（任一条目非法则整体中止、不写半截数据），并兼容旧版裸 JSON 数组。覆盖备份/恢复、机器迁移、批量编辑、多机同步场景。

## [0.1.1] - 2026-06-14

### 修复

- **独立二进制冷启动慢**：`install.sh pyinstaller` 由 `--onefile` 改为 `--onedir`。onefile 每次启动把 ~29MB 解压到临时目录，实测冷启动 ~9s；onedir 把库摊在磁盘上，启动与 wrapper 持平（~70ms）。安装形态从单文件变为 bundle 目录 + 软链（`/usr/local/lib/sshm` + `/usr/local/bin/sshm`），`uninstall` 同步清理 bundle。

## [0.1.0] - 2026-06

首个可用版本。

### 新增

- **加密 vault**：AES-256-GCM + PBKDF2-SHA256（600k 轮），单文件 `~/.sshm/vault.enc`（salt/IV/密文/认证标签）。
- **CLI**（argparse）：`init` / `add` / `ls` / `connect`(=`ssh`) / `edit` / `rm` / `upload` / `download` / `password` / `lock` / `export`。
- **SSH 连接**：基于 pty，密钥与密码认证；密码认证无需 sshpass；自动接受首次 host key、ConnectTimeout、终端状态恢复。
- **SCP 文件传输**：上传 / 下载。
- **会话缓存**：主密码存 macOS Keychain，TTL 3600s；`sshm lock` 清除。
- **交互式 TUI**（Textual）：服务器列表、实时搜索、快捷键操作、内置添加/编辑/传输表单。
- **数据校验**：`ServerConfig` 必填/端口范围/认证方式校验 + `~` 展开；fcntl 文件锁防并发损坏。
- **安装脚本** `install.sh`（wrapper / pyinstaller / 卸载）。
- **版本管理**：`sshm --version`、TUI 主页面显示版本号；版本号单一来源 `__version__`（pyproject 以 dynamic 读取）。

### 修复

- 错误密码显示友好提示而非堆栈；密码输入改用 Textual 原生组件（修复 getpass 卡死）。
- 表单：小窗口滚动、Enter 跳字段、Escape 取消、CSS `%` 字符导致的 ValueError。
- TUI：进入表单隐藏误导性 Footer；**主屏 `q` 退出**（`quit` → `app.quit`）；**搜索过滤后选中错位**与**搜索框焦点陷阱**。
- **会话缓存写入路径缺失**：`session.store_*` 在生产代码中从未被调用 → "首次解锁后免输主密码" 实际从未生效，`--no-cache` 与默认行为无异、`sshm lock` 形同空操作。现于认证成功（`vault.load` 校验通过）后写入缓存；并把 session API 与文档从误导性的"派生密钥"正名为"主密码"（与两个消费方的实际行为一致）。

### 重构

- TUI 从单 mount 迁移到**多 Screen 架构**：`PasswordScreen` / `MainScreen` / `ServerForm` / `TransferForm`，`SSHManagerApp` 退化为协调者；每屏自带 Footer+BINDINGS（消除重复提示行）。

[0.2.0]: https://github.com/guanzhenxing/sshm/releases/tag/v0.2.0
[0.1.5]: https://github.com/guanzhenxing/sshm/releases/tag/v0.1.5
[0.1.4]: https://github.com/guanzhenxing/sshm/releases/tag/v0.1.4
[0.1.3]: https://github.com/guanzhenxing/sshm/releases/tag/v0.1.3
[0.1.2]: https://github.com/guanzhenxing/sshm/releases/tag/v0.1.2
[0.1.1]: https://github.com/guanzhenxing/sshm/releases/tag/v0.1.1
[0.1.0]: https://github.com/guanzhenxing/sshm/releases/tag/v0.1.0
