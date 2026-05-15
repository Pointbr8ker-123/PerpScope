import os
import sys
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ALL_COINS, SLEEP_BETWEEN_CALLS
from collect_historical import fetch_funding_rates_page, fetch_klines_page
from backend.database.timescale import get_connection
from utils import log, now_ms


# Due to timescaledb free tier restrictions (750MB), there has to be a 
# limit to how many days of data for each coin to keep in the database.
# Older roww than the limit are deleted after each update runs thereby
# preventing the timescaledb 750MB free tier from filling up.

RETENTION_DAYS = 90

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
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (symbol,))
                result = cur.fetchone()

        if result and result['max'] is not None:
            return int(result['max']) + 1
        
    except Exception as e:
        log(f"[{symbol}] could not read last timestamp from {table}: {e}")

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

    log(f"Running data cleanup...")

    with get_connection() as conn:
        with conn.cursor() as cur:
            for table in tables:
                try:
                    cur.execute(
                        sql.format(table=table, days=RETENTION_DAYS)
                    )
                    deleted = cur.rowcount
                    if deleted > 0:
                        log(f"Cleaned {deleted:,} old rows from {table}")
                except Exception as e:
                    log(f"Cleanup error on {table}: {e}")
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
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
                return row['size_bytes'] / (1024 * 1024)
    except Exception:
        return 0.0
    

def update_funding_rates(symbol):
    """
    This function fetches funding rate records for a coin since the last
    stores timestamp and inserts them to the database
    """
    start_ms = get_last_timestamp_from_db(symbol, 'funding_rates')
    end_ms = now_ms()

    if start_ms >= end_ms:
        return 0
    
    records = fetch_funding_rates_page(
        symbol, start_ms, end_ms, limit=10
    )

    if not records:
        return 0
    
    rows = []
    for record in records:
        try:
            ts_ms = int(record['fundingRateTimestamp'])
            ts = datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc)
            rate = float(record['fundingRate'])
            rows.append((symbol, ts_ms, ts, rate))
        except (KeyError, ValueError) as e:
            log(f"[{symbol}] Bad funding record: {e}")

    if not rows:
        return 0
    
    sql = """
        INSERT INTO funding_rates
            (symbol, timestamp_ms, timestamp, funding_rate)
        VALUES
            (%s, %s, %s, %s)
        ON CONFLICT (symbol, timestamp_ms, timestamp) DO NOTHING
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()

    return len(rows)


def update_prices(symbol, category):
    """
    This function fetches new hourly OHLCV candles for a coin since
    the last
    """
    table = 'perp_prices' if category == 'linear' else 'spot_prices'
    start_ms = get_last_timestamp_from_db(symbol, table)
    end_ms = now_ms()

    if start_ms >= end_ms:
        return 0
    
    records = fetch_klines_page(
        symbol, category, start_ms, end_ms, limit=10
    )

    if not records:
        return 0
    
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
            log(f"[{symbol}] Bad kline record: {e}")

    if not rows:
        return 0
    
    sql = f"""
        INSERT INTO {table}
            (symbol, timestamp_ms, timestamp, 
            open, high, low, close, volume)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, timestamp_ms, timestamp) DO NOTHING
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()

    return len(rows)


def update_coin_funding_rates(symbol):
    """
    This function updates the funding_rates table in the database 
    for a single coin using the update_funding_rates helper function.
    """
    try:
        n_f = update_funding_rates(symbol)
        time.sleep(SLEEP_BETWEEN_CALLS)
        return (symbol, n_f, True)
    except Exception as e:
        log(f"[{symbol}] Funding rates update failed...")
        return (symbol, 0, False)
    

def update_coin_prices(symbol):
    """
    This function updates both perp_prices and spot_prices tables in
    the database for a single coin using the update_prices helper function.
    """
    try:
        n_p = update_prices(symbol, 'linear')
        time.sleep(SLEEP_BETWEEN_CALLS)
        n_s = update_prices(symbol, 'spot')
        time.sleep(SLEEP_BETWEEN_CALLS)
        return (symbol, n_p, n_s, True)
    except Exception as e:
        log(f"[{symbol}] Price update failed: {e}")
        return (symbol, 0, 0, False)
    

# ------------------------ Pipeline 1: Hourly Price Update ------------------------------
def run_price_update(max_workers=10):
    """
    This function is the Pipeline that runs every hour via Github actions
    
    Updates perp_prices and spot_prices for all coins and cleans up older rows
    after updating.
    """
    start_time = datetime.now()
    log(f"\n{'='*60}")
    log("PRICE UPDATE STARTED")
    log(f"Coins: {len(ALL_COINS)} | Workers: {max_workers}")
    log(f"\n{'='*60}")

    total_perp = 0
    total_spot = 0
    failed     = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(update_coin_prices, symbol): symbol
            for symbol in ALL_COINS
        }

        for future in as_completed(futures):
            symbol, n_p, n_s, success = future.result()

            if success:
                if n_p > 0 or n_s > 0:
                    log(f"{symbol}: +{n_p} perp, +{n_s} spot")
                total_perp += n_p
                total_spot += n_s
            else:
                failed.append(symbol)

    # Clean up old data after insertion
    cleanup_old_data()

    db_size = get_database_size()
    duration = (datetime.now() - start_time).seconds

    log(f"\nPrice update complete in {duration}s")
    log(f"New row: {total_perp:,} perp | {total_spot:,} spot")
    log(f"Database size: {db_size:.1f} MB / 750MB")

    if failed:
        log(f"Failed coins ({len(failed)}): {failed[:10]}")

    if db_size > 400:
        log(f"WARNING: Database is {db_size:.0f}MB - approaching 750MB limit!")
        log(f"Consider reducing RETENTION_DAYS from {RETENTION_DAYS} to {RETENTION_DAYS/1.5}")


# --------------------------Pipeline 2: 8-hour Funding Rates Update ---------------------------------
def run_funding_rates_update(max_workers=10):
    """
    This function represents the second pipeline that runs every 8hrs via
    Github actions.

    Updates funding rates for all coins.
    """
    start_time = datetime.now()
    log(f"\n{'='*60}")
    log("FUNDING RATES UPDATE STARTED")
    log(f"Coins: {len(ALL_COINS)} | Workers: {max_workers}")
    log(f"\n{'='*60}")

    total_funding = 0
    failed = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(update_funding_rates, symbol): symbol
            for symbol in ALL_COINS
        }

        for future in as_completed(futures):
            symbol, n_f, success = future.result()

            if success:
                if n_f > 0:
                    log(f"{symbol}: +{n_f} rate")
                total_funding += n_f
            else:
                failed.append(symbol)

    cleanup_old_data()

    db_size = get_database_size()
    duration = (datetime.now() - start_time).seconds

    log(f"\nFunding update complete in {duration}s")
    log(f"New rows: {total_funding:,} funding rates")
    log(f"Database size: {db_size:.1f}MB / 750MB")

    if failed:
        log(f"Failed coins ({len(failed)}): {failed[:10]}...")


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