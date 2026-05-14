import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from backend.database.db_config import TIMESCALE_DATABASE_URL
from backend.database.supabase import get_supabase_connection
from src.utils import log

import psycopg2
from psycopg2.extras import execute_values


def get_timescale_connection():
    """
    This function connects to TimescaleDB  for time-series data.

    Used by: calculate_rho.py, update_data.py, main.py data endpoints
    
    Tables here: funding_rates, perp_prices, spot_prices,
                coin_universe, collection_progress
    """
    return psycopg2.connect(
        TIMESCALE_DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def get_connection():
    """
    Default connection, points to timescale for now
    """
    return get_timescale_connection()


def create_timescale_tables():
    """
    This function creates the time-series tables in timescaledb.
    """

    statements = [
        # ------------------------ Coin Universe ----------------------------
        # (
        #     "Create coin_universe table",
        #     """
        #     CREATE TABLE IF NOT EXISTS coin_universe (
        #         symbol              VARCHAR(20)  PRIMARY KEY,
        #         name                VARCHAR(100),
        #         coingecko_id        VARCHAR(100),
        #         market_cap          BIGINT,
        #         market_cap_rank     INTEGER,
        #         market_cap_tier     VARCHAR(20),
        #         has_spot_market     BOOLEAN      DEFAULT true,
        #         is_active           BOOLEAN      DEFAULT true,
        #         last_updated        TIMESTAMPTZ  DEFAULT NOW()
        #     );
        #     """
        # ),
        # (
        #     "Add indexes to coin_universe",
        #     """
        #     CREATE INDEX IF NOT EXISTS idx_coin_universe_tier
        #     ON coin_universe (market_cap_tier, last_updated DESC);
            
        #     CREATE INDEX IF NOT EXISTS idx_coin_universe_active
        #     ON coin_universe (is_active) WHERE is_active = true;
        #     """
        # ),

        # ----------------Funding rates table -----------------------------
        (
            "Create funding_rates table",
            """
            CREATE TABLE IF NOT EXISTS funding_rates (
                timestamp        TIMESTAMPTZ        NOT NULL,
                timestamp_ms    BIGINT              NOT NULL,
                symbol          VARCHAR(20)         NOT NULL,
                funding_rate    DOUBLE PRECISION    NOT NULL
            );
            """
        ),
        (
            "Convert funding_rates to hypertable",
            """
            SELECT create_hypertable(
                'funding_rates',
                'timestamp',
                if_not_exists => TRUE
            );
            """
        ),
        (
            "Add unique constraint to funding_rates",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_funding_rates_unique
            ON funding_rates (symbol, timestamp_ms, timestamp);
            """
        ),
        (
            "Add symbol index to funding_rates",
            """
            CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol
            ON funding_rates (symbol, timestamp DESC);
            """
        ),
        (
            "Enable compression on funding_rates",
            """
            ALTER TABLE funding_rates
            SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol',
                timescaledb.compress_orderby = 'timestamp DESC'
            );
            """
        ),
        (
            "Add compression policy to funding_rates",
            """
            SELECT add_compression_policy(
                'funding_rates',
                INTERVAL '7 days',
                if_not_exists => TRUE
            );
            """
        ),

        # --------------------Perp Prices table---------------------------------
        (
            "perp_prices table",
            """
            CREATE TABLE IF NOT EXISTS perp_prices (
                timestamp       TIMESTAMPTZ         NOT NULL,
                timestamp_ms    BIGINT              NOT NULL,
                symbol          VARCHAR(20)         NOT NULL,
                open            DOUBLE PRECISION,
                high            DOUBLE PRECISION,
                low             DOUBLE PRECISION,
                close           DOUBLE PRECISION,
                volume          DOUBLE PRECISION
            );
            """
        ),
        (
            "Convert perp_prices to hypertable",
            """
            SELECT create_hypertable(
                'perp_prices',
                'timestamp',
                if_not_exists => TRUE
            );
            """
        ),
        (
            "Add unique constraint to perp_prices",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_perp_prices_unique
            ON perp_prices (symbol, timestamp_ms, timestamp);
            """
        ),
        (
            "Add symbol index to perp_prices",
            """
            CREATE INDEX IF NOT EXISTS idx_perp_prices_symbol
            ON perp_prices (symbol, timestamp DESC);
            """
        ),
        (
            "Enable compression on perp_prices",
            """
            ALTER TABLE perp_prices
            SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol',
                timescaledb.compress_orderby = 'timestamp DESC'
            );
            """
        ),
        (
            "Add compression policy to perp_prices",
            """
            SELECT add_compression_policy(
                'perp_prices',
                INTERVAL '7 days',
                if_not_exists => TRUE
            );
            """
        ),

        #------------------------------ Spot Prices table-----------------------
        (
            "spot_prices table",
            """
            CREATE TABLE IF NOT EXISTS spot_prices (
                timestamp       TIMESTAMPTZ         NOT NULL,
                timestamp_ms    BIGINT              NOT NULL,
                symbol          VARCHAR(20)         NOT NULL,
                open            DOUBLE PRECISION,
                high            DOUBLE PRECISION,
                low             DOUBLE PRECISION,
                close           DOUBLE PRECISION,
                volume          DOUBLE PRECISION
            );
            """
        ),
        (
            "Convert spot_prices to hypertable",
            """
            SELECT create_hypertable(
                'spot_prices',
                'timestamp',
                if_not_exists => TRUE
            );
            """
        ),
        (
            "Add unique constraint to spot_prices",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_spot_prices_unique
            ON spot_prices (symbol, timestamp_ms, timestamp);
            """
        ),
        (
            "Add symbol index to spot_prices",
            """
            CREATE INDEX IF NOT EXISTS idx_spot_prices_symbol
            ON spot_prices (symbol, timestamp DESC);
            """
        ),
        (
            "Enable compression on spot_prices",
            """
            ALTER TABLE spot_prices
            SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol',
                timescaledb.compress_orderby = 'timestamp DESC'
            );
            """
        ),
        (
            "Add compression policy to spot_prices",
            """
            SELECT add_compression_policy(
                'spot_prices',
                INTERVAL '7 days',
                if_not_exists => TRUE
            );
            """
        ),

        # ------------------------Collection_progress table---------------------
        (
            "collection_progress table",
            """
            CREATE TABLE IF NOT EXISTS collection_progress (
                symbol                      VARCHAR(20),
                funding_collection_status   VARCHAR(20)  DEFAULT 'pending',
                funding_last_collected_ms   BIGINT,
                funding_total_records       INTEGER      DEFAULT 0,
                funding_error_message       TEXT,
                perp_collection_status      VARCHAR(20)  DEFAULT 'pending',
                perp_last_collected_ms      BIGINT,
                perp_total_records          INTEGER      DEFAULT 0,
                perp_error_message          TEXT,
                spot_collection_status      VARCHAR(20)  DEFAULT 'pending',
                spot_last_collected_ms      BIGINT,
                spot_total_records          INTEGER      DEFAULT 0,
                spot_error_message          TEXT,
                overall_status              VARCHAR(20)  DEFAULT 'pending',
                last_attempt                TIMESTAMPTZ,
                created_at                  TIMESTAMPTZ  DEFAULT NOW(),
                updated_at                  TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE (symbol, created_at)
            );
            """
        ),
        (
            "Convert collection_progress to hypertable",
            """
            SELECT create_hypertable(
                'collection_progress',
                'created_at',
                if_not_exists => TRUE
            );
            """
        ),
        (
            "Add indexes to collection_progress",
            """
            CREATE INDEX IF NOT EXISTS idx_collection_status
            ON collection_progress (overall_status, created_at DESC);
            
            CREATE INDEX IF NOT EXISTS idx_collection_symbol_status
            ON collection_progress (symbol, overall_status);
            """
        ),

        # ----------------------- Signal History Table -----------------------
        (
            "signal_history table",
            """
            CREATE TABLE IF NOT EXISTS signal_history (
                timestamp           TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
                timestamp_ms        BIGINT              NOT NULL,
                symbol              VARCHAR(20)         NOT NULL,
                signal_type         VARCHAR(30)         NOT NULL,
                rho                 DOUBLE PRECISION,
                perp_price          DOUBLE PRECISION,
                spot_price          DOUBLE PRECISION,
                premium_pct         DOUBLE PRECISION,
                funding_rate        DOUBLE PRECISION,
                threshold_tier      VARCHAR(20),
                market_cap_tier     VARCHAR(20)
            );
            """
        ),
        (
            "Convert signal_history to hypertable",
            """
            SELECT create_hypertable(
                'signal_history',
                'timestamp',
                if_not_exists => TRUE
            );
            """
        ),
        (
            "Add unique constraint to signal_history",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_history_unique
            ON signal_history (symbol, timestamp_ms, signal_type, timestamp);
            """
        ),
        (
            "Add indexes to signal_history",
            """
            CREATE INDEX IF NOT EXISTS idx_signal_history_symbol_time
            ON signal_history (symbol, timestamp DESC);
            
            CREATE INDEX IF NOT EXISTS idx_signal_history_type_time
            ON signal_history (signal_type, timestamp DESC);
            
            CREATE INDEX IF NOT EXISTS idx_signal_history_tier
            ON signal_history (market_cap_tier, timestamp DESC);
            """
        ),
        (
            "Enable compression on signal_history",
            """
            ALTER TABLE signal_history
            SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol, signal_type',
                timescaledb.compress_orderby = 'timestamp DESC'
            );
            """
        ),
        (
            "Add compression policy to signal_history",
            """
            SELECT add_compression_policy(
                'signal_history',
                INTERVAL '30 days',
                if_not_exists => TRUE
            );
            """
        ),
    ]

    log("Setting up TimescaleDB tables...")

    with get_connection() as conn:
        with conn.cursor() as cur:
            for name, sql in statements:
                try:
                    log(f"{name}...")
                    cur.execute(sql)
                    if conn.notices:
                        for notice in conn.notices:
                            log(f"  Notice: {notice}")
                except Exception as e:
                    log(f"ERROR on '{name}': {e}")
                    raise
        conn.commit()

    log(f"\nTimescaleDB Setup complete... All tables created successfully!!!")

