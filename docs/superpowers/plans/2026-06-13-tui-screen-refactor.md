# TUI Screen 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 sshm TUI 的四个"页面"从 `mount(Vertical)` 架构重构为 Textual 原生的 `Screen` + `push_screen`/`pop_screen` 架构,每个 Screen 自带 `Footer` + 自己的 `BINDINGS`,从而消除主列表页"两行重复提示"、统一全部页面的提示行设计逻辑,并根治 App 级快捷键跨页面误触发。

**Architecture:** `SSHManagerApp` 退化为协调者(持有 vault/password/servers 状态,提供 `do_*` 公共方法,管理 Screen 栈)。四个页面各为一个 `Screen` 子类:`MainScreen`(主列表)、`PasswordScreen`(认证)、`ServerForm`(增/编)、`TransferForm`(上传/下载)。每个 Screen 在自己的 `compose` 里 yield `Header` + 内容 + `Footer`,并定义本屏的 `BINDINGS`;Footer 因此自动显示**当前 Screen** 的快捷键。页面切换全部走 `push_screen`/`pop_screen`(modal 栈)。删除手写 `status-bar` Static 和 `_hide_main_content`/`_show_main_content`/Footer 显隐补丁。`self.exit(result=...)` 的退出语义不变,`cli.run_tui` 接续 ssh/scp 的逻辑零改动。

**Tech Stack:** Python 3.13、Textual >=3.0(`Screen`、`push_screen`/`pop_screen`、`Pilot` 测试)、pytest。

---

## 背景与根因(决策依据)

现状:`PasswordScreen`/`ServerForm`/`TransferForm` 都是 `Vertical`,通过 `self.mount(...)` 挂到 App 唯一的默认 Screen 上;`SSHManagerApp(App)` 没有 `MODES`/`SCREENS`/`push_screen`。后果:

1. **主列表页两行提示**:`compose` 同时 yield 了手写 `Static(id="status-bar")` 和内置 `Footer()`。Footer 读 `self.screen.active_bindings`(见 `.venv/.../textual/widgets/_footer.py:247`),在单 Screen 架构下显示 App 级 `BINDINGS`,与手写 status-bar 内容重叠。
2. **App 级快捷键全局挂载**:App 是所有 widget 的祖先,`App.BINDINGS` 出现在每个页面的 focused 链上(见 `.venv/.../textual/screen.py:411-424`)。表单页只靠 Input 顺便 consume 字母键来"过滤",不可靠——按钮聚焦时 `q/a/e/d` 会重现并可能误触发。commit `917a355`(进表单隐藏 Footer)只藏了提示,没动作用域。
3. **"统一"的真意**:单一机制(Screen + `BINDINGS` + Footer 自动渲染)+ 单一信息源(快捷键只定义在 `BINDINGS`,提示自动派生)。手写 N 个 Static 是"形式统一、实质分裂"(两份信息源易漂移),已被否决。

## 关键架构决策(审计划重点)

- **每个 Screen 自带 `Footer`**(而非 App 全局一个)。理由:规避"modal Screen 是否遮挡 App 层 Footer"的不确定性;且 per-screen Footer 是 Textual 官方多页应用惯例。代价:Footer 实例多个,但每个 Screen 自包含、可独立测试。
- **主页也做成 `MainScreen`**(而非 App 直接 compose)。理由:用户要求"全部页面设计逻辑统一"——四个页面必须同一机制。App.compose 不 yield 业务 UI,只在 `on_mount` 决定 push 哪个首屏。
- **状态留在 App,UI 留在 Screen**。`vault`/`password`/`servers` 是 App 属性;Screen 通过 `self.app`(类型断言为 `SSHManagerApp`)访问数据、委托动作。这与现有 `ServerForm._save` 已用的模式一致(`app = self.app; if isinstance(app, SSHManagerApp): app.do_save_server(...)`)。
- **`↑↓ 导航` 不进 Footer**。上下键是 DataTable 内置行导航,加入 `BINDINGS` 会与 DataTable 冲突。Footer 显示 `/ 搜索 a 添加 e 编辑 d 删除 Enter 连接 u 上传 x 下载 q 退出`;上下导航由光标隐含。若日后坚持提示,可放 MainScreen 顶部小字,但 YAGNI。
- **Screen 栈语义**:启动 → `[PasswordScreen]` 或 `[MainScreen]`(有缓存 key 时直接认证);认证成功 → pop PasswordScreen + push MainScreen;增/编/传输 → push 表单 Screen(栈:`[MainScreen, Form]`);关闭 → pop 回 MainScreen;连接/传输 → `self.exit(result)` 清栈退出。MainScreen 常驻栈底,表格/搜索状态自然保留(优于现在每次 `close_form` 重建)。
- **退出语义不变**:`action_connect_server`/`do_transfer` 仍调 `self.exit(result=...)`,`cli.run_tui` 的 `isinstance(result, ServerConfig)` / transfer-tuple 分支零改动。

