import os
import logging
from datetime import datetime, timezone


def date_to_ms(year, month, day):
    """
    This function converts a date to Unix timestamp in milliseconds
    which is the format that bybit uses.
    """
    dt = datetime(year, month, day, tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def now_ms():
    """
    This function returns the current time as Unix timestamps in milliseconds.
    """
    return int(datetime.now(timezone.utc).timestamp() * 1000)


logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def log_info(msg):
    logger.info(msg)

def log_warn(msg):
    logger.warning(msg)

def log_err(msg):
    logger.error(msg)