# def populate_coin_universe_table(coins):
#     """
#     This inserts coin metadata in the coin_universe database table.
#     """
#     if not coins:
#         return 0
    
#     sql = """
#             INSERT INTO coin_universe (
#                 symbol, name, coingecko_id, market_cap, 
#                 market_cap_rank, market_cap_tier, has_spot_market,
#                 is_active, last_updated)
#             VALUES
#                 (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
#             ON CONFLICT (symbol) DO UPDATE SET
#                 name                = EXCLUDED.name,
#                 coingecko_id        = EXCLUDED.coingecko_id,
#                 market_cap          = EXCLUDED.market_cap,
#                 market_cap_rank     = EXCLUDED.market_cap_rank,
#                 market_cap_tier     = EXCLUDED.market_cap_tier,
#                 has_spot_market     = EXCLUDED.has_spot_market,
#                 is_active           = EXCLUDED.is_active,
#                 last_updated        = NOW()
#         """
    
#     rows = [
#         (
#             c['symbol'],
#             c.get('name', ''),
#             c.get('coingecko_id', ''),
#             c.get('market_cap', 0),
#             c.get('market_cap_rank', 9999),
#             c.get('market_cap_tier', 'Unknown'),
#             c.get('has_spot_market', True),
#             c.get('is_active', True)
#         )
#         for c in coins
#     ]