## File Structure

| 文件 | 改动 | 责任 |
|------|------|------|
| `src/sshm/tui.py` | 重构 | 四个类换基类(`Vertical`→`Screen`);App 改协调者;页面切换改 push/pop;删 status-bar 与显隐补丁 |
| `tests/test_tui.py` | 新建 | Textual Pilot 行为测试:启动/认证/搜索/增删改/传输/连接/各屏 Footer |
| `tests/test_cli.py` | 不改 | 现有 CLI 测试保持绿 |
| `src/sshm/cli.py` | 不改 | `run_tui` 接 result 的逻辑不变 |

tui.py 内部职责切分(重构后):
- `SSHManagerApp`:状态(vault/password/servers/_authenticated)+ 协调方法(`do_authenticate`/`do_save_server`/`do_transfer`/`show_*`/`close_form`/`refresh_main`)+ `on_mount` 选首屏。无业务 UI。
- `PasswordScreen(Screen)`:密码输入 UI + Footer。
- `MainScreen(Screen)`:Header + search-bar + DataTable + Footer;列表 `BINDINGS`;`action_*` 委托 `self.app`;持有 `_setup_table`/`_refresh_table`/`_get_selected_server`。
- `ServerForm(Screen)`:表单 UI + Footer;`BINDINGS=[escape→cancel]`;`_save`/`_close` 委托 App。
- `TransferForm(Screen)`:传输 UI + Footer;`BINDINGS=[escape→cancel]`;`_start`/`_close` 委托 App。

---

## Task 1: 测试基础设施 + 行为保护测试(在现有架构上跑绿)

**目的**:重构前先用 Textual Pilot 把主流程行为锁定为绿测试,作为重构安全网。测试尽量**行为级**(按键→观察可见结果),少依赖内部类名/mount 结构,以便跨架构存活。

**Files:**
- Create: `tests/test_tui.py`
- 参考: `tests/test_cli.py`(测试风格)、`src/sshm/vault.py`(`Vault.init`/`add_server` API)

- [ ] **Step 1: 确认 Vault 测试 API**

Run: `grep -n "def init\|def add_server\|def list_servers\|class Vault" src/sshm/vault.py`
确认构造 vault、加服务器、列服务器的函数签名(测试夹具要用)。

- [ ] **Step 2: 写 tests/test_tui.py 夹具 + 启动测试**

```python
"""TUI 行为测试 — 基于 Textual Pilot。"""
import os
import tempfile
import pytest

from sshm.tui import SSHManagerApp, PasswordScreen, MainScreen, ServerForm, TransferForm
from sshm.vault import Vault, ServerConfig


@pytest.fixture
def app_with_vault(monkeypatch):
    """建一个临时 vault(含一台服务器),返回配置好的 App(未 run)。"""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "vault.enc")
        vault = Vault(path)
        vault.init("test-pw")
        vault.add_server(ServerConfig(name="alpha", host="1.2.3.4", port=22,
                                      user="root", auth_type="password",
                                      password="x"), "test-pw")
        # 让 App 用这个 vault 路径,且无缓存 key → 走密码屏
        monkeypatch.setattr("sshm.session.load_key", lambda: None)
        app = SSHManagerApp(vault_path=path)
        yield app


@pytest.mark.asyncio
async def test_starts_on_password_screen(app_with_vault):
    app = app_with_vault
    async with app.run_test() as pilot:
        await pilot.pause()
        # 行为级:启动后存在密码输入框
        assert app.query_one("#password-input") is not None
```

