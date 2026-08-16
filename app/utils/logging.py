"""Small logging setup seam for application modules."""

import logging


def get_logger(name):
    """Return a consistently named standard-library logger."""
    return logging.getLogger(name)

