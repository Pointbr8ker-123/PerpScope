import os
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


def log(message, log_file='collection_log.txt'):
    """
    This function prints a message and also writes it to a log file
    so I can track events even when my terminal is closed.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_message = f"[{timestamp}] {message}"
    print(full_message)
    with open(os.path.join(base_dir, log_file), 'a') as f:
        f.write(full_message + '\n\n')


