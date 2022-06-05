import logging


_logger = logging.getLogger("BabyBrowser")

def get_logger(name: str):
    return _logger.getChild(name)