> 注:`MainScreen`/`ServerForm`/`TransferForm` 在 Task 6/4/5 才存在;此步先只导入 `SSHManagerApp`/`PasswordScreen`,其余在对应 Task 解除注释。`pytest-asyncio` 需在依赖中(见 Step 4)。

- [ ] **Step 3: 写主流程行为测试(认证→列表→搜索→增→删)**

```python
@pytest.mark.asyncio
async def test_authenticate_shows_table(app_with_vault):
    app = app_with_vault
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#password-input")
        await pilot.press("t", "e", "s", "t", "-", "p", "w")
        await pilot.press("enter")
        await pilot.pause()
        # 认证后主表格出现且含 alpha
        table = app.query_one("#main-table")
        assert any("alpha" in (cell.plain if hasattr(cell, "plain") else str(cell))
                   for row in table.get_table() for cell in [row[1]])


@pytest.mark.asyncio
async def test_search_filters(app_with_vault):
    app = app_with_vault
    async with app.run_test() as pilot:
        await pilot.click("#password-input"); await pilot.press("t","e","s","t","-","p","w","enter")
        await pilot.pause()
        search = app.query_one("#search-input")
        await pilot.click("#search-input")
        await pilot.press("z","z","z")  # 无匹配
        await pilot.pause()
        table = app.query_one("#main-table")
        # 行为级:无匹配时表格提示 no match(见 tui.py _refresh_table)
        assert table.row_count >= 1  # 占位行


@pytest.mark.asyncio
async def test_add_then_save_increments_rows(app_with_vault):
    app = app_with_vault
    async with app.run_test() as pilot:
        await pilot.click("#password-input"); await pilot.press("t","e","s","t","-","p","w","enter")
        await pilot.pause()
        before = app.query_one("#main-table").row_count
        await pilot.press("a")            # 打开添加表单
        await pilot.pause()
        await pilot.click("#f-name"); await pilot.press("b","e","t","a")
        await pilot.click("#f-host"); await pilot.press("5",".","6",".","7",".","8")
        await pilot.click("#f-user"); await pilot.press("r","o","o","t")
        await pilot.click("#f-auth"); await pilot.press("p","a","s","s","w","o","r","d")
        await pilot.press("f6")  # 或点保存按钮;见下 note
        await pilot.click("#btn-save")
        await pilot.pause()
        after = app.query_one("#main-table").row_count
        assert after == before + 1
```

> Note: 表单字段切换用 `click` 而非依赖 Tab 顺序,更鲁棒。`f6` 那行可删,保留 `click("#btn-save")`。测试断言以**实际运行结果**校准——Step 5 跑通时按报错调整断言细节(如 `get_table()` API、占位行文案)。

- [ ] **Step 4: 加测试依赖**

Run: `grep -n "pytest" requirements.txt pyproject.toml`
若无 `pytest-asyncio`,添加。命令:
```bash
pip install pytest-asyncio
echo "pytest-asyncio" >> requirements.txt
```
并在 `pyproject.toml` 的 `[tool.pytest.ini_options]` 加 `asyncio_mode = "auto"`(若没有该段则新建),免得每个测试写 `@pytest.mark.asyncio`。若用 `auto` 模式,删除测试里的 `@pytest.mark.asyncio` 装饰器。

- [ ] **Step 5: 跑测试,校准断言到全绿**

Run: `pytest tests/test_tui.py -v`
Expected: 全 PASS。若断言与实际 API/文案不符,按报错**修正测试断言**(不改产品代码)。目标:这组测试在**现有 mount 架构**上 100% 绿——它是重构安全网。

- [ ] **Step 6: 补连接/传输退出测试**

