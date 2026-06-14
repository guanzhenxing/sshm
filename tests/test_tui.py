"""TUI 行为测试 — 基于 Textual Pilot。

这些测试故意写成行为级(按键 → 观察可见结果),尽量不依赖内部类名 / mount 结构,
以便在后续 Screen 重构(Vertical → 真 Screen)之后仍然存活。

被锁定的主流程:
  - 启动停在密码界面
  - 认证成功进入主表格
  - 搜索实时过滤表格(无匹配时显示占位)
  - 添加服务器(表单填写 → 保存 → 表格多一行)
  - 删除服务器(被删服务器从表格消失)
  - 连接(Enter)退出并返回 ServerConfig
  - 传输(上传)退出并返回 ("transfer", ...) 元组

实现备注(均已对真实 Textual 8.x / 现有 mount 架构校准):
  - run_test 用 size=(80, 50):ServerForm 的内层 Vertical 为 max-height:80vh + 滚动,
    默认 24 行终端里表单控件会落到可见区域之外。
  - 提交表单时聚焦最后一个字段 #f-notes 后按回车(等价于点保存按钮,但不受滚动影响)。
  - 认证后主表格处于"无焦点"状态(焦点是 None),此时按 d / enter / u 等应用级
    绑定能正确触发;若主动给 DataTable focus,它会吞掉 enter。因此这些用例不显式
    聚焦表格,而是依赖默认 cursor_row=0(已校准)。
  - 表格清空后会显示占位行("(empty — ...)"),所以删除后 row_count 不一定减少;
    改为断言"被删服务器文本不再可见"这一真正的用户可见行为。
"""

import os
import tempfile

import pytest
from textual.dom import NoMatches
from textual.widgets import DataTable, Footer, Input
from textual.widgets._footer import FooterKey

from sshm.tui import SSHManagerApp, MainScreen
from sshm.vault import ServerConfig, Vault


TEST_PASSWORD = "test-pw"

# 偏大的终端尺寸:保证 ServerForm 的保存按钮落在可见区域内。
TEST_SIZE = (80, 50)


@pytest.fixture
def app_with_vault(monkeypatch):
    """临时 vault(含一台服务器)+ 已配置但尚未运行的 App。

    monkeypatch 让 session.load_key 返回 None,强制走"无缓存 → 显示密码界面"的路径。
    """
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "vault.enc")
        vault = Vault(path)
        vault.init(TEST_PASSWORD)
        vault.add_server(
            ServerConfig(
                name="alpha",
                host="1.2.3.4",
                port=22,
                user="root",
                auth_type="password",
                password="x",
            ),
            TEST_PASSWORD,
        )
        monkeypatch.setattr("sshm.session.load_key", lambda: None)
        app = SSHManagerApp(vault_path=path)
        yield app


# ── 辅助函数 ──────────────────────────────────────────────

async def _authenticate(pilot, password: str = TEST_PASSWORD) -> None:
    """在密码界面输入密码并回车,完成认证。"""
    await pilot.click("#password-input")
    await pilot.press(*password)
    await pilot.press("enter")
    await pilot.pause()


def _table(app) -> DataTable:
    # #main-table 位于 MainScreen 上。MainScreen 仅在认证成功后 push,之后无论栈顶是
    # 主屏还是某张表单/传输屏,MainScreen 都停留在 screen_stack 上。遍历 screen_stack
    # 按类型找到它再取 #main-table:
    #  - 认证成功后(绝大多数用例):栈上找到 MainScreen,返回其表格。
    #  - 认证失败时(test_wrong_password_keeps_retry_screen):栈上没有 MainScreen,
    #    返回一张空表 → _row_contains 对所有内容返回 False,与重构前"空表格不含
    #    alpha"的行为完全一致,不改变任何断言语义。
    # 注:Textual 的 app.query_one 只在当前活动 screen 范围内搜索,故必须遍历 screen_stack。
    for screen in app.screen_stack:
        if isinstance(screen, MainScreen):
            return screen.query_one("#main-table", DataTable)
    return DataTable()


