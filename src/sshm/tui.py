"""交互式 TUI — 基于 Textual。"""

import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal, Center
from textual.widgets import DataTable, Footer, Header, Input, Static, Label

from sshm.vault import Vault, ServerConfig
from sshm.session import load_key, clear_key


class PasswordScreen(Vertical):
    """密码输入界面。"""

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
        with Vertical():
            yield Label("sshm — SSH Server Manager" if not self.retry else "密码错误，请重试")
            yield Input(
                placeholder="输入主密码",
                password=True,
                id="password-input",
            )
            yield Label("", id="error-label")

    def on_mount(self) -> None:
        self.query_one("#password-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "password-input":
            password = event.value
            if not password:
                self.query_one("#error-label", Label).update("密码不能为空")
                return
            # 通知父 App 尝试认证
            app = self.app
            if isinstance(app, SSHManagerApp):
                app.do_authenticate(password)


class SSHManagerApp(App):
    """sshm 交互式服务器管理界面。"""

    TITLE = "sshm — SSH Server Manager"
    CSS = """
    #search-bar {
        height: 3;
        margin: 0 1;
    }
    #search-input {
        width: 100%;
    }
    #status-bar {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    #main-table {
        height: 1fr;
    }
    #main-view {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("slash", "focus_search", "搜索", key_display="/"),
        Binding("a", "add_server", "添加"),
        Binding("e", "edit_server", "编辑"),
        Binding("d", "delete_server", "删除"),
        Binding("enter", "connect_server", "连接"),
        Binding("u", "upload_file", "上传"),
        Binding("x", "download_file", "下载"),
        Binding("escape", "unfocus_search", "取消搜索"),
    ]

    def __init__(self, vault_path: str = "~/.sshm/vault.enc"):
        super().__init__()
        self.vault = Vault(vault_path)
        self.password = ""
        self.servers: list[ServerConfig] = []
        self._authenticated = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-view"):
            with Horizontal(id="search-bar"):
                yield Input(placeholder="搜索 (/)", id="search-input")
            yield DataTable(id="main-table")
            yield Static(
                "/ 搜索  ↑↓ 导航  Enter 连接  e 编辑  d 删除  u 上传  x 下载  q 退出",
                id="status-bar",
            )
        yield Footer()

    def on_mount(self) -> None:
        """启动时检查缓存或显示密码输入。"""
        self._setup_table()
        self._hide_main_content()

        # 先尝试从 Keychain 缓存读取
        cached = load_key()
        if cached:
            self.do_authenticate(cached)
        else:
            self._show_password_screen()

    def _hide_main_content(self) -> None:
        """隐藏主内容区域。"""
        main_view = self.query_one("#main-view")
        main_view.display = False

    def _show_main_content(self) -> None:
        """显示主内容区域。"""
        main_view = self.query_one("#main-view")
        main_view.display = True

    def _show_password_screen(self, retry: bool = False) -> None:
        """显示密码输入界面。"""
        # 移除已有的密码界面
        try:
            self.query_one("PasswordScreen").remove()
        except Exception:
            pass
        self._hide_main_content()
        self.mount(PasswordScreen(retry=retry))

    def do_authenticate(self, password: str) -> None:
        """尝试用给定密码认证。"""
        try:
            self.servers = self.vault.list_servers(password)
            self.password = password
            self._authenticated = True
        except Exception:
            self._authenticated = False
            self._show_password_screen(retry=True)
            return

        # 认证成功：移除密码界面，显示主内容
        try:
            self.query_one("PasswordScreen").remove()
        except Exception:
            pass
        self._show_main_content()
        self._refresh_table()

    def _setup_table(self) -> None:
        """配置表格列。"""
        table = self.query_one("#main-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("#", "Name", "Address", "User", "Auth", "Group")

    def _refresh_table(self, filter_text: str = "") -> None:
        """刷新表格显示。"""
        table = self.query_one("#main-table", DataTable)
        table.clear()

        filtered = self.servers
        if filter_text:
            ft = filter_text.lower()
            filtered = [
                s for s in self.servers
                if ft in s.name.lower() or ft in s.host.lower()
            ]

        if not filtered:
            if not self.servers:
                table.add_row("", "(empty — use 'sshm add' to add your first server)", "", "", "", "")
            else:
                table.add_row("", "(no match)", "", "", "", "")
            return

        for i, s in enumerate(filtered, 1):
            auth_label = "key" if s.auth_type == "key" else "pwd"
            table.add_row(str(i), s.name, s.host, s.user, auth_label, s.group)

    def on_input_changed(self, event: Input.Changed) -> None:
        """搜索输入变化时过滤表格。"""
        if event.input.id == "search-input":
            self._refresh_table(event.value)

    def action_focus_search(self) -> None:
        """聚焦搜索框。"""
        if not self._authenticated:
            return
        search = self.query_one("#search-input", Input)
        search.focus()

    def action_unfocus_search(self) -> None:
        """取消搜索，清空搜索框。"""
        search = self.query_one("#search-input", Input)
        search.value = ""
        table = self.query_one("#main-table", DataTable)
        table.focus()

    def _get_selected_server(self) -> ServerConfig | None:
        """获取当前选中的服务器。"""
        table = self.query_one("#main-table", DataTable)
        row = table.cursor_row
        if row is None or row >= len(self.servers):
            return None
        return self.servers[row]

    def action_connect_server(self) -> None:
        """连接到选中的服务器。"""
        server = self._get_selected_server()
        if not server:
            return
        self.exit(result=server)

    def action_add_server(self) -> None:
        """添加服务器。"""
        self.exit(message="Use 'sshm add' to add a new server.")

    def action_edit_server(self) -> None:
        """编辑选中的服务器。"""
        server = self._get_selected_server()
        if not server:
            return
        self.exit(message=f"Use 'sshm edit {server.name}' to edit this server.")

    def action_delete_server(self) -> None:
        """删除选中的服务器。"""
        server = self._get_selected_server()
        if not server:
            return
        try:
            self.vault.remove_server(server.name, self.password)
            self.servers = self.vault.list_servers(self.password)
            self._refresh_table()
        except Exception as e:
            self.exit(message=f"Delete failed: {e}")

    def action_upload_file(self) -> None:
        """上传文件。"""
        server = self._get_selected_server()
        if not server:
            return
        self.exit(message=f"Use 'sshm upload {server.name} <local> <remote>' to upload.")

    def action_download_file(self) -> None:
        """下载文件。"""
        server = self._get_selected_server()
        if not server:
            return
        self.exit(message=f"Use 'sshm download {server.name} <remote> <local>' to download.")
