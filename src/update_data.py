import psycopg2.extras
import os
import sys
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import ALL_COINS
from src.collect_historical import fetch_funding_rates_page, fetch_klines_page
from src.calculate_rho import calculate_current_opportunities
from src.telegram_alerts import check_and_send_alerts
from src.utils import log_info, log_warn, log_err, now_ms

from backend.database.timescale import (
    create_pool,
    close_pool,
    get_pooled_connection,
)


# Due to timescaledb free tier restrictions (750MB), there has to be a 
# limit to how many days of data for each coin to keep in the database.

# Older rows than the limit are deleted after each update runs thereby
# preventing the timescaledb (750MB) free tier from filling up.

RETENTION_DAYS = 90
BATCH_SIZE     = 50     # insert this many rows per database commit
MAX_WORKERS    = 5      # max number of Bybit API workers
POOL_MIN       = 2      # minimum pool connections
POOL_MAX       = 5      # maximum pool connections


def get_last_timestamp_from_db(symbol, table):
    """
    This function gets the most recent timestamp_ms for a particular symbol
    of a particular table in the database
    """
    sql = f"""
        SELECT MAX(timestamp_ms)
        FROM {table}
        WHERE symbol = %s
    """

    try:
        with get_pooled_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (symbol,))
                result = cur.fetchone()

        if result and result['max'] is not None:
            return int(result['max']) + 1
        
    except Exception as e:
        log_err(f"[{symbol}] could not read last timestamp from {table}: {e}")

    ninety_days_ms = RETENTION_DAYS * 24 * 60 * 60 * 1000
    return now_ms() - ninety_days_ms


def cleanup_old_data():
    """
    This function deletes rows older than the RETENTION_DAYS (i.e 90 days)
    from the three time-series tables

    This keeps the database size from exceeding the timescaledb 750MB limit
    """
    tables = ['funding_rates', 'perp_prices', 'spot_prices']

    sql = """
        DELETE from {table}
        WHERE timestamp < NOW() - INTERVAL '{days} days'
    """

    log_info(f"Running data cleanup...")

    with get_pooled_connection() as conn:
        with conn.cursor() as cur:
            for table in tables:
                try:
                    cur.execute(
                        sql.format(table=table, days=RETENTION_DAYS)
                    )
                    deleted = cur.rowcount
                    if deleted > 0:
                        log_info(f"Cleaned {deleted:,} old rows from {table}")
                except Exception as e:
                    log_err(f"Cleanup error on {table}: {e}")
        conn.commit()


def get_database_size():
    """
    This function returns the current size of the timescaledb database in MB.
    """
    sql = """
        SELECT 
            pg_size_pretty(pg_database_size(current_database())) AS size,
            pg_database_size(current_database()) AS size_bytes
    """

    try:
        with get_pooled_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
                return row['size_bytes'] / (1024 * 1024)
    except Exception:
        return 0.0
    

def fetch_new_funding_rates(symbol):
    """
    This function fetches funding rate records for a coin since the last
    stores timestamp and inserts them to the database
    """
    start_ms = get_last_timestamp_from_db(symbol, 'funding_rates')
    end_ms   = now_ms()

    if start_ms >= end_ms:
        return []
    
    records = fetch_funding_rates_page(
        symbol, start_ms, end_ms, limit=10
    )

    if not records:
        return []
    
    rows = []
    for record in records:
        try:
            ts_ms = int(record['fundingRateTimestamp'])
            ts    = datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc)
            rate  = float(record['fundingRate'])
            rows.append((symbol, ts_ms, ts, rate))
        except (KeyError, ValueError) as e:
            log_err(f"[{symbol}] Bad funding record: {e}")
            continue

    return rows


def batch_insert_funding_rates(rows):
    """
    This function inserts a batch of funding rate rows in a single database 
    commit and returns the number of rows inserted
    """
    if not rows:
        return 0
    
    sql = """
        INSERT INTO funding_rates
            (symbol, timestamp_ms, timestamp, funding_rate)
        VALUES %s
        ON CONFLICT (symbol, timestamp_ms, timestamp) DO NOTHING
    """

    with get_pooled_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, rows, page_size=BATCH_SIZE)
        conn.commit()

    return len(rows)


