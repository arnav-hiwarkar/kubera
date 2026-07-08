import hashlib
import os
import uuid
from typing import Tuple

from fastapi import UploadFile

from app.config import get_settings
from app.core.crypto import (
    decrypt_dek,
    decrypt_file_data,
    encrypt_dek,
    encrypt_file_data,
    generate_dek,
)


async def save_document(company_id: uuid.UUID, file: UploadFile) -> Tuple[str, int, str, str]:
    """
    Saves an uploaded file to disk.
    Returns: (storage_path, size_bytes, checksum, encrypted_dek)
    """
    settings = get_settings()
    base_path = settings.vault_storage_path
    
    # Ensure company directory exists
    company_dir = os.path.join(base_path, str(company_id))
    os.makedirs(company_dir, exist_ok=True)
    
    file_uuid = uuid.uuid4()
    storage_path = os.path.join(company_dir, f"{file_uuid}.enc")
    
    # Read file data
    file_data = await file.read()
    size_bytes = len(file_data)
    
    # Checksum
    checksum = hashlib.sha256(file_data).hexdigest()
    
    # Encrypt
    dek = generate_dek()
    encrypted_dek = encrypt_dek(dek)
    encrypted_data = encrypt_file_data(dek, file_data)
    
    # Write to disk
    with open(storage_path, "wb") as f:
        f.write(encrypted_data)
        
    return storage_path, size_bytes, checksum, encrypted_dek


def load_document(storage_path: str, encrypted_dek: str) -> bytes:
    """
    Loads and decrypts a document from disk into memory.
    """
    dek = decrypt_dek(encrypted_dek)
    with open(storage_path, "rb") as f:
        encrypted_data = f.read()
    
    return decrypt_file_data(dek, encrypted_data)


def delete_document_file(storage_path: str) -> None:
    """Deletes a file from disk if it exists."""
    if os.path.exists(storage_path):
        os.remove(storage_path)
