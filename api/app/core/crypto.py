import os
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

def get_kek() -> bytes:
    kek_hex = get_settings().vault_kek
    if not kek_hex:
        raise ValueError("VAULT_KEK is not set in environment")
    return bytes.fromhex(kek_hex)

def generate_dek() -> bytes:
    """Generate a random 32-byte (256-bit) Data Encryption Key."""
    return secrets.token_bytes(32)

def encrypt_dek(dek: bytes) -> str:
    """Encrypt the DEK using the KEK via AES-256-GCM. Returns hex string."""
    kek = get_kek()
    aesgcm = AESGCM(kek)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, dek, None)
    return (nonce + ciphertext).hex()

def decrypt_dek(encrypted_dek_hex: str) -> bytes:
    """Decrypt the DEK using the KEK."""
    kek = get_kek()
    encrypted_data = bytes.fromhex(encrypted_dek_hex)
    nonce = encrypted_data[:12]
    ciphertext = encrypted_data[12:]
    aesgcm = AESGCM(kek)
    return aesgcm.decrypt(nonce, ciphertext, None)

def encrypt_file_data(dek: bytes, data: bytes) -> bytes:
    """Encrypt file bytes using the DEK via AES-256-GCM."""
    aesgcm = AESGCM(dek)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext

def decrypt_file_data(dek: bytes, encrypted_data: bytes) -> bytes:
    """Decrypt file bytes using the DEK."""
    nonce = encrypted_data[:12]
    ciphertext = encrypted_data[12:]
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, ciphertext, None)