def fetch_new_prices(symbol, category):
    """
    This function fetches new hourly OHLCV candles for a coin since
    the last timestamp_ms in the database
    """
    table    = 'perp_prices' if category == 'linear' else 'spot_prices'
    start_ms = get_last_timestamp_from_db(symbol, table)
    end_ms   = now_ms()

    if start_ms >= end_ms:
        return []
    
    records = fetch_klines_page(
        symbol, category, start_ms, end_ms, limit=10
    )

    if not records:
        return []
    
    rows = []
    for record in records:
        try:
            ts_ms   = int(record[0])
            ts      = datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc)
            open_   = float(record[1])
            high    = float(record[2])
            low     = float(record[3])
            close   = float(record[4])
            volume  = float(record[5])
            rows.append((symbol, ts_ms, ts, open_, high, low, close, volume))
        except (IndexError, ValueError) as e:
            log_err(f"[{symbol}] Bad kline record: {e}")
            continue

    return rows


def batch_insert_prices(rows, table):
    """
    This function inserts a batch of price rows into perp_prices or spot_prices
    tables in the database.
    """
    if not rows:
        return 0
    
    if table not in ('perp_prices', 'spot_prices'):
        raise ValueError(f"Invalid table name: {table}")
    
    sql = f"""
        INSERT INTO {table}
            (symbol, timestamp_ms, timestamp, 
            open, high, low, close, volume)
        VALUES %s
        ON CONFLICT (symbol, timestamp_ms, timestamp) DO NOTHING
    """

    with get_pooled_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, rows, page_size=BATCH_SIZE)
        conn.commit()

    return len(rows)
    

# -------------------------- Batch Collector -------------------------------------------
def collect_all_rows_parallel(coins, fetch_func, max_workers):
    """
    This function runs fetch_func for every coin in parallel using worker threads.
    Then collects all returned rows into a single list

    fetch_func: function (like 'update_funding_rates()' and 'update_prices()' that takes a 
    symbol and returns a list of rows.

    This function returns all the rows from all the coins combined as a list.
    """    
    all_rows = []
    failed   = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_func, symbol): symbol
            for symbol in  coins
        }

        for future in as_completed(futures):
            symbol = futures[future]
            try:
                rows = future.result()
                if rows:
                    all_rows.extend(rows)
            except Exception as e:
                log_info(f"Fetch failed for {symbol}: {e}")
                failed.append(symbol)

    if failed:
        log_err(f"{len(failed)} coins failed to fetch")

    return all_rows


def insert_in_batches(rows, insert_func, table_name):
    """
    This function takes a list of rows and inserts them in batches.
    This significantly reduces the total number of single data transactions.
    """
    if not rows:
        return 0
    
    total_inserted = 0
    batch_count    = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        try:
            n = insert_func(batch)
            total_inserted += n
            batch_count += 1
        except Exception as e:
            log_err(f"Batch insert failed for {table_name} "
                     f"(batch {batch_count + 1}): {e}")
            
    log_info(f"{table_name}: {total_inserted} rows in {batch_count} batches")
    return total_inserted


