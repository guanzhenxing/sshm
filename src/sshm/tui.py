"""交互式 TUI — 基于 Textual。"""

from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Label, Button

from sshm.vault import Vault, ServerConfig
from sshm.session import load_key


# ── 密码输入界面 ──────────────────────────────────────

class PasswordScreen(Screen):

    DEFAULT_CSS = """
    PasswordScreen {
        align: center middle;
        height: 100%;
        width: 100%;
    }
    PasswordScreen Vertical {
        width: 60;
        height: auto;
        padding: 2 4;
        border: thick $accent;
    }
    PasswordScreen Label {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }
    PasswordScreen #password-input {
        width: 100%;
        margin-bottom: 1;
    }
    PasswordScreen #error-label {
        color: $error;
        text-align: center;
    }
    """

    def __init__(self, retry: bool = False):
        super().__init__()
        self.retry = retry

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label("sshm — SSH Server Manager" if not self.retry else "密码错误，请重试")
            yield Input(placeholder="输入主密码", password=True, id="password-input")
            yield Label("", id="error-label")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#password-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "password-input":
            password = event.value
            if not password:
                self.query_one("#error-label", Label).update("密码不能为空")
                return
            app = self.app
            if isinstance(app, SSHManagerApp):
                app.do_authenticate(password)


# ── 服务器添加/编辑表单 ────────────────────────────────

