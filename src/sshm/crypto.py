"""加密/解密模块 — AES-256-GCM + PBKDF2-SHA256。"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

SALT_SIZE = 16
IV_SIZE = 12
KDF_ITERATIONS = 600_000


def derive_key(password: str, salt: bytes) -> bytes:
    """使用 PBKDF2-SHA256 从密码派生 256 位 AES 密钥。"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt(plaintext: bytes, password: str) -> bytes:
    """加密数据，返回 salt + IV + ciphertext（含 auth tag）。"""
    salt = os.urandom(SALT_SIZE)
    key = derive_key(password, salt)
    iv = os.urandom(IV_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext, None)
    return salt + iv + ciphertext


def decrypt(data: bytes, password: str) -> bytes:
    """解密数据（salt + IV + ciphertext），返回明文。"""
    salt = data[:SALT_SIZE]
    iv = data[SALT_SIZE : SALT_SIZE + IV_SIZE]
    ciphertext = data[SALT_SIZE + IV_SIZE :]
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext, None)
