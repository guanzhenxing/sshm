"""交互式 TUI — 基于 Textual。"""

import getpass
import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.widgets import DataTable, Footer, Header, Input, Static

from sshm.vault import Vault, ServerConfig
from sshm.session import load_key, clear_key


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

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(id="search-bar"):
                yield Input(placeholder="搜索 (/)", id="search-input")
            yield DataTable(id="main-table")
            yield Static(
                "/ 搜索  ↑↓ 导航  Enter 连接  e 编辑  d 删除  u 上传  x 下载  q 退出",
                id="status-bar",
            )
        yield Footer()

    def on_mount(self) -> None:
        """启动时加载 vault 数据。"""
        self._setup_table()
        self._authenticate_and_load()

    def _setup_table(self) -> None:
        """配置表格列。"""
        table = self.query_one("#main-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("#", "Name", "Address", "User", "Auth", "Group")

    def _authenticate_and_load(self) -> None:
        """认证并加载服务器列表。"""
        cached = load_key()
        if cached:
            self.password = cached
        else:
            self.password = getpass.getpass("Master password: ")

        try:
            self.servers = self.vault.list_servers(self.password)
        except Exception:
            self.password = getpass.getpass("Master password (retry): ")
            try:
                self.servers = self.vault.list_servers(self.password)
            except Exception as e:
                self.exit(message=f"Authentication failed: {e}")
                return

        self._refresh_table()

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