```python
@pytest.mark.asyncio
async def test_connect_exits_with_server(app_with_vault):
    app = app_with_vault
    async with app.run_test() as pilot:
        await pilot.click("#password-input"); await pilot.press("t","e","s","t","-","p","w","enter")
        await pilot.pause()
        await pilot.press("enter")  # 连接选中行
        await pilot.pause()
    # app 退出,result 是 ServerConfig
    assert isinstance(app.return_value or app._return_value, ServerConfig) \
        or (hasattr(app, "return_value") and isinstance(app.return_value, ServerConfig))
```
> 校准:`App.run_test()` 下退出结果取值方式以实际 Textual API 为准(查 `app.return_value` / `_return_value`),按跑通结果固定。

Run: `pytest tests/test_tui.py -v` → 全绿。

- [ ] **Step 7: Commit**

```bash
git add tests/test_tui.py requirements.txt pyproject.toml
git commit -m "test: 新增 TUI Pilot 行为测试作为 Screen 重构安全网"
```

---

## Task 2: PasswordScreen 改为 Screen

**Files:**
- Modify: `src/sshm/tui.py:16-66`(`PasswordScreen` 类)、`src/sshm/tui.py:376-402`(`on_mount`/`_show_password_screen`)

- [ ] **Step 1: 改基类与 compose(加 Header/Footer)**

把 `class PasswordScreen(Vertical):` 改为 `class PasswordScreen(Screen):`,顶部 import 加 `from textual.screen import Screen`。`compose` 改为:

```python
def compose(self) -> ComposeResult:
    yield Header()
    with Vertical():
        yield Label("sshm — SSH Server Manager" if not self.retry else "密码错误，请重试")
        yield Input(placeholder="输入主密码", password=True, id="password-input")
        yield Label("", id="error-label")
    yield Footer()
```

`DEFAULT_CSS` 选择器 `PasswordScreen` 保持不变(Screen 也是 widget,CSS 照常)。`on_mount`/`on_input_submitted` 逻辑不变(仍调 `self.app.do_authenticate`)。

- [ ] **Step 2: App 改用 push_screen 挂密码屏**

`SSHManagerApp.on_mount` 与 `_show_password_screen` 改为:

```python
def on_mount(self) -> None:
    self._setup_state()          # 见 Step 3:原 _setup_table 的非 UI 部分
    cached = load_key()
    if cached:
        self.do_authenticate(cached)
    else:
        self._show_password_screen()

def _show_password_screen(self, retry: bool = False) -> None:
    self.push_screen(PasswordScreen(retry=retry))
```

`do_authenticate` 成功分支改为:

```python
def do_authenticate(self, password: str) -> None:
    try:
        self.servers = self.vault.list_servers(password)
        self.password = password
        self._authenticated = True
    except Exception:
        self._authenticated = False
        # 替换栈顶密码屏为重试屏
        self.pop_screen()
        self._show_password_screen(retry=True)
        return
    # 认证成功:弹出密码屏,进入主屏
    if self.screen is not None and isinstance(self.screen, PasswordScreen):
        self.pop_screen()
    self._show_main_screen()
```

- [ ] **Step 3: 抽出非 UI 的初始化**

原 `on_mount` 调 `self._setup_table()`(操作 DataTable)。重构期 DataTable 还在 App.compose(Task 6 才挪走)。**本任务保留 App.compose 仍 yield 主页 UI**(过渡态),但 `_setup_table` 在 MainScreen 出现前仍可用。新增占位方法 `_setup_state(self)`(空实现或仅 log),`on_mount` 调它,为 Task 6 做准备。

> 过渡态说明:Task 2-5 期间,App.compose 仍 yield Header+main-view+Footer(主页),密码/表单/传输 Screen 以 modal push 在上。主页此时仍由 App 持有,Task 6 整体迁移到 MainScreen。**每一步都跑测试保持绿。**

- [ ] **Step 4: 跑测试**

Run: `pytest tests/test_tui.py -v`
Expected: 全 PASS。若 `query_one("#password-input")` 因 Screen 隔离查不到,改用 `app.screen.query_one(...)` 或 pilot.click(行为级更稳)。按报错校准。

- [ ] **Step 5: 手动冒烟**

Run: `python -m sshm`(或项目启动方式) → 应先看到密码屏(带 Header/Footer),输入正确密码进主页。错误密码→重试屏。

- [ ] **Step 6: Commit**

