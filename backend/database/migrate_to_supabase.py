# Due to the fact that the TimescaleDB free tier is expiring in a few days
# (which I didn't realize on time), it'd be better if I moved the entire DB
# back to supabase since there's the 90-day rolling retention in place which
# would help conserve what little space I'd be working with on supabase.

# In the future - when I want to scale the platform and probably can afford 
# TimescaleDB pro plans - I can split the DB again. So for now, I'm keeping 
# the timescale.py script.

import psycopg2
import psycopg2.extras
import time
from backend.database.timescale import get_connection
from backend.database.supabase import get_supabase_connection


BATCH_SIZE = 5000

def count_rows(conn, table):
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
        return cur.fetchone()['n']
    

def migrate_funding_rates(ts_conn, sb_conn):
    """Migrates all funding_rates rows from TimescaleDB to Supabase."""

    print("\nMigrating funding_rates...")

    total = count_rows(ts_conn, 'funding_rates')
    print(f"  Source rows: {total:,}")

    migrated = 0
    offset   = 0

    insert_sql = """
        INSERT INTO funding_rates
            (symbol, timestamp_ms, timestamp, funding_rate)
        VALUES %s
        ON CONFLICT (symbol, timestamp_ms, timestamp) DO NOTHING
    """

    while True:
        # Read a batch from TimescaleDB
        with ts_conn.cursor() as cur:
            cur.execute("""
                SELECT symbol, timestamp_ms, timestamp, funding_rate
                FROM funding_rates
                ORDER BY timestamp_ms ASC
                LIMIT %s OFFSET %s
            """, (BATCH_SIZE, offset))
            rows = cur.fetchall()

        if not rows:
            break

        # Convert to list of tuples for execute_values
        tuples = [
            (r['symbol'], r['timestamp_ms'], r['timestamp'], r['funding_rate'])
            for r in rows
        ]

        # Write batch to Supabase
        with sb_conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, insert_sql, tuples)
        sb_conn.commit()

        migrated += len(rows)
        offset   += BATCH_SIZE
        pct       = (migrated / total * 100) if total > 0 else 0
        print(f"  Progress: {migrated:,}/{total:,} ({pct:.1f}%)", end='\r')

        # Small pause to avoid overwhelming Supabase
        time.sleep(0.1)

    print(f"\n  Done: {migrated:,} rows migrated")
    return migrated


def migrate_prices(ts_conn, sb_conn, table):
    """Migrates all rows from a price table (perp_prices or spot_prices)."""

    print(f"\nMigrating {table}...")

    total = count_rows(ts_conn, table)
    print(f"  Source rows: {total:,}")

    migrated = 0
    offset   = 0

    insert_sql = f"""
        INSERT INTO {table}
            (symbol, timestamp_ms, timestamp,
             open, high, low, close, volume)
        VALUES %s
        ON CONFLICT (symbol, timestamp_ms, timestamp) DO NOTHING
    """

    while True:
        with ts_conn.cursor() as cur:
            cur.execute(f"""
                SELECT symbol, timestamp_ms, timestamp,
                       open, high, low, close, volume
                FROM {table}
                ORDER BY timestamp_ms ASC
                LIMIT %s OFFSET %s
            """, (BATCH_SIZE, offset))
            rows = cur.fetchall()

        if not rows:
            break

        tuples = [
            (
                r['symbol'],
                r['timestamp_ms'],
                r['timestamp'],
                r['open'],
                r['high'],
                r['low'],
                r['close'],
                r['volume']
            )
            for r in rows
        ]

        with sb_conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, insert_sql, tuples)
        sb_conn.commit()

        migrated += len(rows)
        offset   += BATCH_SIZE
        pct       = (migrated / total * 100) if total > 0 else 0
        print(f"  Progress: {migrated:,}/{total:,} ({pct:.1f}%)", end='\r')

        time.sleep(0.1)

    print(f"\n  Done: {migrated:,} rows migrated")
    return migrated


def verify_migration(ts_conn, sb_conn):
    """
    After migration, compares row counts between source and destination.
    Prints a summary showing whether counts match.
    """
    print("\n" + "="*50)
    print("VERIFICATION")
    print("="*50)

    tables = ['funding_rates', 'perp_prices', 'spot_prices']

    all_match = True
    for table in tables:
        ts_count = count_rows(ts_conn, table)
        sb_count = count_rows(sb_conn, table)
        match    = "✅" if ts_count == sb_count else "❌ MISMATCH"
        print(f"  {table:<20} source={ts_count:>8,}  dest={sb_count:>8,}  {match}")
        if ts_count != sb_count:
            all_match = False

    print()
    if all_match:
        print("✅ All row counts match. Migration successful.")
    else:
        print("❌ Row count mismatches detected.")

    return all_match


def run_migration():
    print(f"Migration started...")
    print("="*50)


    print("Connecting to databases...")

    ts_conn = get_connection()
    sb_conn = get_supabase_connection()

    print("✅ TimescaleDB connected")
    print("✅ Supabase connected")

    try:
        migrate_funding_rates(ts_conn, sb_conn)
        migrate_prices(ts_conn, sb_conn, 'perp_prices')
        migrate_prices(ts_conn, sb_conn, 'spot_prices')
        verify_migration(ts_conn, sb_conn)

    finally:
        ts_conn.close()
        sb_conn.close()

    print(f"\nMigration complete...")


if __name__ == "__main__":
    run_migration()
