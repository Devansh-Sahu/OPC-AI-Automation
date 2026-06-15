import logging
import json
from datetime import datetime, timezone
import base64
from cryptography.fernet import Fernet
from cryptography.exceptions import InvalidToken
from backend.core.config import settings

logger = logging.getLogger(__name__)

class SecretsManager:
    def __init__(self):
        # EnsureFERNET_KEY is present and valid
        try:
            key = settings.FERNET_KEY.encode() if isinstance(settings.FERNET_KEY, str) else settings.FERNET_KEY
            self.fernet = Fernet(key)
        except Exception as e:
            logger.warning(f"Failed to initialize Fernet with provided key. Generating fallback key for this session. Error: {e}")
            self.fernet = Fernet(Fernet.generate_key())

    def encrypt_secret(self, secret: str) -> str:
        """Encrypt a string secret and return the base64 encoded encrypted string."""
        if not secret:
            return ""
        try:
            encrypted_bytes = self.fernet.encrypt(secret.encode('utf-8'))
            return base64.b64encode(encrypted_bytes).decode('utf-8')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError("Failed to encrypt secret")

    def decrypt_secret(self, encrypted_secret: str) -> str:
        """Decrypt a base64 encoded encrypted string."""
        if not encrypted_secret:
            return ""
        try:
            encrypted_bytes = base64.b64decode(encrypted_secret.encode('utf-8'))
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except (InvalidToken, ValueError) as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError("Failed to decrypt secret. Key might have changed.")

secrets_manager = SecretsManager()
