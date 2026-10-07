from cryptography.fernet import Fernet, InvalidToken

from app.errors import UserError


class SecretBox:
    def __init__(self, key: str = ""):
        self.fernet = Fernet(key.encode() if key else Fernet.generate_key())

    def seal(self, text: str) -> bytes:
        return self.fernet.encrypt(text.encode())

    def open(self, blob: bytes) -> str:
        try:
            return self.fernet.decrypt(blob).decode()
        except InvalidToken as exc:
            raise UserError("The stored API key can no longer be read. Please enter it again.", "key_unreadable", 400) from exc
