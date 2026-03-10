import logging

# Redis/Celery removed: logging is console-only. Functionality unchanged.


def setup_task_logger(task_id, name="AgentTaskLogger"):
    """
    Set up a logger with a console handler for task execution.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        c_handler = logging.StreamHandler()
        c_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        c_handler.setFormatter(c_format)
        logger.addHandler(c_handler)

    return logger
