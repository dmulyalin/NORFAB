import logging
import os


def setup_logging(filename=None, queue=None, log_level="WARNING"):
    handlers = []

    console_logger = logging.StreamHandler()
    console_logger.setLevel(log_level)
    handlers.append(console_logger)

    if filename is not None:
        LOG_DIR = os.path.join(os.getcwd(), "__norfab__", "logs")
        os.makedirs(LOG_DIR, exist_ok=True)
        LOG_FILE = os.path.join(LOG_DIR, filename)
        file_logger = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            mode="a",
            delay=False,
            encoding="utf-8",
            maxBytes=1024000,
            backupCount=50,
        )
        file_logger.setLevel(log_level)
        handlers.append(file_logger)

    if queue is not None:
        queue_handler = logging.handlers.QueueHandler(queue)
        queue_handler.setLevel(log_level)
        handlers.append(queue_handler)

    logging.basicConfig(
        format="%(asctime)s.%(msecs)d %(levelname)s [%(name)s:%(lineno)d ] -- %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=log_level,
        handlers=handlers,
        force=True,
    )
