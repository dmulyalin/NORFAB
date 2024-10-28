import logging
import os


def setup_logging(name):
    LOG_DIR = os.path.join(os.getcwd(), "__norfab__", "logs")
    LOG_FILE = os.path.join(LOG_DIR, "norfab.log")
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.root.handlers = []
    logging.basicConfig(
        format="%(asctime)s.%(msecs)d %(levelname)s [%(name)s:%(lineno)d ] -- %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level="WARNING",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, mode="a", delay=False, encoding="utf-8"),
        ],
    )
    log = logging.getLogger(name)

    return log