class ServerForm(Screen):

    BINDINGS = [
        Binding("escape", "cancel", "取消"),
    ]

    DEFAULT_CSS = """
    ServerForm {
        align: center middle;
        height: 100%;
        width: 100%;
    }
    ServerForm Vertical {
        width: 70;
        max-height: 80vh;
        padding: 1 4;
        border: thick $accent;
        overflow-y: auto;
    }
    ServerForm Label {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }
    ServerForm Input {
        width: 100%;
        margin-bottom: 1;
    }
    ServerForm #error-label {
        color: $error;
        text-align: center;
        margin-bottom: 1;
    }
    ServerForm Horizontal {
        width: 100%;
        height: auto;
        margin-top: 1;
    }
    ServerForm Button {
        margin: 0 2;
    }
    """

    def __init__(self, server: ServerConfig | None = None):
        super().__init__()
        self.server = server

    def compose(self) -> ComposeResult:
        title = "编辑服务器" if self.server else "添加服务器"
        s = self.server

        yield Header()
        with Vertical():
            yield Label(title, id="form-title")
            yield Input(value=s.name if s else "", placeholder="名称 (必填)", id="f-name")
            yield Input(value=s.host if s else "", placeholder="地址 (必填，IP 或域名)", id="f-host")
            yield Input(value=str(s.port) if s and s.port != 22 else "", placeholder="端口 (默认 22)", id="f-port")
            yield Input(value=s.user if s else "", placeholder="用户名 (必填)", id="f-user")
            yield Input(value=s.auth_type if s else "", placeholder="认证方式 (key 或 password)", id="f-auth")
            yield Input(value=s.key_path if s and s.key_path else "", placeholder="密钥路径 (认证方式为 key 时必填)", id="f-keypath")
            yield Input(value="***" if s and s.password else "", placeholder="密码 (认证方式为 password 时必填)", password=True, id="f-password")
            yield Input(value=s.group if s and s.group else "", placeholder="分组 (可选)", id="f-group")
            yield Input(value=s.notes if s and s.notes else "", placeholder="备注 (可选)", id="f-notes")
            yield Label("", id="error-label")
            with Horizontal():
                yield Button("保存", variant="success", id="btn-save")
                yield Button("取消", variant="default", id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#f-name", Input).focus()

    def action_cancel(self) -> None:
        """Escape 绑定触发的取消(单一 escape 路径)。"""
        self._close()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self._close()
        elif event.button.id == "btn-save":
            self._save()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        field_ids = [
            "f-name", "f-host", "f-port", "f-user",
            "f-auth", "f-keypath", "f-password", "f-group", "f-notes",
        ]
        current_id = event.input.id
        if current_id in field_ids:
            idx = field_ids.index(current_id)
            if idx < len(field_ids) - 1:
                self.query_one(f"#{field_ids[idx + 1]}", Input).focus()
                return
        self._save()

    def _save(self) -> None:
        name = self.query_one("#f-name", Input).value.strip()
        host = self.query_one("#f-host", Input).value.strip()
        port_str = self.query_one("#f-port", Input).value.strip()
        user = self.query_one("#f-user", Input).value.strip()
        auth_type = self.query_one("#f-auth", Input).value.strip()
        key_path = self.query_one("#f-keypath", Input).value.strip()
        password = self.query_one("#f-password", Input).value.strip()
        group = self.query_one("#f-group", Input).value.strip()
        notes = self.query_one("#f-notes", Input).value.strip()

        if self.server and password == "***":
            password = self.server.password or ""

        port = int(port_str) if port_str else 22

        if not name:
            self.query_one("#error-label", Label).update("名称不能为空")
            return
        if not host:
            self.query_one("#error-label", Label).update("地址不能为空")
            return
        if not user:
            self.query_one("#error-label", Label).update("用户名不能为空")
            return
        if auth_type not in ("key", "password"):
            self.query_one("#error-label", Label).update("认证方式必须是 key 或 password")
            return

        try:
            cfg = ServerConfig(
                name=name, host=host, port=port, user=user,
                auth_type=auth_type, key_path=key_path or None,
                password=password or None, group=group, notes=notes,
            )
        except ValueError as e:
            self.query_one("#error-label", Label).update(str(e))
            return

        app = self.app
        if isinstance(app, SSHManagerApp):
            app.do_save_server(cfg, self.server)

    def _close(self) -> None:
        app = self.app
        if isinstance(app, SSHManagerApp):
            app.close_form()


# ── 文件传输表单 ──────────────────────────────────────

class TransferForm(Screen):
    """上传/下载文件路径输入表单。"""

    BINDINGS = [
        Binding("escape", "cancel", "取消"),
    ]

    DEFAULT_CSS = """
    TransferForm {
        align: center middle;
        height: 100%;
        width: 100%;
    }
    TransferForm Vertical {
        width: 60;
        max-height: 80vh;
        padding: 1 4;
        border: thick $accent;
        overflow-y: auto;
    }
    TransferForm Label {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }
    TransferForm Input {
        width: 100%;
        margin-bottom: 1;
    }
    TransferForm #error-label {
        color: $error;
        text-align: center;
        margin-bottom: 1;
    }
    TransferForm Horizontal {
        width: 100%;
        height: auto;
        margin-top: 1;
    }
    TransferForm Button {
        margin: 0 2;
    }
    """

    def __init__(self, server: ServerConfig, mode: str):
        super().__init__()
        self.server = server
        self.mode = mode  # "upload" 或 "download"

    def compose(self) -> ComposeResult:
        if self.mode == "upload":
            title = f"上传文件 → {self.server.name}"
            local_ph = "本地文件路径 (如 ./file.txt)"
            remote_ph = f"远程路径 (如 /home/{self.server.user}/file.txt)"
        else:
            title = f"下载文件 ← {self.server.name}"
            remote_ph = "远程文件路径 (如 /var/log/syslog)"
            local_ph = "本地保存路径 (如 ./syslog)"

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

    def on_mount(self) -> None:
        self.query_one("#tf-local", Input).focus()

    def action_cancel(self) -> None:
        """Escape 绑定触发的取消(单一 escape 路径)。"""
        self._close()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self._close()
        elif event.button.id == "btn-transfer":
            self._start()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "tf-local":
            self.query_one("#tf-remote", Input).focus()
        elif event.input.id == "tf-remote":
            self._start()

    def _start(self) -> None:
        local = self.query_one("#tf-local", Input).value.strip()
        remote = self.query_one("#tf-remote", Input).value.strip()

        if not local:
            self.query_one("#error-label", Label).update("本地路径不能为空")
            return
        if not remote:
            self.query_one("#error-label", Label).update("远程路径不能为空")
            return

        app = self.app
        if isinstance(app, SSHManagerApp):
            app.do_transfer(self.server, self.mode, local, remote)

    def _close(self) -> None:
        app = self.app
        if isinstance(app, SSHManagerApp):
            app.close_form()


# ── 主列表页 ─────────────────────────────────────────────

class MainScreen(Screen):
    """主列表页:搜索 + 服务器表格。"""

    def __init__(self) -> None:
        super().__init__()
        # 表格当前渲染的(可能已过滤)服务器列表,与可见行一一对应。
        # _get_selected_server 据此把 cursor_row 映射回正确的服务器,而不再去索引
        # 未过滤的 app.servers —— 后者在搜索时会让"选中/连接/删除的不是看到的那台"。
        self._filtered_servers: list[ServerConfig] = []

    # 禁用本屏自动聚焦 → 焦点保持为 None:
    #  (1) Screen._update_auto_focus 因 auto_focus 为空而跳过,pop_screen 回到本屏时
    #      不会把焦点落到第一个可聚焦控件 (#search-input);
    #  (2) 焦点为 None 时 Screen._binding_chain 直接启用本屏 BINDINGS,且 DataTable 未
    #      聚焦 → 不会用其 enter→select_cursor 吞掉回车。
    #  这是现有"认证后无焦点"行为的延续,据此彻底删除旧的焦点清空辅助方法。
    AUTO_FOCUS: ClassVar[str | None] = ""

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

    DEFAULT_CSS = """
    MainScreen #search-bar { height: 3; margin: 0 1; }
    MainScreen #search-input { width: 100%; }
    MainScreen #main-table { height: 1fr; }
    MainScreen #main-view { height: 1fr; }
    """

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
        # 不聚焦任何控件:保持焦点 None,使本屏 BINDINGS 直接生效。

    def _setup_table(self) -> None:
        table = self.query_one("#main-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("#", "Name", "Address", "User", "Auth", "Group")

    def _refresh_table(self) -> None:
        app = self.app
        assert isinstance(app, SSHManagerApp)
        table = self.query_one("#main-table", DataTable)
        # 搜索框是过滤的唯一真相源:读取它的当前值来渲染匹配项。这样表格内容与
        # 搜索框文本永远一致 —— 添加/编辑/删除后重新刷新也遵循同一过滤,不会出现
        # "框里有查询、表格却显示全量"的脱节。
        filter_text = self.query_one("#search-input", Input).value.strip().lower()
        self._filtered_servers = (
            app.servers if not filter_text
            else [s for s in app.servers
                  if filter_text in s.name.lower() or filter_text in s.host.lower()]
        )
        table.clear()
        if not self._filtered_servers:
            if not app.servers:
                table.add_row("", "(empty — 按 a 添加你的第一台服务器)", "", "", "", "")
            else:
                table.add_row("", "(no match)", "", "", "", "")
            return
        for i, s in enumerate(self._filtered_servers, 1):
            auth_label = "key" if s.auth_type == "key" else "pwd"
            table.add_row(str(i), s.name, s.host, s.user, auth_label, s.group)

    def _get_selected_server(self) -> ServerConfig | None:
        table = self.query_one("#main-table", DataTable)
        row = table.cursor_row
        # cursor_row 是"可见行"的下标,而可见行 == _filtered_servers,二者同源。
        if row is None or row < 0 or row >= len(self._filtered_servers):
            return None
        return self._filtered_servers[row]

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._refresh_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-input":
            # 提交查询:保留当前过滤结果(表格仍只显示匹配项),把焦点还给主屏,
            # 使 a/e/d/enter/u/x 等主屏绑定能在过滤结果上直接生效,而非被困在
            # 搜索框里。Input 把 enter 绑定为 submit(触发本消息)、不绑定 escape,
            # 故 esc 仍走 action_unfocus_search 清空查询、回到全量列表。
            self.set_focus(None)

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_unfocus_search(self) -> None:
        self.query_one("#search-input", Input).value = ""
        self._refresh_table()
        self.set_focus(None)  # 回到焦点-None 基线,a/d/enter/u 仍可用

    def action_connect_server(self) -> None:
        server = self._get_selected_server()
        if server:
            self.app.exit(result=server)

    def action_add_server(self) -> None:
        app = self.app
        assert isinstance(app, SSHManagerApp)
        app.show_server_form(server=None)

    def action_edit_server(self) -> None:
        app = self.app
        assert isinstance(app, SSHManagerApp)
        server = self._get_selected_server()
        if server:
            app.show_server_form(server=server)

    def action_delete_server(self) -> None:
        server = self._get_selected_server()
        if not server:
            return
        app = self.app
        assert isinstance(app, SSHManagerApp)
        try:
            app.vault.remove_server(server.name, app.password)
            app.servers = app.vault.list_servers(app.password)
            self._refresh_table()
        except Exception as e:
            self.app.exit(message=f"Delete failed: {e}")

    def action_upload_file(self) -> None:
        app = self.app
        assert isinstance(app, SSHManagerApp)
        server = self._get_selected_server()
        if server:
            app.show_transfer_form(server, mode="upload")

    def action_download_file(self) -> None:
        app = self.app
        assert isinstance(app, SSHManagerApp)
        server = self._get_selected_server()
        if server:
            app.show_transfer_form(server, mode="download")


# ── 主应用 ─────────────────────────────────────────────

class SSHManagerApp(App):
    """sshm 交互式服务器管理界面(协调者:持有状态、管理 Screen 栈)。"""

    TITLE = "sshm — SSH Server Manager"

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

    # ── Screen 协调 ──────────────────────────────────

    def _show_password_screen(self, retry: bool = False) -> None:
        if isinstance(self.screen, PasswordScreen):
            self.pop_screen()
        self.push_screen(PasswordScreen(retry=retry))

    def _show_main_screen(self) -> None:
        self.push_screen(MainScreen())

    def show_server_form(self, server: ServerConfig | None = None) -> None:
        self.push_screen(ServerForm(server=server))

    def show_transfer_form(self, server: ServerConfig, mode: str) -> None:
        self.push_screen(TransferForm(server=server, mode=mode))

    def close_form(self) -> None:
        """关闭栈顶表单/传输屏并刷新主屏。"""
        if isinstance(self.screen, (TransferForm, ServerForm)):
            self.pop_screen()
        self.refresh_main()

    def refresh_main(self) -> None:
        """数据变更后刷新主屏表格(主屏不在栈上时忽略)。"""
        # Textual 的 App.query_one 只在当前活动 screen 范围内搜索,而 close_form 在
        # 表单 pop 之后、任何后续 push 之前调用,此刻主屏确实是活动屏;但为了对其它
        # 调用时机也稳健,直接遍历 screen_stack 找到 MainScreen 实例再刷新。
        for screen in self.screen_stack:
            if isinstance(screen, MainScreen):
                screen._refresh_table()
                return

    # ── 认证 ──────────────────────────────────────

    def do_authenticate(self, password: str) -> None:
        try:
            self.servers = self.vault.list_servers(password)
            self.password = password
            self._authenticated = True
        except Exception:
            self._authenticated = False
            self._show_password_screen(retry=True)
            return
        # 认证成功:密码屏在栈上则弹出,然后进入主屏。
        if isinstance(self.screen, PasswordScreen):
            self.pop_screen()
        self._show_main_screen()

    # ── 服务器 CRUD ───────────────────────────────

    def do_save_server(self, cfg: ServerConfig, original: ServerConfig | None) -> None:
        try:
            if original:
                self.vault.remove_server(original.name, self.password)
            self.vault.add_server(cfg, self.password)
            self.servers = self.vault.list_servers(self.password)
            self.close_form()
        except Exception as e:
            try:
                self.query_one("#error-label", Label).update(f"保存失败: {e}")
            except Exception:
                pass

    # ── 文件传输 ──────────────────────────────────

    def do_transfer(self, server: ServerConfig, mode: str, local: str, remote: str) -> None:
        """退出 TUI 并执行文件传输。"""
        self.exit(result=("transfer", server, mode, local, remote))
