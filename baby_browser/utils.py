from functools import wraps
from logging import Logger
from time import time_ns


def format_bytes(num: float, suffix="B"):
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Y{suffix}"


def timed(logger: Logger):
    def timed_inner(f):
        @wraps(f)
        def wrapper(*args, **kwds):
            start = time_ns()

            result = f(*args, **kwds)

            elapsed = (time_ns() - start) / 1_000_000

            logger.debug(f"{f.__name__} took {elapsed} ms")

            return result

        return wrapper

    return timed_inner


def tree_to_list(tree, flat: list):
    flat.append(tree)
    for child in tree.children:
        tree_to_list(child, flat)
    return flat
