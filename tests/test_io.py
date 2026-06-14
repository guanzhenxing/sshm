"""io 模块单元测试 — 导入/导出信封引擎。"""

import base64
import json

import pytest

from sshm.crypto import KDF_ITERATIONS, decrypt
from sshm.io import EXPORT_FORMAT, EXPORT_VERSION, read_export, write_export
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


class TestReadExport:
    def test_plaintext_round_trip(self, tmp_path):
        out = tmp_path / "exp.json"
        original = [_sample_server("a"), _sample_server("b")]
        write_export(original, str(out))

        loaded = read_export(str(out))
        assert [s.name for s in loaded] == ["a", "b"]
        assert loaded[0].host == "1.1.1.1"

    def test_encrypted_round_trip(self, tmp_path):
        out = tmp_path / "exp.enc.json"
        write_export([_sample_server()], str(out), encrypt_password="expw")
        loaded = read_export(str(out), decrypt_password="expw")
        assert loaded[0].name == "alpha"

    def test_encrypted_wrong_password_fails(self, tmp_path):
        from cryptography.exceptions import InvalidTag

        out = tmp_path / "exp.enc.json"
        write_export([_sample_server()], str(out), encrypt_password="expw")
        with pytest.raises(InvalidTag):
            read_export(str(out), decrypt_password="wrong")

    def test_encrypted_without_password_raises_specific(self, tmp_path):
        from sshm.io import EncryptedExportError

        out = tmp_path / "exp.enc.json"
        write_export([_sample_server()], str(out), encrypt_password="expw")
        with pytest.raises(EncryptedExportError):
            read_export(str(out))

    def test_legacy_bare_format_compat(self, tmp_path):
        """旧版 sshm export 输出的 {"version":1,"servers":[...]} 仍可导入。"""
        out = tmp_path / "legacy.json"
        out.write_text(
            json.dumps({
                "version": 1,
                "servers": [{
                    "name": "legacy", "host": "9.9.9.9", "port": 22,
                    "user": "root", "auth_type": "password", "password": "p",
                }],
            }),
            encoding="utf-8",
        )
        loaded = read_export(str(out))
        assert loaded[0].name == "legacy"

    def test_newer_export_version_rejected(self, tmp_path):
        out = tmp_path / "future.json"
        out.write_text(
            json.dumps({"format": EXPORT_FORMAT, "export_version": 99,
                        "encrypted": False, "servers": []}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="超过本工具支持"):
            read_export(str(out))

    def test_unrecognized_format_rejected(self, tmp_path):
        out = tmp_path / "bad.json"
        out.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
        with pytest.raises(ValueError, match="无法识别"):
            read_export(str(out))

    def test_atomic_validation_lists_all_errors(self, tmp_path):
        """含多条非法 server → 抛出含全部错误清单的异常，不返回半截。"""
        out = tmp_path / "bad2.json"
        out.write_text(
            json.dumps({
                "format": EXPORT_FORMAT, "export_version": 1, "encrypted": False,
                "servers": [
                    {"name": "bad1", "host": "", "user": "root",
                     "auth_type": "key", "key_path": "/k"},          # host 空
                    {"name": "bad2", "host": "1.2.3.4", "user": "root",
                     "auth_type": "token"},                          # 非法 auth_type
                ],
            }),
            encoding="utf-8",
        )
        with pytest.raises(ValueError) as exc_info:
            read_export(str(out))
        msg = str(exc_info.value)
        assert "第 1 条" in msg
        assert "第 2 条" in msg

    def test_empty_servers_is_legal(self, tmp_path):
        out = tmp_path / "empty.json"
        write_export([], str(out))
        assert read_export(str(out)) == []

    def test_non_dict_envelope_rejected(self, tmp_path):
        """顶层 JSON 是数组（用户管道传入）→ ValueError，而非 AttributeError。"""
        out = tmp_path / "arr.json"
        out.write_text(
            json.dumps([{"name": "x", "host": "1.1.1.1", "port": 22,
                         "user": "root", "auth_type": "password", "password": "p"}]),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            read_export(str(out))

    def test_servers_not_a_list_rejected(self, tmp_path):
        """servers 字段存在但不是数组 → ValueError，而非 AttributeError。"""
        out = tmp_path / "badservers.json"
        out.write_text(
            json.dumps({"format": EXPORT_FORMAT, "export_version": 1,
                        "encrypted": False, "servers": {"a": 1}}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            read_export(str(out))

    def test_encrypted_envelope_missing_data_rejected(self, tmp_path):
        """加密信封缺 data 字段 → ValueError，而非 KeyError。"""
        out = tmp_path / "nodata.json"
        out.write_text(
            json.dumps({"format": EXPORT_FORMAT, "export_version": 1,
                        "encrypted": True, "cipher": "aes-256-gcm",
                        "kdf": "pbkdf2-sha256", "iterations": KDF_ITERATIONS}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            read_export(str(out), decrypt_password="anything")