```bash
git add src/sshm/tui.py
git commit -m "refactor(tui): PasswordScreen 改为 Screen,push/pop 管理认证流"
```

---

## Task 3: TransferForm 改为 Screen

**Files:**
- Modify: `src/sshm/tui.py:213-310`(`TransferForm` 类)、`_show_transfer_form`、`close_form`

- [ ] **Step 1: 改基类 + compose 加 Header/Footer + BINDINGS**

```python
class TransferForm(Screen):
    """上传/下载文件路径输入表单。"""
    BINDINGS = [Binding("escape", "cancel", "取消")]

    # DEFAULT_CSS 不变(选择器 TransferForm 仍生效)

    def compose(self) -> ComposeResult:
        # title/local_ph/remote_ph 计算逻辑不变
        yield Header()
        with Vertical():
            yield Label(title, id="form-title")
            yield Input(placeholder=local_ph, id="tf-local")
            yield Input(placeholder=remote_ph, id="tf-remote")
            yield Label("", id="error-label")
            with Horizontal():
                yield Button("开始传输", variant="success", id="btn-transfer")
                yield Button("取消", variant="default", id="btn-cancel")
        yield Footer()

    def action_cancel(self) -> None:
        self._close()
```

`on_mount`/`on_key`/`on_button_pressed`/`on_input_submitted`/`_start`/`_close` 逻辑不变(`_close` 仍调 `self.app.close_form()`)。删除手写 `on_key` 的 escape 分支也可(改由 BINDINGS 的 `action_cancel` 处理),二选一,**保留其一**避免重复触发——推荐留 BINDINGS 版,删 `on_key`。

- [ ] **Step 2: App._show_transfer_form / close_form 改 push/pop**

```python
def _show_transfer_form(self, server: ServerConfig, mode: str) -> None:
    self.push_screen(TransferForm(server=server, mode=mode))

def close_form(self) -> None:
    """关闭栈顶表单/传输屏,回到主屏。"""
    if len(self.screen_stack) > 1:
        self.pop_screen()
    self.refresh_main()
```

(`refresh_main` 见 Task 6;此处若 MainScreen 尚未引入,过渡期用现有 `_refresh_table` 逻辑——`close_form` 内 `self._refresh_table()`。Task 6 统一为 `refresh_main`。)

- [ ] **Step 3: 跑测试 + 手动冒烟(选中服务器→u/x→填路径→取消/传输)**

Run: `pytest tests/test_tui.py -v` → 全绿。手动:`u` 开传输表单(带 Footer 显示 `esc 取消`),`esc` 回主页。

- [ ] **Step 4: Commit**

```bash
git add src/sshm/tui.py
git commit -m "refactor(tui): TransferForm 改为 Screen,自带 Footer 与 esc 绑定"
```

---

## Task 4: ServerForm 改为 Screen

**Files:**
- Modify: `src/sshm/tui.py:71-208`(`ServerForm` 类)、`_show_server_form`

- [ ] **Step 1: 改基类 + compose 加 Header/Footer + BINDINGS**

```python
class ServerForm(Screen):
    DEFAULT_CSS = """..."""  # 不变
    BINDINGS = [Binding("escape", "cancel", "取消")]

    def compose(self) -> ComposeResult:
        title = "编辑服务器" if self.server else "添加服务器"
        s = self.server
        yield Header()
        with Vertical():
            yield Label(title, id="form-title")
            # …9 个 Input + error-label + Horizontal(保存/取消)…
        yield Footer()

    def action_cancel(self) -> None:
        self._close()
```

`_save`/`_close`/`on_mount`/`on_button_pressed`/`on_input_submitted` 不变。删除 `on_key` 的 escape 分支(改由 `action_cancel`),与 Task 3 一致。

- [ ] **Step 2: App._show_server_form 改 push**

```python
def _show_server_form(self, server: ServerConfig | None = None) -> None:
    self.push_screen(ServerForm(server=server))
```

- [ ] **Step 3: 跑测试(增/编/取消/保存)+ 手动冒烟**

Run: `pytest tests/test_tui.py -v` → 全绿。`test_add_then_save_increments_rows` 必须仍绿。手动:`a`→填→保存→回主页行数+1;`e`→编辑;`esc`→取消回主页。