def _cell_to_str(cell) -> str:
    """单元格可能是 str 或 Text,统一转成纯文本。"""
    return cell.plain if hasattr(cell, "plain") else str(cell)


def _row_contains(table: DataTable, needle: str) -> bool:
    """表格里是否存在包含 needle 的可见行(按可见文本断言)。"""
    for row_key in table.rows:
        text = " ".join(
            _cell_to_str(table.get_cell(row_key, col_key))
            for col_key in table.columns
        )
        if needle in text:
            return True
    return False


# ── 1. 启动 / 认证 ────────────────────────────────────────

async def test_starts_on_password_screen(app_with_vault):
    """无缓存启动时,停在密码输入界面。"""
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await pilot.pause()
        # 密码输入框现在位于被 push 的 PasswordScreen 上,用当前 screen 查询。
        pw_input = app.screen.query_one("#password-input", Input)
        assert pw_input is not None
        assert pw_input.has_focus


async def test_authenticate_shows_main_table(app_with_vault):
    """输入正确密码 + 回车 → 主表格可见,且包含已配置的服务器。"""
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)
        assert _row_contains(_table(app), "alpha")


async def test_wrong_password_keeps_retry_screen(app_with_vault):
    """输入错误密码 → 仍停留在密码界面(可重试),主表格不出现。"""
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot, password="wrong-password")
        assert not _row_contains(_table(app), "alpha")
        # 密码输入框仍在(重试界面,位于被 push 的 PasswordScreen 上)
        assert app.screen.query_one("#password-input", Input) is not None


# ── 2. 搜索 ───────────────────────────────────────────────

async def test_search_filters_table_live(app_with_vault):
    """在搜索框输入不匹配的字符串 → 表格显示 no-match 占位,原服务器被过滤掉。"""
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)
        assert _row_contains(_table(app), "alpha")

        await pilot.click("#search-input")
        await pilot.press(*"zzzznomatch")
        await pilot.pause()

        assert not _row_contains(_table(app), "alpha")
        assert _row_contains(_table(app), "(no match)")


# ── 3. 添加服务器 ────────────────────────────────────────

async def test_add_server_creates_row(app_with_vault):
    """按 a → 弹出表单 → 填写关键字段 → 保存 → 主表格多一行新服务器。"""
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)
        before = _table(app).row_count

        await pilot.press("a")
        await pilot.pause()
        # ServerForm 现在是被 push 的 Screen,用当前 screen 查询(同密码/传输界面测试)。
        assert app.screen.query_one("#f-name", Input) is not None

        # 用 click 聚焦各字段填写(避免依赖 Tab 顺序)
        await pilot.click("#f-name")
        await pilot.press(*"beta")
        await pilot.click("#f-host")
        await pilot.press(*"5.6.7.8")
        await pilot.click("#f-user")
        await pilot.press(*"deploy")
        await pilot.click("#f-auth")
        await pilot.press(*"password")
        await pilot.click("#f-password")
        await pilot.press(*"secret")

        # 提交:聚焦最后一个字段后回车 → 触发表单 _save()。
        # (ServerForm 的内层 Vertical 为 max-height:80vh + 滚动,保存按钮常常在
        # 可见区域之外;用回车提交是等价且更稳健的用户行为。)
        await pilot.click("#f-notes")
        await pilot.press("enter")
        await pilot.pause()

        assert _table(app).row_count == before + 1
        assert _row_contains(_table(app), "beta")


# ── 4. 删除服务器 ────────────────────────────────────────

async def test_delete_server_removes_row(app_with_vault):
    """选中第一行后按 d → 该服务器从表格消失,并显示空占位行。

    注意:表格清空后会显示占位行,所以不能简单断言 row_count--。
    这里既断言"alpha 不再可见",也断言"空占位行已渲染"——
    避免 action_delete_server 的 bare except 吞掉异常导致测试 vacuous pass。
    """
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)
        assert _row_contains(_table(app), "alpha")

        # 认证后默认无焦点、cursor_row=0(即选中 alpha);直接按 d 触发应用级绑定。
        await pilot.press("d")
        await pilot.pause()

        assert not _row_contains(_table(app), "alpha")
        # 正向断言:删除唯一服务器后,表格应渲染空占位行。
        assert _row_contains(_table(app), "(empty")


