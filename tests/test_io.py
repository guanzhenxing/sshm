"""io 模块单元测试 — 导入/导出信封引擎。"""

import base64
import json

from sshm.crypto import KDF_ITERATIONS, decrypt
from sshm.io import EXPORT_FORMAT, EXPORT_VERSION, write_export
from sshm.vault import ServerConfig


def _sample_server(name="alpha"):
    return ServerConfig(
        name=name, host="1.1.1.1", port=22, user="root",
        auth_type="password", password="secret",
    )


class TestWriteExport:
    def test_plaintext_envelope_structure(self, tmp_path):
        out = tmp_path / "exp.json"
        write_export([_sample_server()], str(out))

        envelope = json.loads(out.read_text("utf-8"))
        assert envelope["format"] == EXPORT_FORMAT
        assert envelope["export_version"] == EXPORT_VERSION
        assert envelope["encrypted"] is False
        assert envelope["servers"][0]["name"] == "alpha"
        # 明文信封必须包含密码（凭证管理器的导出本就该含凭证）
        assert envelope["servers"][0]["password"] == "secret"

    def test_encrypted_envelope_structure(self, tmp_path):
        out = tmp_path / "exp.enc.json"
        write_export([_sample_server()], str(out), encrypt_password="expw")

        envelope = json.loads(out.read_text("utf-8"))
        assert envelope["format"] == EXPORT_FORMAT
        assert envelope["encrypted"] is True
        assert envelope["cipher"] == "aes-256-gcm"
        assert envelope["kdf"] == "pbkdf2-sha256"
        assert envelope["iterations"] == KDF_ITERATIONS
        # 密文信封里绝不能出现明文密码
        assert "secret" not in out.read_text("utf-8")
        # 用同一密码能解密还原
        blob = base64.b64decode(envelope["data"])
        plaintext = json.loads(decrypt(blob, "expw").decode("utf-8"))
        assert plaintext["servers"][0]["name"] == "alpha"
