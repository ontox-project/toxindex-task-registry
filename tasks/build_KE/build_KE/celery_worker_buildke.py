import os
import logging
from webserver.logging_utils import setup_logging, log_service_startup, get_logger

# Remove print statements and use env vars for Redis URLs
broker_url = os.environ.get("CELERY_BROKER_URL")
result_backend = os.environ.get("CELERY_RESULT_BACKEND")

from workflows.celery_app import celery

# Import ONLY the buildke task
import build_KE.build_KE_celery # noqa: F401

def setup_celery_worker():
    """Setup logging and startup for celery worker - only call this when actually starting a worker"""
    # Setup logging with shared utility
    setup_logging("celery-worker-buildke", log_level=logging.INFO)
    logger = get_logger("celery-worker-buildke")

    # Log startup information
    log_service_startup("celery-worker-buildke")

    # Log registered tasks
    logger.info(f"Registered tasks: {list(celery.tasks.keys())}")

# Only setup logging if this module is run directly (i.e., as a celery worker)
if __name__ == '__main__':
    setup_celery_worker()