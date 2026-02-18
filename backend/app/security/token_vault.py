import base64
from cryptography.fernet import Fernet, InvalidToken


class TokenVault:
    def __init__(self, raw_key: str | None):
        self._cipher = None

        if raw_key:
            key = raw_key.encode("utf-8")
            # Fernet key must be URL-safe base64-encoded 32-byte key.
            if len(key) != 44:
                key = base64.urlsafe_b64encode(raw_key.encode("utf-8").ljust(32, b"0")[:32])
            self._cipher = Fernet(key)

    def encrypt(self, token: str) -> str:
        if not self._cipher:
            return token
        return self._cipher.encrypt(token.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> str:
        if not self._cipher:
            return token
        try:
            return self._cipher.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Backward-compatibility: allow legacy plain tokens during migration.
            return token
