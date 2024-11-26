import logging
import os


def setup_logging(name, log_level="WARNING"):
    LOG_DIR = os.path.join(os.getcwd(), "__norfab__", "logs")
    LOG_FILE = os.path.join(LOG_DIR, "norfab.log")
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.root.handlers = []
    console_logger = logging.StreamHandler()
    console_logger.setLevel(log_level)
    file_logger = logging.FileHandler(LOG_FILE, mode="a", delay=False, encoding="utf-8")
    file_logger.setLevel(log_level)
    logging.basicConfig(
        format="%(asctime)s.%(msecs)d %(levelname)s [%(name)s:%(lineno)d ] -- %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level="WARNING",
        handlers=[
            console_logger,
            file_logger,
        ],
    )
    log = logging.getLogger(name)

    return log
