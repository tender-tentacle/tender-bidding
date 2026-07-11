import logging
import sys


def setup_logger(name: str, service: str = "bidding") -> logging.Logger:
    """Structured-ish stdout logger, consistent with the other services."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(f"%(asctime)s [{service}] %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