# ── 5. 连接(Enter)退出 ───────────────────────────────────

async def test_connect_exits_with_server_config(app_with_vault):
    """选中服务器后按 Enter → 应用退出,return_value 为 ServerConfig。"""
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)
        # 认证后默认无焦点、cursor_row=0;按 enter 触发应用级"连接"绑定。
        await pilot.press("enter")
        await pilot.pause()

    assert isinstance(app.return_value, ServerConfig)
    assert app.return_value.name == "alpha"


# ── 6. 传输(上传)退出 ────────────────────────────────────

async def test_upload_exits_with_transfer_tuple(app_with_vault):
    """按 u → 弹出传输表单 → 填写路径 → 开始传输 → 退出并返回 ("transfer", ...) 元组。"""
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)
        # 认证后默认 cursor_row=0(选中 alpha),按 u 进入上传表单。
        await pilot.press("u")
        await pilot.pause()
        # TransferForm 现在是被 push 的 Screen,用当前 screen 查询(同密码界面测试)。
        assert app.screen.query_one("#tf-local", Input) is not None

        await pilot.click("#tf-local")
        await pilot.press(*"./local.txt")
        await pilot.click("#tf-remote")
        await pilot.press(*"/remote/path.txt")

        await pilot.click("#btn-transfer")
        await pilot.pause()

    result = app.return_value
    assert isinstance(result, tuple)
    assert len(result) == 5
    assert result[0] == "transfer"
    server, mode, local, remote = result[1], result[2], result[3], result[4]
    assert server.name == "alpha"
    assert mode == "upload"
    assert local == "./local.txt"
    assert remote == "/remote/path.txt"


# ── 7. Footer 统一设计(Screen 化重构后的回归保护) ──────────
#
# 重构前 bug:主屏底部同时渲染了一个手写的 status-bar Static 和一个 Footer,
# 出现两条重复的快捷键提示。重构后每张 Screen 自己 yield 一个 Footer,且 Footer
# 自动读取"当前活动 Screen"的 BINDINGS —— 所以 Footer 内容随栈顶 Screen 变化。
# 以下用例锁定这两件事:(1) 每屏 Footer 显示本屏自己的绑定;(2) 主屏不再有重复行。

def _footer_descriptions(app) -> set[str]:
    """收集当前活动 Screen 上 Footer 各 FooterKey 的描述文本。

    Footer.compose() 在 _bindings_ready 后从 self.screen.active_bindings 构建
    FooterKey 子控件;每个 FooterKey 暴露 .description(如 "搜索"/"取消")。
    直接读 .description 比 render().plain 更稳(后者含键名 + padding 空格)。
    """
    footer = app.screen.query_one(Footer)
    return {fk.description for fk in footer.query(FooterKey)}


async def test_main_screen_footer_shows_its_bindings(app_with_vault):
    """主屏 Footer 显示主屏自己的绑定(搜索/添加/连接/退出…)。"""
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)
        assert isinstance(app.screen, MainScreen)

        descs = _footer_descriptions(app)
        # 主屏 BINDINGS 里这些描述都应出现在 Footer。
        assert {"搜索", "添加", "连接", "退出"} <= descs
        # 顺带多覆盖几个(这些一旦被删/改名,Footer 立刻反映)。
        assert {"编辑", "删除", "上传", "下载"} <= descs


async def test_main_screen_has_no_duplicate_status_bar(app_with_vault):
    """主屏只有一行底部提示:旧的 status-bar 已删除,且恰好一个 Footer。

    这是对"双行重复提示"原始 bug 的回归用例。
    """
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)
        assert isinstance(app.screen, MainScreen)

        # (a) 旧的 status-bar Static 已不存在。
        with pytest.raises(NoMatches):
            app.screen.query_one("#status-bar")
        # (b) 恰好一个 Footer(没有重复渲染)。
        assert len(app.screen.query(Footer)) == 1


