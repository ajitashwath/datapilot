import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

import segno

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1
RECOVERY_CODE_COUNT = 10
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def decode_secret(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def code_at(secret: str, step: int, digits: int = DIGITS) -> str:
    digest = hmac.new(decode_secret(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(number).zfill(digits)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def verify_code(secret: str, code: str, last_step: int = 0, now: float | None = None) -> int | None:
    cleaned = code.strip().replace(" ", "")
    if len(cleaned) != DIGITS or not cleaned.isdigit():
        return None
    step_now = current_step(now)
    matched = None
    for step in range(step_now - WINDOW, step_now + WINDOW + 1):
        if hmac.compare_digest(code_at(secret, step), cleaned) and step > last_step:
            matched = step
    return matched


def otpauth_uri(secret: str, email: str, issuer: str = "DataPilot") -> str:
    label = quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"


def qr_svg(uri: str) -> str:
    return segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#0f172a", light="#ffffff")


def new_recovery_codes() -> list[str]:
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def normalise_recovery_code(code: str) -> str:
    return code.strip().lower().replace(" ", "")


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(normalise_recovery_code(code).encode()).hexdigest()
