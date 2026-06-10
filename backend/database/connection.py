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
            minconn=min_connections,
            maxconn=max_connections,
            dsn=SUPABASE_DATABASE_URL,
            cursor_factory=RealDictCursor
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
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn and _pool:
            _pool.putconn(conn)


def get_connection():
    """
    This function connects to TimescaleDB  for time-series data.

    Used by: calculate_rho.py, update_data.py, main.py data endpoints
    
    Tables here: funding_rates, perp_prices, spot_prices,
                coin_universe, collection_progress

    Returns a non-pooled connection.
    """
    return psycopg2.connect(
        SUPABASE_DATABASE_URL,
        cursor_factory=RealDictCursor
    )