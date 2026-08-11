"""Machine-bound encryption for secrets stored in ``btf_viewer.rc``.

AI provider API keys are written as ``enc1:<urlsafe-b64>`` so a shared or
committed ``.rc`` file does not expose plaintext credentials. The key is
derived from local machine identity (host, user, home, machine-id); the same
file will not decrypt on another machine.

This is at-rest protection for the config file, not a substitute for OS
keychain / vault storage against a compromised local account.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import os
import platform
import secrets
from typing import Optional

_PREFIX = "enc1:"
_SALT_LEN = 16
_NONCE_LEN = 16
_TAG_LEN = 32
_DK_LEN = 32
_PBKDF2_ITERS = 120_000
_APP_SALT = b"BTFViewer-ai-api-key-v1"

_machine_material_cache: Optional[bytes] = None


def is_encrypted_secret(value: Optional[str]) -> bool:
    """True when *value* uses the ``enc1:`` storage encoding."""
    return bool(value) and str(value).startswith(_PREFIX)


def is_ai_api_key_option(section: str, key: str) -> bool:
    """True for ``[ai]`` keys that hold provider API credentials."""
    return section == "ai" and str(key).endswith("_api_key")


def _machine_material() -> bytes:
    global _machine_material_cache
    if _machine_material_cache is not None:
        return _machine_material_cache
    parts = [
        platform.node(),
        getpass.getuser(),
        os.path.expanduser("~"),
    ]
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, "rb") as fh:
                mid = fh.read().decode("ascii", "ignore").strip()
            if mid:
                parts.append(mid)
                break
        except OSError:
            pass
    if platform.system() == "Windows":
        try:
            import winreg  # type: ignore[import-not-found]

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            ) as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                parts.append(str(guid))
        except Exception:
            pass
    _machine_material_cache = "|".join(parts).encode("utf-8", "surrogateescape")
    return _machine_material_cache


def _derive_key(salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        _machine_material() + _APP_SALT,
        salt,
        _PBKDF2_ITERS,
        dklen=_DK_LEN,
    )


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(
            key + nonce + counter.to_bytes(4, "big")
        ).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_secret(plaintext: Optional[str]) -> str:
    """Return an ``enc1:`` blob, or ``\"\"`` for empty input."""
    text = (plaintext or "").strip()
    if not text:
        return ""
    if is_encrypted_secret(text):
        return text
    salt = secrets.token_bytes(_SALT_LEN)
    nonce = secrets.token_bytes(_NONCE_LEN)
    key = _derive_key(salt)
    pt = text.encode("utf-8")
    ct = bytes(a ^ b for a, b in zip(pt, _keystream(key, nonce, len(pt))))
    tag = hmac.new(key, salt + nonce + ct, hashlib.sha256).digest()
    blob = base64.urlsafe_b64encode(salt + nonce + tag + ct).decode("ascii")
    return _PREFIX + blob


def decrypt_secret(stored: Optional[str]) -> str:
    """Decrypt an ``enc1:`` blob, or pass plaintext legacy values through."""
    raw = stored or ""
    if not raw:
        return ""
    if not is_encrypted_secret(raw):
        return raw
    try:
        blob = base64.urlsafe_b64decode(raw[len(_PREFIX):].encode("ascii"))
        need = _SALT_LEN + _NONCE_LEN + _TAG_LEN
        if len(blob) < need:
            return ""
        salt = blob[:_SALT_LEN]
        nonce = blob[_SALT_LEN:_SALT_LEN + _NONCE_LEN]
        tag = blob[_SALT_LEN + _NONCE_LEN:need]
        ct = blob[need:]
        key = _derive_key(salt)
        expect = hmac.new(key, salt + nonce + ct, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expect):
            return ""
        pt = bytes(a ^ b for a, b in zip(ct, _keystream(key, nonce, len(ct))))
        return pt.decode("utf-8")
    except Exception:
        return ""