#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.executemany(sql, rows)
#         conn.commit()

#     return len(rows)


# def seed_coin_universe_table_from_json(json_path=None):
#     """
#     This function reads "market_cap_classification.json" file and populates
#     the coin_universe database table using the helper function above.
#     """
#     if json_path is None:
#         json_path = os.path.join(BASE_DIR, 'market_cap_classification.json')

#     with open(json_path, 'r') as f:
#         data = json.load(f)

#     coins = []
#     for tier in ('large_cap', 'mid_cap', 'small_cap'):
#         for coin in data[tier]:
#             coins.append({
#                 'symbol': coin['symbol'],
#                 'name': coin['name'],
#                 'coingecko_id': coin['coingecko_id'],
#                 'market_cap': coin['market_cap'],
#                 'market_cap_rank': coin['rank'],
#                 'market_cap_tier': tier,
#                 'has_spot_market': True
#             })

#     inserted = populate_coin_universe_table(coins)
#     log(f"Upserted {inserted} coins into coin_universe database table")
#     return inserted


# def is_already_loaded(symbol, table):
#     sql = f"""SELECT 1 FROM {table} WHERE symbol = %s LIMIT 1"""
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute(sql, (symbol,))
#             return cur.fetchone() is not None


# def get_already_loaded_symbols(table):
#     """
#     This function returns a set of symbols that already have data in the given table.
#     """
#     sql = f"SELECT DISTINCT symbol FROM {table}"
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute(sql)
#             rows = cur.fetchall()

