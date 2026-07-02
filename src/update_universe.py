# src/update_universe.py (import from get_universe)

# Updates the historical universe table with the current set of active
# perpetual contracts from Bybit.

# This script would run weekly via cron job

from datetime import datetime, timezone
from backend.database.connection import get_connection
from src.get_universe import get_all_linear_perpetuals
from src.utils import log_info

def update_universe():
    """
    Inserts a new snapshot of active symbols into the historical_universe table.
    """
    # Use the existing function
    symbols = get_all_linear_perpetuals()
    if not symbols:
        return 0

    snapshot_date = datetime.now(timezone.utc)

    sql = """
        INSERT INTO historical_universe
            (snapshot_date, symbol, status, launch_time_ms, quote_coin)
        SELECT %s, %s, %s, %s, %s
        WHERE EXISTS (
            SELECT 1 FROM coin_universe
            WHERE symbol = %s AND is_active = true
        )
        ON CONFLICT (snapshot_date, symbol) DO NOTHING
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            inserted = 0
            for item in symbols:
                cur.execute(sql, (
                    snapshot_date,
                    item['symbol'],
                    item['status'],
                    item['launch_time_ms'],
                    'USDT'  # All linear perpetuals are USDT-settled
                ))
                inserted += 1
        conn.commit()

    log_info(f"Inserted {inserted} symbols into historical_universe")
    return inserted


def sync_coin_universe_table():
    """
    Syncs coin_universe table with the latest historical_universe snapshot.

    New symbols on Bybit but not yet in coin_universe -> inserted with
    placeholder tier 'SMALL' until get_market_caps.py classified them properly.

    Symbols which are no longer Trading in the latest snapshot are marked inactive.
    """
    # Insert newly discovered symbols
    insert_sql = """
        WITH latest AS (
            SELECT symbol, launch_time_ms
            FROM historical_universe
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM historical_universe)
            AND status = 'Trading'
        )
        INSERT INTO coin_universe (symbol, name, market_cap_tier, market_cap_rank, is_active)
        SELECT
            l.symbol,
            REPLACE(l.symbol, 'USDT', ''),
            'SMALL',
            9999,
            true
        FROM latest l
        LEFT JOIN coin_universe cu on cu.symbol = l.symbol
        WHERE cu.symbol IS NULL
    """

    # Mark delisted symbols inactive
    # Conservative deactivation - absent from last 3 snapshots 
    # before deactivation
    deactivate_sql = """
        WITH recent_snapshots AS (
            SELECT DISTINCT snapshot_date
            FROM historical_universe
            ORDER BY snapshot_date DESC
            LIMIT 3
        ),
        snapshot_count AS (
            SELECT COUNT(*) AS n FROM recent_snapshots
        ),
        absent_coins AS (
            SELECT cu.symbol
            FROM coin_universe cu
            CROSS JOIN snapshot_count sc
            WHERE cu.is_active = true
                AND sc.n >= 3
                AND NOT EXISTS (
                    SELECT 1
                    FROM historical_universe hu
                    WHERE hu.symbol = cu.symbol
                        AND hu.status = 'Trading'
                        AND hu.snapshot_date IN (SELECT snapshot_date FROM recent_snapshots)
                )
        )
        UPDATE coin_universe
        SET is_active = false
        WHERE symbol IN (SELECT symbol FROM absent_coins)
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(insert_sql)
            new_count = cur.rowcount
            cur.execute(deactivate_sql)
            deactivated_count = cur.rowcount
        conn.commit()

    log_info(f"coin_universe sync: {new_count} new symbols added, "
             f"{deactivated_count} symbols marked inactive "
             f"absent from last 3 consecutive weekly snapshots")


if __name__== "__main__":
    # update_universe()
    sync_coin_universe_table()