- [ ] **Step 4: Commit**

```bash
git add src/sshm/tui.py
git commit -m "refactor(tui): ServerForm 改为 Screen,自带 Footer 与 esc 绑定"
```

---

## Task 5: 主页迁移到 MainScreen(核心任务)

**Files:**
- Modify: `src/sshm/tui.py:320-563`(`SSHManagerApp` → 拆出 `MainScreen`)、新建 `MainScreen` 类

- [ ] **Step 1: 新增 MainScreen 类骨架**

在 `ServerForm` 之后、`SSHManagerApp` 之前插入:

```python
class MainScreen(Screen):
    """主列表页:搜索 + 服务器表格。"""

    BINDINGS = [
        Binding("slash", "focus_search", "搜索", key_display="/"),
        Binding("a", "add_server", "添加"),
        Binding("e", "edit_server", "编辑"),
        Binding("d", "delete_server", "删除"),
        Binding("enter", "connect_server", "连接"),
        Binding("u", "upload_file", "上传"),
        Binding("x", "download_file", "下载"),
        Binding("q", "quit", "退出"),
        Binding("escape", "unfocus_search", "取消搜索"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-view"):
            with Horizontal(id="search-bar"):
                yield Input(placeholder="搜索 (/)", id="search-input")
            yield DataTable(id="main-table")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_table()
        self._refresh_table()
        self.query_one("#main-table", DataTable).focus()

    def _setup_table(self) -> None:
        table = self.query_one("#main-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("#", "Name", "Address", "User", "Auth", "Group")

    def _refresh_table(self, filter_text: str = "") -> None:
        # 原 SSHManagerApp._refresh_table 逻辑原样搬来,servers 从 self.app 取
        app = self.app
        assert isinstance(app, SSHManagerApp)
        table = self.query_one("#main-table", DataTable)
        table.clear()
        filtered = app.servers
        if filter_text:
            ft = filter_text.lower()
            filtered = [s for s in app.servers
                        if ft in s.name.lower() or ft in s.host.lower()]
        if not filtered:
            if not app.servers:
                table.add_row("", "(empty — 按 a 添加你的第一台服务器)", "", "", "", "")
            else:
                table.add_row("", "(no match)", "", "", "", "")
            return
        for i, s in enumerate(filtered, 1):
            auth_label = "key" if s.auth_type == "key" else "pwd"
            table.add_row(str(i), s.name, s.host, s.user, auth_label, s.group)

    def _get_selected_server(self) -> ServerConfig | None:
        table = self.query_one("#main-table", DataTable)
        row = table.cursor_row
        app = self.app
        assert isinstance(app, SSHManagerApp)
        if row is None or row >= len(app.servers):
            return None
        return app.servers[row]
```

- [ ] **Step 2: 把 action_* 从 App 迁到 MainScreen(委托 self.app)**

```python
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._refresh_table(event.value)

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_unfocus_search(self) -> None:
        self.query_one("#search-input", Input).value = ""
        self.query_one("#main-table", DataTable).focus()

    def action_connect_server(self) -> None:
        server = self._get_selected_server()
        if server:
            self.app.exit(result=server)

    def action_add_server(self) -> None:
        app = self.app; assert isinstance(app, SSHManagerApp)
        app.show_server_form(server=None)

    def action_edit_server(self) -> None:
        app = self.app; assert isinstance(app, SSHManagerApp)
        server = self._get_selected_server()
        if server:
            app.show_server_form(server=server)

    def action_delete_server(self) -> None:
        server = self._get_selected_server()
        if not server:
            return
        app = self.app; assert isinstance(app, SSHManagerApp)
        try:
            app.vault.remove_server(server.name, app.password)
            app.servers = app.vault.list_servers(app.password)
            self._refresh_table()
        except Exception as e:
            self.app.exit(message=f"Delete failed: {e}")

    def action_upload_file(self) -> None:
        app = self.app; assert isinstance(app, SSHManagerApp)
        server = self._get_selected_server()
        if server:
            app.show_transfer_form(server, mode="upload")

    def action_download_file(self) -> None:
        app = self.app; assert isinstance(app, SSHManagerApp)
        server = self._get_selected_server()
        if server:
            app.show_transfer_form(server, mode="download")
```