#     return {row['symbol'] for row in rows}


# def insert_funding_rates(days=90):
#     """
#     This function migrates only the last N days from the funding_rates CSV 
#     files into the funding_rates table in the database.
#     """
#     cutoff_ms = now_ms() - (days * 24 * 60 * 60 * 1000)

#     already_loaded = get_already_loaded_symbols('funding_rates')
#     remaining = [s for s in ALL_COINS if s not in already_loaded]

#     log(f"Loading last {days} days of historical funding rates for {len(remaining)} coins...")

#     total_inserted = 0
#     missing = []

#     for symbol in remaining:
#         csv_path = os.path.join(DATA_DIR, symbol, f"{symbol}_funding_rates.csv")

#         if not os.path.exists(csv_path):
#             log(f"WARNING: No funding rates CSV found for {symbol}, skipping...")
#             missing.append(symbol)
#             continue

#         try:
#             df = pd.read_csv(csv_path)

#             df = df[df['timestamp_ms'] >= cutoff_ms]

#             if df.empty:
#                 log(f"{symbol}: no data in last {days} days, skipping...")
#                 continue

#             rows = [
#                 (
#                     str(row['symbol']) if 'symbol' in df.columns else symbol,
#                     int(row['timestamp_ms']),
#                     str(row['timestamp']),
#                     float(row['funding_rate'])
#                 )
#                 for _, row in df.iterrows()
#             ]

#             sql = """
#                 INSERT INTO funding_rates
#                     (symbol, timestamp_ms, timestamp, funding_rate)
#                 VALUES
#                     (%s, %s, %s, %s)
#                 ON CONFLICT (symbol, timestamp_ms) DO NOTHING
#             """

#             with get_connection() as conn:
#                 with conn.cursor() as cur:
#                     cur.executemany(sql, rows)
#                 conn.commit()

#             total_inserted += len(rows)
#             log(f"{symbol}: inserted {len(rows)} rows")

#         except Exception as e:
#             log(f"ERROR on {symbol}: {e}")
#             missing.append(symbol)

#     log(f"\nDone. Total rows inserted: {total_inserted}")

#     if missing:
#         log(f"Missing or failed CSVs for {len(missing)} coins: {missing}")

#     return total_inserted


# def insert_prices(price_type, database_table, csv_suffix, days=90):
#     """
#     This function migrates only the last N days from the perp_prices
#     and spot_prices CSV files into their respective tables in the database.
#     """
#     cutoff_ms = now_ms() - (days * 24 * 60 * 60 * 1000)
#     already_loaded = get_already_loaded_symbols(database_table)
#     remaining = [s for s in ALL_COINS if s not in already_loaded]

#     log(f"Loading last {days} days of {price_type} prices for {len(remaining)} coins")

#     total_inserted = 0
#     missing = []
#     CHUNK_SIZE = 200 

#     for symbol in remaining:
#         csv_path = os.path.join(DATA_DIR, symbol, f"{symbol}_{csv_suffix}.csv")

#         if not os.path.exists(csv_path):
#             missing.append(symbol)
#             continue

#         try:
#             df = pd.read_csv(
#                 csv_path,
#                 usecols=['timestamp_ms', 'timestamp', 'open', 'high',
#                          'low', 'close', 'volume'],
#                 dtype={
#                     'timestamp_ms': 'int64',
#                     'open': 'float64', 'high': 'float64',
#                     'low':  'float64', 'close':'float64',
#                     'volume': 'float64',
#                 }
#             )
#             df = df[df['timestamp_ms'] >= cutoff_ms]

#             if df.empty:
#                 log(f"  {symbol}: no data in last {days} days, skipping")
#                 continue

#             rows = [
#                 (symbol, int(r.timestamp_ms), r.timestamp,
#                  r.open, r.high, r.low, r.close, r.volume)
#                 for r in df.itertuples(index=False)
#             ]

#             sql = f"""
#                 INSERT INTO {database_table}
#                     (symbol, timestamp_ms, timestamp,
#                      open, high, low, close, volume)
#                 VALUES %s
#                 ON CONFLICT (symbol, timestamp_ms) DO NOTHING
#             """