# ------------------------ Pipeline 1: Hourly Price Update ------------------------------
def run_price_update():
    """
    This function is the Pipeline that runs every hour via cron-job.org trigger.
    
    Updates perp_prices and spot_prices for all coins and cleans up older rows
    after updating.
    """
    start_time = datetime.now()
    log_info(f"\n{'='*60}")
    log_info("PRICE UPDATE STARTED")
    log_info(f"Coins: {len(ALL_COINS)} | Workers: {MAX_WORKERS} | Pool: {POOL_MAX}")
    log_info(f"\n{'='*60}")

    # Initialize pool for this run
    create_pool(min_connections=POOL_MIN, max_connections=POOL_MAX)

    try:
        # Fetch perp prices in parallel
        log_info("Fetching perpetual prices from Bybit...")
        perp_rows = collect_all_rows_parallel(
            ALL_COINS,
            lambda symbol: fetch_new_prices(symbol, 'linear'),
            MAX_WORKERS
        )
        log_info(f"Fetched {len(perp_rows):,} perp price rows")

        # Insert fetched perp prices in batches
        log_info("Inserting perpetual prices...")
        total_perp = insert_in_batches(
            perp_rows,
            lambda rows: batch_insert_prices(rows, 'perp_prices'),
            'perp_prices'
        )

        # Fetch spot prices in parallel
        log_info("Fetching spot prices from Bybit...")
        spot_rows = collect_all_rows_parallel(
            ALL_COINS,
            lambda symbol: fetch_new_prices(symbol, 'spot'),
            MAX_WORKERS
        )
        log_info(f"Fetched {len(spot_rows):,} spot price rows")

        # Insert fetched spot prices in batches
        log_info("Inserting spot prices...")
        total_spot = insert_in_batches(
            spot_rows,
            lambda rows: batch_insert_prices(rows, 'spot_prices'),
            'spot_prices'
        )

        # Cleanup
        log_info("Running cleanup")
        cleanup_old_data()

        db_size = get_database_size()
        duration = (datetime.now() - start_time).seconds

        log_info(f"\nPrice update complete in {duration}s")
        log_info(f"New row: {total_perp:,} perp | {total_spot:,} spot")
        log_info(f"Database size: {db_size:.1f} MB / 750MB")

        if db_size > 400:
            log_warn(f"WARNING: Database is {db_size:.0f}MB - approaching 750MB limit!")
            log_warn(f"Consider reducing RETENTION_DAYS from {RETENTION_DAYS} to {RETENTION_DAYS/1.5}")

    finally:
        # Close pool, no matter what
        close_pool()

    # Alert engine runs after pool is closed
    try:
        opps_df = calculate_current_opportunities(threshold_tier='high')
        if not opps_df.empty:
            opps_list = opps_df.to_dict('records')
            alerts_sent = check_and_send_alerts(opps_list)
            log_info(f"Alert engine: {alerts_sent} alerts sent")

    except Exception as e:
        log_err(f"Alert engine error: {e}")


# --------------------------Pipeline 2: 8-hour Funding Rates Update ---------------------------------
def run_funding_rates_update(max_workers=5):
    """
    This function represents the second pipeline that runs every 8hrs via
    Github actions.

    Updates funding rates for all coins.
    """
    start_time = datetime.now()
    log_info(f"\n{'='*60}")
    log_info("FUNDING RATES UPDATE STARTED")
    log_info(f"Coins: {len(ALL_COINS)} | Workers: {max_workers}")
    log_info(f"\n{'='*60}")

    create_pool(min_connections=POOL_MIN, max_connections=POOL_MAX)

    try:
        # Fetch all the funding rates in parallel
        log_info("Fetching funding rates from Bybit...")    
        funding_rows = collect_all_rows_parallel(
            ALL_COINS,
            fetch_new_funding_rates,
            MAX_WORKERS
        )
        log_info(f"Fetched {len(funding_rows):,} funding rate rows")

        # Insert funding rates in batches to the database
        log_info("Inserting funding rates...")
        total_funding = insert_in_batches(
            funding_rows,
            batch_insert_funding_rates,
            'funding_rates'
        )

        # Cleanup
        log_info("Running cleanup...")
        cleanup_old_data()

        db_size = get_database_size()
        duration = (datetime.now() - start_time).seconds

        log_info(f"\nFunding update complete in {duration}s")
        log_info(f"New rows: {total_funding:,} funding rates")
        log_info(f"Database size: {db_size:.1f}MB / 750MB")

    finally:
        close_pool()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else 'both'

    if mode == 'prices':
        run_price_update()
    elif mode == 'funding':
        run_funding_rates_update()
    elif mode == 'both':
        run_funding_rates_update()
        run_price_update()
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)