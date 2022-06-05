import logging


logging.basicConfig(level=logging.DEBUG, format='%(message)s')
_logger = logging.getLogger("BabyBrowser")
_logger.setLevel(logging.DEBUG)

def get_logger(name: str):
    return _logger.getChild(name)
