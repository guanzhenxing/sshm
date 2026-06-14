"""服务器列表导入/导出 — 自描述信封 I/O + 可选二次加密。

交换格式就是 vault 内部 server dict（ServerConfig.to_dict()），零翻译层。
信封自描述明文/密文，read_export 据此自动识别；并对旧版裸格式
{"version":1,"servers":[...]} 向后兼容。
"""

import base64
import json
import sys

from sshm.crypto import KDF_ITERATIONS, encrypt
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