#             symbol_inserted = 0
#             for i in range(0, len(rows), CHUNK_SIZE):
#                 chunk = rows[i : i + CHUNK_SIZE]
#                 with get_connection() as conn:
#                     with conn.cursor() as cur:
#                         cur.execute("SET LOCAL statement_timeout = '120s'")
#                         execute_values(cur, sql, chunk, page_size=100)
#                     conn.commit()
#                 symbol_inserted += len(chunk)

#             total_inserted += symbol_inserted
#             log(f"  {symbol}: inserted {symbol_inserted:,} rows "
#                 f"({len(rows)//CHUNK_SIZE + 1} chunks)")

#         except Exception as e:
#             log(f"  {symbol}: ERROR — {e}")
#             missing.append(symbol)

#     log(f"\nDone. Total inserted: {total_inserted:,}")
#     if missing:
#         log(f"Missing/failed: {missing}")

#     return total_inserted


# def get_coin_universe_from_database():
#     """
#     This function returns coin info from the database.
#     This would work with the FastAPI backend to retrieve coin data for
#     display on the frontend.
#     """
#     sql = """
#         SELECT
#             symbol, name, coingecko_id,
#             market_cap, market_cap_rank,
#             market_cap_tier, has_spot_market,
#             is_active
#         FROM coin_universe
#         WHERE is_active = true
#         ORDER BY market_cap_rank ASC NULLS LAST
#     """

#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute(sql)
#             rows = cur.fetchall()

#     return [dict(row) for row in rows]

RETENTION_DAYS = 90

def migrate_tables(source_table, dest_table, columns, use_time_filter=True):
    """
    This function migrates the timeseries data from supabase to TimescaleDB
    """
    log(f"\nMigrating {source_table} -> {dest_table}")

    col_str = ', '.join(columns)

    if use_time_filter:
        select_sql = f"""
            SELECT {col_str}
            FROM {source_table}
            WHERE timestamp >= NOW() - INTERVAL '{RETENTION_DAYS} days'
            ORDER BY timestamp ASC
        """
    else:
        select_sql = f"""
            SELECT {col_str}
            FROM {source_table}
            ORDER BY symbol ASC
        """

    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(select_sql)
            rows = cur.fetchall()

    if not rows:
        log(f"No data in {source_table} for the last {RETENTION_DAYS} days")
        return 0
    
    log(f"Read {len(rows):,} rows from Supabase")

    data = [
        tuple(row[col] for col in columns)
        for row in rows
    ]

    with get_timescale_connection() as conn:
        with conn.cursor() as cur:
            if source_table == 'coin_universe':
                execute_values(
                    cur,
                    f"""
                        INSERT INTO {dest_table} ({col_str})
                        VALUES %s
                        ON CONFLICT (symbol) DO UPDATE SET
                            last_updated = EXCLUDED.last_updated
                    """,
                    data,
                    page_size=500
                )
            else:
                execute_values(
                    cur,
                    f"""
                        INSERT INTO {dest_table} ({col_str})
                        VALUES %s
                        ON CONFLICT (symbol, timestamp_ms, timestamp) DO NOTHING
                    """,
                    data,
                    page_size=1000
                )
        conn.commit()

    log(f"Inserted {len(data):,} rows into TimescaleDB")
    return len(data)


def run_migration():
    log(f"Migrating last {RETENTION_DAYS} days to TimescaleDB")
    log("="*60)

    coin_universe_cols = ['symbol', 'name', 'coingecko_id', 'market_cap',
                          'market_cap_rank', 'market_cap_tier', 'has_spot_market',
                          'is_active', 'last_updated']
    funding_cols = ['timestamp', 'timestamp_ms', 'symbol', 'funding_rate']
    price_cols = ['timestamp', 'timestamp_ms', 'symbol',
                    'open', 'high', 'low', 'close', 'volume']
    
    # coin_uni  = migrate_tables('coin_universe', 'coin_universe', coin_universe_cols, use_time_filter=False)
    n_funding = migrate_tables('funding_rates', 'funding_rates', funding_cols)
    n_perp    = migrate_tables('perp_prices', 'perp_prices', price_cols)
    n_spot    = migrate_tables('spot_prices', 'spot_prices', price_cols)

    print("\n" + "=" * 55)
    print("Migration complete")
    print(f"  Funding rates: {n_funding:,} rows")
    print(f"  Perp prices:   {n_perp:,} rows")
    print(f"  Spot prices:   {n_spot:,} rows")


if __name__ == "__main__":
    # create_timescale_tables()

    run_migration()