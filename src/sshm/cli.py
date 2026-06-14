"""命令行入口 — argparse 命令解析和路由。"""

import argparse
import getpass
import os
import sys
import time

from cryptography.exceptions import InvalidTag

from sshm import __version__
from sshm.io import EncryptedExportError, read_export, write_export
from sshm.session import clear_password, load_password, store_password
from sshm.vault import ServerConfig, Vault


def get_password(prompt: str = "Master password: ") -> str:
    """安全地获取密码输入。"""
    return getpass.getpass(prompt)


def get_vault_password(args, vault: Vault) -> str:
    """获取主密码：优先校验 Keychain 缓存，缓存缺失/失效则提示输入并写回缓存。

    会用 vault.load 校验候选密码——校验通过才返回/缓存，避免把误输的密码缓存下来。
    """
    if not args.no_cache:
        cached = load_password()
        if cached:
            try:
                vault.load(cached)
                return cached
            except Exception:
                clear_password()  # 缓存失效（密码已改）：清掉后回落到提示
    while True:
        password = get_password()
        try:
            vault.load(password)
        except Exception:
            print("密码错误，请重试。")
            continue
        if not args.no_cache:
            store_password(password)
        return password


def cmd_init(args):
    """处理 init 命令。"""
    vault = Vault(args.vault)
    if vault.path_exists() and not args.force:
        print(f"Vault already exists: {vault.path}")
        print("Use --force to overwrite.")
        sys.exit(1)
    password = get_password("Set master password: ")
    confirm = get_password("Confirm master password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)
    vault.init(password, force=args.force)
    print(f"Vault created: {vault.path}")


def cmd_add(args):
    """处理 add 命令。"""
    vault = Vault(args.vault)
    password = get_vault_password(args, vault)
    print("Adding a new server:")
    name = input("  Name: ")
    host = input("  Host: ")
    port_str = input("  Port [22]: ")
    port = int(port_str) if port_str else 22
    user = input("  User: ")
    auth_type = input("  Auth type (key/password): ")
    key_path = None
    pwd = None
    if auth_type == "key":
        key_path = input("  Key path [~/.ssh/id_rsa]: ") or "~/.ssh/id_rsa"
    else:
        pwd = get_password("  Server password: ")
    group = input("  Group: ")
    notes = input("  Notes: ")
    server = ServerConfig(
        name=name, host=host, port=port, user=user,
        auth_type=auth_type, key_path=key_path, password=pwd,
        group=group, notes=notes,
    )
    vault.add_server(server, password)
    print(f"Server '{name}' added.")


def cmd_ls(args):
    """处理 ls 命令。"""
    vault = Vault(args.vault)
    password = get_vault_password(args, vault)
    servers = vault.list_servers(password)
    if not servers:
        print("(no servers configured — use 'sshm add' to add one)")
        return
    print(f"  {'#':<4} {'Name':<16} {'Address':<20} {'User':<10} {'Auth':<6} {'Group'}")
    print(f"  {'---':<4} {'---':<16} {'---':<20} {'---':<10} {'---':<6} {'---'}")
    for i, s in enumerate(servers, 1):
        auth_label = "key" if s.auth_type == "key" else "pwd"
        print(f"  {i:<4} {s.name:<16} {s.host:<20} {s.user:<10} {auth_label:<6} {s.group}")


def cmd_connect(args):
    """处理 connect/ssh 命令。"""
    from sshm.ssh import ssh_connect
    vault = Vault(args.vault)
    password = get_vault_password(args, vault)
    servers = vault.list_servers(password)
    if not servers:
        print("No servers configured. Add one with 'sshm add' first.")
        sys.exit(1)
    server = _find_server(servers, args.server)
    sys.exit(ssh_connect(server))


def cmd_edit(args):
    """处理 edit 命令。"""
    vault = Vault(args.vault)
    password = get_vault_password(args, vault)
    servers = vault.list_servers(password)
    server = _find_server(servers, args.server)
    print(f"Editing '{server.name}' (press Enter to keep current value):")
    updates = {}
    new_host = input(f"  Host [{server.host}]: ")
    if new_host:
        updates["host"] = new_host
    new_port = input(f"  Port [{server.port}]: ")
    if new_port:
        updates["port"] = int(new_port)
    new_user = input(f"  User [{server.user}]: ")
    if new_user:
        updates["user"] = new_user
    new_group = input(f"  Group [{server.group}]: ")
    if new_group:
        updates["group"] = new_group
    new_notes = input(f"  Notes [{server.notes}]: ")
    if new_notes:
        updates["notes"] = new_notes
    if updates:
        vault.edit_server(server.name, updates, password)
        print(f"Server '{server.name}' updated.")
    else:
        print("No changes.")


def cmd_rm(args):
    """处理 rm 命令。"""
    vault = Vault(args.vault)
    password = get_vault_password(args, vault)
    vault.remove_server(args.server, password)
    print(f"Server '{args.server}' removed.")


def cmd_upload(args):
    """处理 upload 命令。"""
    from sshm.transfer import scp_upload
    vault = Vault(args.vault)
    password = get_vault_password(args, vault)
    servers = vault.list_servers(password)
    server = _find_server(servers, args.server)
    sys.exit(scp_upload(server, args.local, args.remote))


def cmd_download(args):
    """处理 download 命令。"""
    from sshm.transfer import scp_download
    vault = Vault(args.vault)
    password = get_vault_password(args, vault)
    servers = vault.list_servers(password)
    server = _find_server(servers, args.server)
    sys.exit(scp_download(server, args.remote, args.local))


def cmd_password(args):
    """处理 password 命令（修改主密码）。"""
    vault = Vault(args.vault)
    old_password = get_password("Current master password: ")
    try:
        data = vault.load(old_password)
    except Exception:
        print("当前密码错误。")
        sys.exit(1)
    new_password = get_password("New master password: ")
    confirm = get_password("Confirm new master password: ")
    if new_password != confirm:
        print("两次输入的新密码不一致。")
        sys.exit(1)
    vault.save(data, new_password)
    clear_password()
    print("Master password changed.")


def cmd_lock(args):
    """处理 lock 命令。"""
    clear_password()
    print("Session locked. Master password will be required on next use.")


def cmd_export(args):
    """处理 export 命令。"""
    vault = Vault(args.vault)
    password = get_vault_password(args, vault)
    servers = vault.list_servers(password)
    encrypt_password = None
    if args.encrypt:
        if args.password:
            encrypt_password = args.password
        else:
            encrypt_password = get_password("Export password: ")
            confirm = get_password("Confirm export password: ")
            if encrypt_password != confirm:
                print("两次输入的导出密码不一致。")
                sys.exit(1)
    write_export(servers, args.output, encrypt_password)
    if args.output:
        kind = "加密" if encrypt_password else "明文"
        print(f"已{kind}导出 {len(servers)} 台服务器到 {args.output}")


def _read_import_file(args) -> list[ServerConfig]:
    """读导入文件；遇加密但缺密码则交互提示。InvalidTag（错密码）向上抛由调用方处理。"""
    decrypt_password = args.password
    try:
        return read_export(args.file, decrypt_password)
    except EncryptedExportError:
        decrypt_password = get_password("Export password: ")
        return read_export(args.file, decrypt_password)


def cmd_import(args):
    """处理 import 命令。"""
    vault = Vault(args.vault)
    password = get_vault_password(args, vault)
    try:
        incoming = _read_import_file(args)
    except InvalidTag:
        print("解密失败，密码错误")
        sys.exit(1)
    except (ValueError, FileNotFoundError) as e:
        print(f"导入失败：{e}")
        sys.exit(1)
    report = vault.merge_servers(
        incoming, args.strategy, password, dry_run=args.dry_run,
    )
    prefix = "（dry-run）" if args.dry_run else ""
    print(f"{prefix}导入完成：{report.summary()}")
    for name in report.skipped:
        print(f"  skipped: {name}")
    for old, new in report.renamed:
        print(f"  renamed: {old} → {new}")


def _find_server(servers: list[ServerConfig], name_or_index: str) -> ServerConfig:
    """按名称或序号查找服务器。"""
    if name_or_index.isdigit():
        idx = int(name_or_index) - 1
        if 0 <= idx < len(servers):
            return servers[idx]
    for s in servers:
        if s.name == name_or_index:
            return s
    print(f"Server not found: {name_or_index}")
    sys.exit(1)


def run_tui():
    """启动 Textual TUI。"""
    import termios

    from sshm.ssh import ssh_connect
    from sshm.transfer import scp_download, scp_upload
    from sshm.tui import SSHManagerApp

    parser = build_parser()
    args, _ = parser.parse_known_args()
    vault_path = getattr(args, "vault", "~/.sshm/vault.enc")

    app = SSHManagerApp(vault_path=vault_path, no_cache=getattr(args, "no_cache", False))
    result = app.run()

    # 确保终端恢复
    try:
        fd = sys.stdin.fileno()
        attrs = termios.tcgetattr(fd)
        attrs[3] |= termios.ECHO | termios.ICANON
        termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
    except Exception:
        pass
    sys.stdout.flush()
    time.sleep(0.05)

    if isinstance(result, ServerConfig):
        sys.exit(ssh_connect(result))

    if isinstance(result, tuple) and len(result) == 5 and result[0] == "transfer":
        _, server, mode, local, remote = result
        if mode == "upload":
            sys.exit(scp_upload(server, local, remote))
        else:
            sys.exit(scp_download(server, remote, local))


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。"""
    parser = argparse.ArgumentParser(
        prog="sshm",
        description="SSH Server Manager — encrypted, interactive CLI",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    parser.add_argument(
        "-V", "--version", action="version", version=f"sshm {__version__}",
    )
    parser.add_argument("--no-cache", action="store_true", help="跳过 Keychain 缓存")
    parser.add_argument("--vault", default="~/.sshm/vault.enc", help="vault 文件路径")

    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="初始化加密 vault")
    p_init.add_argument("--force", action="store_true", help="覆盖已有 vault")

    sub.add_parser("add", help="添加服务器")
    sub.add_parser("ls", help="列出所有服务器")

    p_conn = sub.add_parser("connect", help="连接到服务器")
    p_conn.add_argument("server", help="服务器名称或序号")
    p_ssh = sub.add_parser("ssh", help="连接到服务器 (connect 别名)")
    p_ssh.add_argument("server", help="服务器名称或序号")

    p_edit = sub.add_parser("edit", help="编辑服务器配置")
    p_edit.add_argument("server", help="服务器名称或序号")

    p_rm = sub.add_parser("rm", help="删除服务器")
    p_rm.add_argument("server", help="服务器名称或序号")

    p_up = sub.add_parser("upload", help="上传文件 (SCP)")
    p_up.add_argument("server", help="服务器名称或序号")
    p_up.add_argument("local", help="本地文件路径")
    p_up.add_argument("remote", help="远程文件路径")

    p_dl = sub.add_parser("download", help="下载文件 (SCP)")
    p_dl.add_argument("server", help="服务器名称或序号")
    p_dl.add_argument("remote", help="远程文件路径")
    p_dl.add_argument("local", help="本地文件路径")

    sub.add_parser("password", help="修改主密码")
    sub.add_parser("lock", help="清除 Keychain 会话缓存")
    p_exp = sub.add_parser("export", help="导出服务器配置 (JSON)")
    p_exp.add_argument("-o", "--output", help="输出文件路径（不传则打到 stdout）")
    p_exp.add_argument("--encrypt", action="store_true", help="用独立密码加密导出文件")
    p_exp.add_argument("--password", help="加密密码（--encrypt 时不传则交互提示）")
    p_imp = sub.add_parser("import", help="导入服务器配置 (JSON)")
    p_imp.add_argument("file", help="导入文件路径（- 表示 stdin）")
    strategy = p_imp.add_mutually_exclusive_group()
    strategy.add_argument("--skip", action="store_const", dest="strategy", const="skip")
    strategy.add_argument("--overwrite", action="store_const", dest="strategy", const="overwrite")
    strategy.add_argument("--rename", action="store_const", dest="strategy", const="rename")
    p_imp.set_defaults(strategy="skip")
    p_imp.add_argument("--dry-run", action="store_true", help="只报告，不写盘")
    p_imp.add_argument("--password", help="加密导出文件的解密密码（不传则交互提示）")

    return parser


def main():
    """主入口。"""
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        os.environ["SSHM_VERBOSE"] = "1"

    if not args.command:
        run_tui()
        return

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "ls": cmd_ls,
        "connect": cmd_connect,
        "ssh": cmd_connect,
        "edit": cmd_edit,
        "rm": cmd_rm,
        "upload": cmd_upload,
        "download": cmd_download,
        "password": cmd_password,
        "lock": cmd_lock,
        "export": cmd_export,
        "import": cmd_import,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