async def test_form_footer_shows_cancel(app_with_vault):
    """按 a 进入添加表单后,栈顶 ServerForm 的 Footer 显示"取消",
    且不再显示主屏专属的"添加"/"连接"——证明 Footer 随当前 Screen 变化。"""
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)
        await pilot.press("a")
        await pilot.pause()

        from sshm.tui import ServerForm
        assert isinstance(app.screen, ServerForm)

        descs = _footer_descriptions(app)
        assert "取消" in descs
        # 主屏专属绑定不该出现在表单屏 Footer 里(上下文敏感)。
        assert "添加" not in descs
        assert "连接" not in descs


async def test_transfer_footer_shows_cancel(app_with_vault):
    """按 u 进入上传表单后,栈顶 TransferForm 的 Footer 显示"取消"。"""
    app = app_with_vault
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)
        await pilot.press("u")
        await pilot.pause()

        from sshm.tui import TransferForm
        assert isinstance(app.screen, TransferForm)

        descs = _footer_descriptions(app)
        assert "取消" in descs
        assert "添加" not in descs


# ── 8. 搜索行为修正(重构前遗留 bug 的回归用例) ──────────────
#
# 两个遗留 bug(重构前就存在,本次一并修掉):
#  (B1) 过滤后选中错位:_refresh_table 渲染的是"过滤后"列表,但 _get_selected_server
#       用 cursor_row 去索引"未过滤"的 app.servers —— 搜索时选中的/连接的/删除的
#       不是表格里看到的那台。
#  (B2) 搜索焦点陷阱:进入搜索后所有字母键都被搜索框吃掉,只能 esc 退出,无法
#       "提交查询后在过滤结果上继续操作"。修正:Enter 提交查询(保留过滤、把焦点
#       还给主屏),Esc 取消(清空、回到全量)。

@pytest.fixture
def app_with_three_servers(monkeypatch):
    """临时 vault(含 alpha/bravo/charlie 三台),用于过滤后选中行的测试。"""
    servers = [
        ServerConfig(name="alpha", host="1.1.1.1", port=22, user="root",
                     auth_type="password", password="x"),
        ServerConfig(name="bravo", host="2.2.2.2", port=22, user="root",
                     auth_type="password", password="x"),
        ServerConfig(name="charlie", host="3.3.3.3", port=22, user="root",
                     auth_type="password", password="x"),
    ]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "vault.enc")
        vault = Vault(path)
        vault.init(TEST_PASSWORD)
        for s in servers:
            vault.add_server(s, TEST_PASSWORD)
        monkeypatch.setattr("sshm.session.load_key", lambda: None)
        app = SSHManagerApp(vault_path=path)
        yield app


async def test_get_selected_server_reflects_filtered_list(app_with_three_servers):
    """(B1) 搜索 'charlie' 后表格只剩 charlie(cursor_row=0),
    _get_selected_server 应返回 charlie,而不是未过滤列表里的 alpha。"""
    app = app_with_three_servers
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)

        await pilot.click("#search-input")
        await pilot.press(*"charlie")
        await pilot.pause()

        main = next(s for s in app.screen_stack if isinstance(s, MainScreen))
        selected = main._get_selected_server()
        assert selected is not None
        assert selected.name == "charlie"


async def test_search_enter_commits_filter_and_defocuses(app_with_three_servers):
    """(B2) 搜索框输入后按 Enter 应"提交"查询:焦点离开搜索框(主屏绑定重新可用),
    且过滤结果保留。重构前 Enter 在搜索框里是空操作,焦点被困住。"""
    app = app_with_three_servers
    async with app.run_test(size=TEST_SIZE) as pilot:
        await _authenticate(pilot)

        await pilot.click("#search-input")
        await pilot.press(*"charlie")
        await pilot.press("enter")   # 提交查询
        await pilot.pause()

        main = next(s for s in app.screen_stack if isinstance(s, MainScreen))
        search = main.query_one("#search-input", Input)
        # 焦点已离开搜索框 → a/d/enter 等主屏绑定重新可用。
        assert not search.has_focus
        # 过滤结果仍保留(charlie 可见、alpha 被过滤掉)。
        assert _row_contains(_table(app), "charlie")
        assert not _row_contains(_table(app), "alpha")
