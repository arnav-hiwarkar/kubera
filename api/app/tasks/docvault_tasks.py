import os
import subprocess
from datetime import datetime
from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.config import get_settings

logger = get_task_logger(__name__)

@celery_app.task
def backup_vault_and_db():
    """
    Nightly Celery Beat job to backup the database and the document vault.
    Creates a pg_dump and a tarball of /data/vault, moving them to BACKUP_DESTINATION_PATH.
    """
    settings = get_settings()
    dest_path = settings.backup_destination_path
    vault_path = settings.vault_storage_path
    
    # Ensure backup directory exists
    os.makedirs(dest_path, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_backup_file = os.path.join(dest_path, f"db_backup_{timestamp}.sql")
    vault_backup_file = os.path.join(dest_path, f"vault_backup_{timestamp}.tar.gz")
    
    # We use sync_database_url but replace asyncpg/psycopg2 dialect part for pg_dump
    db_url = settings.sync_database_url
    if db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    elif db_url.startswith("sqlite"):
        db_url = "" # Ignore sqlite for pg_dump
    
    logger.info(f"Starting backup process. DB: {db_backup_file}, Vault: {vault_backup_file}")
    
    if db_url:
        # Run pg_dump
        try:
            env = os.environ.copy()
            # Prevent password prompt if included in URL or set via pgpass, pg_dump accepts DB URL
            subprocess.run(
                ["pg_dump", "--dbname", db_url, "-f", db_backup_file],
                check=True,
                env=env,
                capture_output=True
            )
            logger.info("Database backup completed successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Database backup failed: {e.stderr.decode()}")
            raise
    
    # Run tar for vault
    if os.path.exists(vault_path):
        try:
            subprocess.run(
                ["tar", "-czf", vault_backup_file, "-C", os.path.dirname(vault_path), os.path.basename(vault_path)],
                check=True,
                capture_output=True
            )
            logger.info("Vault backup completed successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Vault backup failed: {e.stderr.decode()}")
            raise
    else:
        logger.warning(f"Vault path {vault_path} does not exist, skipping vault backup.")
        
    logger.info("Backup process finished successfully.")
