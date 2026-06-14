"""crypto 模块单元测试。"""

import os

import pytest
from cryptography.exceptions import InvalidTag

from sshm.crypto import IV_SIZE, SALT_SIZE, decrypt, derive_key, encrypt


class TestDeriveKey:
    def test_returns_32_bytes(self):
        salt = os.urandom(SALT_SIZE)
        key = derive_key("test-password", salt)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_same_input_same_output(self):
        salt = os.urandom(SALT_SIZE)
        key1 = derive_key("test-password", salt)
        key2 = derive_key("test-password", salt)
        assert key1 == key2

    def test_different_password_different_key(self):
        salt = os.urandom(SALT_SIZE)
        key1 = derive_key("password-a", salt)
        key2 = derive_key("password-b", salt)
        assert key1 != key2

    def test_different_salt_different_key(self):
        key1 = derive_key("test-password", os.urandom(SALT_SIZE))
        key2 = derive_key("test-password", os.urandom(SALT_SIZE))
        assert key1 != key2


class TestEncryptDecrypt:
    def test_roundtrip(self):
        plaintext = b'{"version": 1, "servers": []}'
        password = "my-master-password"
        encrypted = encrypt(plaintext, password)
        decrypted = decrypt(encrypted, password)
        assert decrypted == plaintext

    def test_encrypted_not_plaintext(self):
        plaintext = b"hello world"
        encrypted = encrypt(plaintext, "password")
        assert encrypted != plaintext

    def test_different_password_decrypt_fails(self):
        encrypted = encrypt(b"secret data", "correct-password")
        with pytest.raises(InvalidTag):
            decrypt(encrypted, "wrong-password")

    def test_ciphertext_starts_with_salt_and_iv(self):
        encrypted = encrypt(b"test", "password")
        assert len(encrypted) > SALT_SIZE + IV_SIZE

    def test_different_calls_different_ciphertext(self):
        plaintext = b"same data"
        password = "same-password"
        enc1 = encrypt(plaintext, password)
        enc2 = encrypt(plaintext, password)
        assert enc1 != enc2
        assert decrypt(enc1, password) == plaintext
        assert decrypt(enc2, password) == plaintext

    def test_tampered_ciphertext_decrypt_fails(self):
        encrypted = encrypt(b"important data", "password")
        tampered = bytearray(encrypted)
        tampered[-1] ^= 0xFF
        with pytest.raises(InvalidTag):
            decrypt(bytes(tampered), "password")

    def test_empty_plaintext(self):
        encrypted = encrypt(b"", "password")
        assert decrypt(encrypted, "password") == b""
