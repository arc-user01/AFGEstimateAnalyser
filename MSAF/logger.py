import logging
import redis
import json
import os
from datetime import datetime

class RedisLogHandler(logging.Handler):
    """
    A logging handler that pushes log messages to a Redis list.
    This enables real-time traceability for task execution.
    """
    def __init__(self, task_id):
        super().__init__()
        self.task_id = task_id
        # Configuration from environment
        redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        prefix = os.getenv("TRACEBILITY_QUEUE_PREFIX", "tracebility_queue:")
        
        self.redis_client = redis.from_url(redis_url)
        self.queue_name = f"{prefix}{task_id}"
        # Set an expiry on the log queue (e.g., 24 hours) to avoid memory bloat
        self.redis_client.expire(self.queue_name, 86400)

    def emit(self, record):
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": record.levelname,
                "message": self.format(record),
                "task_id": self.task_id,
                "module": record.module,
                "funcName": record.funcName
            }
            # Push to the tail of the list
            self.redis_client.rpush(self.queue_name, json.dumps(log_entry))
        except Exception:
            self.handleError(record)

def setup_task_logger(task_id, name="AgentTaskLogger"):
    """
    Helper to set up a logger with both Console and Redis handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if the logger is reused
    if not logger.handlers:
        # Console Handler
        c_handler = logging.StreamHandler()
        c_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        c_handler.setFormatter(c_format)
        logger.addHandler(c_handler)
        
        # Redis Handler for traceability
        r_handler = RedisLogHandler(task_id)
        r_format = logging.Formatter('%(message)s') # We include metadata in the JSON structure
        r_handler.setFormatter(r_format)
        logger.addHandler(r_handler)
        
    return logger