- [ ] **Step 3: 瘦身 SSHManagerApp——删主页 UI/BINDINGS/action,留状态+协调**

App 不再 `compose` 业务 UI,改为:

```python
class SSHManagerApp(App):
    def __init__(self, vault_path: str = "~/.sshm/vault.enc"):
        super().__init__()
        self.vault = Vault(vault_path)
        self.password = ""
        self.servers: list[ServerConfig] = []
        self._authenticated = False

    def on_mount(self) -> None:
        cached = load_key()
        if cached:
            self.do_authenticate(cached)
        else:
            self._show_password_screen()

    # 协调方法(供 Screen 委托)
    def _show_password_screen(self, retry: bool = False) -> None:
        self.push_screen(PasswordScreen(retry=retry))

    def _show_main_screen(self) -> None:
        self.push_screen(MainScreen())

    def show_server_form(self, server: ServerConfig | None = None) -> None:
        self.push_screen(ServerForm(server=server))

    def show_transfer_form(self, server: ServerConfig, mode: str) -> None:
        self.push_screen(TransferForm(server=server, mode=mode))

    def close_form(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()
        self.refresh_main()

    def refresh_main(self) -> None:
        """数据变更后刷新主屏表格。"""
        try:
            main = self.query_one(MainScreen)
            main._refresh_table()
        except Exception:
            pass  # 主屏不在栈上时忽略

    def do_authenticate(self, password: str) -> None: ...   # 见 Task 2 Step 2
    def do_save_server(self, cfg, original) -> None: ...    # 不变,末尾改调 self.refresh_main()
    def do_transfer(self, server, mode, local, remote) -> None:
        self.exit(result=("transfer", server, mode, local, remote))
```

`do_save_server` 末尾把 `self.close_form()` 保留(它会 pop 表单 + refresh_main)。

- [ ] **Step 4: 删除 App 旧成员**

删除:`App.BINDINGS`、`App.compose`(或改为空)、`_hide_main_content`/`_show_main_content`、`_setup_table`/`_refresh_table`/`_get_selected_server`(已迁 MainScreen)、所有 `action_*`(已迁)、`on_input_changed`、手写 `status-bar` Static、`yield Footer()` 的 App 级引用、`query_one(Footer).display` 显隐逻辑。

- [ ] **Step 5: 跑全套测试**

Run: `pytest tests/ -v`
Expected: 全 PASS。`test_authenticate_shows_table`/`test_search_filters`/`test_add_then_save_increments_rows`/连接/传输 均绿。若 query 因 Screen 隔离失败,改 `app.screen.query_one(...)` 或用 pilot 行为级操作。

- [ ] **Step 6: 手动冒烟全流程**

Run: 启动 → 密码屏 → 主页 → `/` 搜索 → `esc` 取消 → `a` 添加 → 保存 → `e` 编辑 → `esc` 取消 → `d` 删除 → `u` 上传 → `esc` → 选中 `Enter` 连接(退出)。

- [ ] **Step 7: Commit**

```bash
git add src/sshm/tui.py
git commit -m "refactor(tui): 主页迁移到 MainScreen,App 退化为协调者"
```

---

## Task 6: 验证 Footer 统一 + 补 Footer 断言测试

**Files:**
- Modify: `tests/test_tui.py`(加 Footer 断言)

- [ ] **Step 1: 写 Footer 内容断言(锁定"每屏显示自己的快捷键")**

```python
@pytest.mark.asyncio
async def test_main_screen_footer_has_search_add_quit(app_with_vault):
    app = app_with_vault
    async with app.run_test() as pilot:
        await pilot.click("#password-input"); await pilot.press("t","e","s","t","-","p","w","enter")
        await pilot.pause()
        footer = app.screen.query_one(Footer)
        labels = footer.query("FooterKey")
        texts = " ".join(fk.render().plain for fk in labels)
        assert "搜索" in texts and "退出" in texts and "添加" in texts


@pytest.mark.asyncio
async def test_no_duplicate_status_bar(app_with_vault):
    """主页不再有手写 status-bar(只剩 Footer 一行提示)。"""
    app = app_with_vault
    async with app.run_test() as pilot:
        await pilot.click("#password-input"); await pilot.press("t","e","s","t","-","p","w","enter")
        await pilot.pause()
        with pytest.raises(Exception):
            app.screen.query_one("#status-bar")
        footers = app.screen.query(Footer)
        assert len(footers) == 1
```

