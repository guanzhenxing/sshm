#!/usr/bin/env python3
"""渲染 sshm 主界面截图到 docs/images/tui.svg（用于 README 展示）。

用 Textual Pilot 驱动真实 App：填入若干演示服务器 → 认证 → 导出主屏 SVG。
不连真实 SSH、不碰真实 Keychain（强制走密码界面路径）。

用法：python scripts/render_screenshot.py
"""

import asyncio
import os
import sys
import tempfile

# 让脚本能 import 项目源码（src layout），无需安装。
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import sshm.session  # noqa: E402
from sshm.tui import SSHManagerApp  # noqa: E402
from sshm.vault import ServerConfig, Vault  # noqa: E402

DEMO_PASSWORD = "demo"

# 一组看起来真实的演示服务器，覆盖 key/password、不同端口、不同分组。
DEMO_SERVERS = [
    ServerConfig(
        name="prod-web", host="192.168.1.100", port=22, user="admin",
        auth_type="key", key_path="~/.ssh/id_ed25519", group="production",
    ),
    ServerConfig(
        name="prod-db", host="192.168.1.101", port=22, user="admin",
        auth_type="key", key_path="~/.ssh/id_ed25519", group="production",
    ),
    ServerConfig(
        name="prod-cache", host="192.168.1.102", port=2222, user="redis",
        auth_type="password", password="••••••••", group="production",
    ),
    ServerConfig(
        name="staging-app", host="10.0.0.50", port=22, user="deploy",
        auth_type="password", password="••••••••", group="staging",
    ),
    ServerConfig(
        name="bastion", host="bastion.example.com", port=22, user="jesen",
        auth_type="key", key_path="~/.ssh/id_ed25519", group="",
    ),
]


async def render(out_path: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        vault_path = os.path.join(d, "vault.enc")
        vault = Vault(vault_path)
        vault.init(DEMO_PASSWORD)
        for server in DEMO_SERVERS:
            vault.add_server(server, DEMO_PASSWORD)

        # 强制走"无缓存 → 显示密码界面"路径，不读真实 Keychain。
        sshm.session.load_key = lambda: None  # type: ignore[assignment]

        app = SSHManagerApp(vault_path=vault_path)
        async with app.run_test(size=(118, 40)) as pilot:
            await pilot.click("#password-input")
            await pilot.press(*DEMO_PASSWORD)
            await pilot.press("enter")
            await pilot.pause()

            svg = app.export_screenshot(title="sshm — SSH Server Manager")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(svg)
            print(f"wrote {out_path} ({len(svg)} bytes)")


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "docs/images/tui.svg"
    asyncio.run(render(out))


if __name__ == "__main__":
    main()
