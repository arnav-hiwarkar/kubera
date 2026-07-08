"""
Minimal Celery application stub.
Workers and Beat scheduler reference this. Background tasks will be
added in Phase 1+ as modules are built.
"""
from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "kubera",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[],  # task modules added here per phase
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
)
