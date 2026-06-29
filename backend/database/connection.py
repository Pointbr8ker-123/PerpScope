# connection.py - Thread-safe connection pooling for the PerpScope data pipeline
#
# The update script processes 300+ coins with multiple workers. Without pooling,
# each worker would open a new connection per coin, causing:
# - Connection churn (300+ connections per update run)
# - Risk of hitting Supabase's connection limit
# - Slower performance (each connection handshake takes time)
#
# This module provides a shared pool that workers borrow from and return to,
# ensuring we never exceed 5 concurrent connections.

import psycopg2
import threading
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from psycopg2.extras import RealDictCursor
from backend.database.db_config import SUPABASE_DATABASE_URL
from src.utils import log_info, log_warn


_pool      = None
_pool_lock = threading.Lock()


def create_pool(min_connections=2, max_connections=5):
    """
    This function creates the connection pool for an update run.
    It'd be called once at the start of the run_price_update() and 
    run_funding_rates_update() functions in update_data.py
    """
    global _pool

    with _pool_lock:
        if _pool is not None:
            log_warn("Pool already exists - skipping creation")
            return
        
        _pool = ThreadedConnectionPool(
            # ThreadedConnectionPool is safer to use in this context than 
            # SimpleConnectionPool in order to avoid random errors when 
            # multiple threads borrow connections.
            minconn=min_connections,
            maxconn=max_connections,
            dsn=SUPABASE_DATABASE_URL,
            cursor_factory=RealDictCursor 
            # RealDictCursor return rows as dictionaries which matches 
            # with what the rest of the codebase expects.
        )
        log_info(
            f"Connection pool created "
            f"(min={min_connections}, max={max_connections})"
        )


def close_pool():
    """
    This function closes all connections in the pool.
    It'd be called once at the end of the run_price_update() and 
    run_funding_rates_update() functions in update_data.py
    """
    global _pool

    with _pool_lock:
        if _pool is None:
            return
        _pool.closeall()
        _pool = None
        log_info("Connection pool closed")


@contextmanager
def get_pooled_connection():
    """
    This function is a context manager that borrows a connection from
    the pool, yields it for use, and returns it when its done.
    """
    if _pool is None:
        raise RuntimeError(
            "Connection pool is not initialized "
            "Call create_pool() before using get_pooled_connection()"
        )
    
    conn = None
    try:
        conn = _pool.getconn()
        yield conn
    except Exception:
        if conn:
            try:
                # rollback any open transactions to prevent it from
                # lingering and blocking other operations.
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn and _pool:
            # Always return the connetion whether there was
            # an error not not. If we don't, the pool will
            # eventually exhaust and the script will hang
            _pool.putconn(conn)


def get_connection():
    """
    This function connects to our Supabase database for time-series 
    and user management data.

    Returns a non-pooled connection.
    """
    return psycopg2.connect(
        SUPABASE_DATABASE_URL,
        cursor_factory=RealDictCursor
    )
