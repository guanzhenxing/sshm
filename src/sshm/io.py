"""服务器列表导入/导出 — 自描述信封 I/O + 可选二次加密。

交换格式就是 vault 内部 server dict（ServerConfig.to_dict()），零翻译层。
信封自描述明文/密文，read_export 据此自动识别；并对旧版裸格式
{"version":1,"servers":[...]} 向后兼容。
"""

import base64
import binascii
import json
import sys

from sshm.crypto import KDF_ITERATIONS, decrypt, encrypt
from sshm.vault import ServerConfig

EXPORT_FORMAT = "sshm-export"
EXPORT_VERSION = 1


class EncryptedExportError(ValueError):
    """导出文件已加密但未提供解密密码。供 CLI/TUI 决定是否交互提示。"""


def write_export(
    servers: list[ServerConfig],
    out_path: str | None,
    encrypt_password: str | None = None,
) -> None:
    """构造信封并写出。

    out_path=None → 写到 stdout（管道场景）；encrypt_password 非空 → 加密信封。
    """
    servers_payload = [s.to_dict() for s in servers]
    if encrypt_password:
        inner = json.dumps({"servers": servers_payload}, ensure_ascii=False).encode("utf-8")
        blob = encrypt(inner, encrypt_password)
        envelope = {
            "format": EXPORT_FORMAT,
            "export_version": EXPORT_VERSION,
            "encrypted": True,
            "cipher": "aes-256-gcm",
            "kdf": "pbkdf2-sha256",
            "iterations": KDF_ITERATIONS,
            "data": base64.b64encode(blob).decode("ascii"),
        }
    else:
        envelope = {
            "format": EXPORT_FORMAT,
            "export_version": EXPORT_VERSION,
            "encrypted": False,
            "servers": servers_payload,
        }
    text = json.dumps(envelope, ensure_ascii=False, indent=2)
    if out_path is None:
        sys.stdout.write(text + "\n")
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")


def read_export(in_path: str, decrypt_password: str | None = None) -> list[ServerConfig]:
    """读信封 → 校验 → 返回 ServerConfig 列表。

    自动识别：新信封（明文/加密）、旧版裸格式 {"version":1,"servers":[...]}。
    原子：任一 server 非法则收集全部错误后一次性抛出，绝不返回半截结果。
    """
    raw_text = _read_text(in_path)
    try:
        envelope = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"导入文件不是合法 JSON：{e}") from e
    servers_payload = _extract_servers(envelope, decrypt_password)
    errors: list[str] = []
    servers: list[ServerConfig] = []
    for i, raw in enumerate(servers_payload):
        try:
            servers.append(ServerConfig.from_dict(raw))
        except (ValueError, TypeError) as e:
            errors.append(f"  第 {i + 1} 条：{e}")
    if errors:
        raise ValueError("导入文件包含非法条目：\n" + "\n".join(errors))
    return servers


def _read_text(in_path: str) -> str:
    if in_path == "-":
        return sys.stdin.read()
    with open(in_path, encoding="utf-8") as f:
        return f.read()


def _extract_servers(envelope, decrypt_password: str | None) -> list[dict]:
    if not isinstance(envelope, dict):
        raise ValueError("导入文件顶层必须是 JSON 对象。")
    if envelope.get("format") == EXPORT_FORMAT:
        version = envelope.get("export_version", 0)
        if version > EXPORT_VERSION:
            raise ValueError(
                f"导出版本 {version} 超过本工具支持（最高 {EXPORT_VERSION}），请升级 sshm。"
            )
        if envelope.get("encrypted"):
            if not decrypt_password:
                raise EncryptedExportError("该导出文件已加密，需要提供解密密码。")
            # 结构性错误（缺字段 / 非法 base64）→ ValueError；让 decrypt 的
            # InvalidTag（密码错误）原样抛出，保留其独立的"密码错误"语义。
            try:
                blob = base64.b64decode(envelope["data"])
            except (KeyError, binascii.Error, ValueError) as e:
                raise ValueError(f"无法解密或解析加密信封：{e}") from e
            plaintext = decrypt(blob, decrypt_password)  # InvalidTag 原样抛出
            try:
                payload = json.loads(plaintext.decode("utf-8"))
                return payload["servers"]
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                raise ValueError(f"无法解密或解析加密信封：{e}") from e
        servers = envelope.get("servers", [])
        if not isinstance(servers, list):
            raise ValueError("'servers' 字段必须是数组。")
        return servers
    # 旧版裸格式：当前 export（升级前）输出的 {"version":1,"servers":[...]}
    if "servers" in envelope:
        servers = envelope["servers"]
        if not isinstance(servers, list):
            raise ValueError("'servers' 字段必须是数组。")
        return servers
    raise ValueError("无法识别的导入格式（缺少 format / servers 字段）。")