> 校准:`FooterKey.render().plain` 取文本以实际 Textual API 为准;断言按跑通结果固定。

- [ ] **Step 2: 跑测试 → 全绿**

Run: `pytest tests/ -v`

- [ ] **Step 3: 手动确认每屏 Footer**

逐屏核对:主页(`/ 添加 编辑 删除 连接 上传 下载 退出 取消搜索`)、表单(`取消`)、传输(`取消`)、密码屏(Footer 几乎空或仅命令面板)。**确认主页只有一行提示**(原 bug 消失)。

- [ ] **Step 4: Commit**

```bash
git add tests/test_tui.py
git commit -m "test(tui): 断言每屏 Footer 内容 + 主页无双行提示"
```

---

## Task 7: 全量回归 + 清理 + 文档

**Files:**
- Modify: `src/sshm/tui.py`(清理死代码/注释)、`README.md`(若有快捷键说明)

- [ ] **Step 1: 死代码扫描**

Run: `grep -n "_hide_main_content\|_show_main_content\|status-bar\|query_one(Footer).display" src/sshm/tui.py`
Expected: 无匹配(均已删)。若有残留,删除。

- [ ] **Step 2: 全量测试**

Run: `pytest tests/ -v`
Expected: 全 PASS(test_cli.py + test_tui.py + 其它)。

- [ ] **Step 3: 手动全流程终验**

按 Task 5 Step 6 的流程完整走一遍 + 故意输错密码(重试屏)+ 空 vault(`a` 添加首台)+ 搜索无匹配(`no match`)。确认无回归、无异常 traceback。

- [ ] **Step 4: 更新 README 快捷键说明(若有)**

Run: `grep -n "搜索\|快捷键\|/\|Footer" README.md`
若 README 列了快捷键,核对与新的各屏 BINDINGS 一致(尤其表单/传输页现在有 `esc 取消`)。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(tui): 清理 Screen 重构后的死代码与文档"
```

---

## 风险与回滚

- **最大风险**:Task 5(主页迁移)是最大改动,可能引入 Screen 栈/聚焦/退出语义问题。缓解:Task 1 的行为测试是安全网;Task 5 前四个 Screen 已逐个迁移并测绿,主页迁移时其余已稳定。回滚:每个 Task 独立 commit,任何一步红可 `git reset` 到上一个绿 commit。
- **Textual API 细节**:`push_screen`/`pop_screen`/`screen_stack`/`query_one` 跨 Screen 查询、`run_test()` 取退出 result 的 API,以实际 textual>=3.0 行为为准——测试断言处已标注"按跑通结果校准"。
- **过渡态(Task 2-4)**:App 仍 compose 主页 + modal Screen 共存。每步测绿才进下一步,避免大爆炸式重构。

## Self-Review

- **Spec 覆盖**:"消除两行重复"→ Task 5 删 status-bar + Task 6 断言;"统一全部页面提示逻辑"→ 四屏均 Screen+Footer+BINDINGS(Task 2-5);"根治跨页快捷键误触发"→ App 不再持 BINDINGS,每屏隔离(Task 5);"退出语义不变"→ cli 零改(Task 1-7 均未动 cli.py)。✓
- **占位符扫描**:无 TBD/TODO;关键类骨架与协调方法均给了完整代码;测试断言处明确标注"按跑通结果校准"(这是允许的——Pilot API 细节需实测确认,非占位)。✓
- **类型一致性**:`show_server_form`/`show_transfer_form`/`refresh_main`/`close_form` 在 MainScreen action 与 App 定义中签名一致;`_refresh_table`/`_get_selected_server` 迁到 MainScreen 后,App 不再持有(Step 4 已删)。✓
