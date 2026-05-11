import json
import pandas as pd
import psycopg2
import os
import time
from dotenv import load_dotenv
from io import StringIO
from psycopg2.extras import execute_values
from utils import log, now_ms

from config import BASE_DIR, DATA_DIR, ALL_COINS

load_dotenv()

def get_connection():
    """
    This functions opens a connection to my Supabase PostgreSQL database.
    """
    return psycopg2.connect(
        os.getenv('DATABASE_URL'),
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def create_tables():
    """
    This function creates all the tables in dependency order.
    """
    
    statements = [
        # Coin universe table
        (
            "coin_universe table",
            """
            CREATE TABLE IF NOT EXISTS coin_universe (
                symbol              VARCHAR(20)  PRIMARY KEY,
                name                VARCHAR(100),
                coingecko_id        VARCHAR(100),
                market_cap          BIGINT,
                market_cap_rank     INTEGER,
                market_cap_tier     VARCHAR(20),
                has_spot_market     BOOLEAN      DEFAULT true,
                is_active           BOOLEAN      DEFAULT true,
                last_updated        TIMESTAMPTZ  DEFAULT NOW()
            );
            """
        ),
        (
            "coin_universe indexes",
            """
            CREATE INDEX IF NOT EXISTS idx_coin_universe_tier
            ON coin_universe (market_cap_tier);

            CREATE INDEX IF NOT EXISTS idx_coin_universe_rank
            ON coin_universe (market_cap_rank)
            """
        ),

        # Funding rates table
        (
            "funding_rates table",
            """
            CREATE TABLE IF NOT EXISTS funding_rates (
                id              BIGSERIAL           PRIMARY KEY,
                symbol          VARCHAR(20)         NOT NULL,
                timestamp_ms    BIGINT              NOT NULL,
                timestamp        TIMESTAMPTZ        NOT NULL,
                funding_rate    DOUBLE PRECISION    NOT NULL,
                UNIQUE (symbol, timestamp_ms)
            );
            """
        ),
        (
            "funding_rates index",
            """
            CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol_time
            ON funding_rates (symbol, timestamp_ms DESC)
            """
        ),

        # Perp Prices table
        (
            "perp_prices table",
            """
            CREATE TABLE IF NOT EXISTS perp_prices (
                id              BIGSERIAL           PRIMARY KEY,
                symbol          VARCHAR(20)         NOT NULL,
                timestamp_ms    BIGINT              NOT NULL,
                timestamp       TIMESTAMPTZ         NOT NULL,
                open            DOUBLE PRECISION,
                high            DOUBLE PRECISION,
                low             DOUBLE PRECISION,
                close           DOUBLE PRECISION,
                volume          DOUBLE PRECISION,
                UNIQUE (symbol, timestamp_ms)
            );
            """
        ),
        (
            "perp_prices index",
            """
            CREATE INDEX IF NOT EXISTS idx_perp_prices_symbol_time
            ON perp_prices (symbol, timestamp_ms DESC);
            """
        ),

        # Spot Prices table
        (
            "spot_prices table",
            """
            CREATE TABLE IF NOT EXISTS spot_prices (
                id              BIGSERIAL           PRIMARY KEY,
                symbol          VARCHAR(20)         NOT NULL,
                timestamp_ms    BIGINT              NOT NULL,
                timestamp       TIMESTAMPTZ         NOT NULL,
                open            DOUBLE PRECISION,
                high            DOUBLE PRECISION,
                low             DOUBLE PRECISION,
                close           DOUBLE PRECISION,
                volume          DOUBLE PRECISION,
                UNIQUE (symbol, timestamp_ms)
            );
            """
        ),
        (
            "spot_prices index",
            """
            CREATE INDEX IF NOT EXISTS idx_spot_prices_symbol_time
            ON spot_prices (symbol, timestamp_ms DESC)
            """
        ),

        # Collection_progress table
        (
            "collection_progress table",
            """
            CREATE TABLE IF NOT EXISTS collection_progress (
                symbol                      VARCHAR(20)  PRIMARY KEY,
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
                created_at                  TIMESTAMPTZ  DEFAULT NOW()
            );
            """
        ),

        # Signal history table
        (
            "signal_history table",
            """
            CREATE TABLE IF NOT EXISTS signal_history (
                id              BIGSERIAL           PRIMARY KEY,
                symbol          VARCHAR(20)         NOT NULL,
                timestamp       TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
                timestamp_ms    BIGINT              NOT NULL,
                signal_type     VARCHAR(30)         NOT NULL,
                rho             DOUBLE PRECISION,
                perp_price      DOUBLE PRECISION,
                spot_price      DOUBLE PRECISION,
                premium_pct     DOUBLE PRECISION,
                funding_rate    DOUBLE PRECISION,
                threshold_tier  VARCHAR(20),
                market_cap_tier VARCHAR(20)
            );
            """
        ),
        (
            "signal_history indexes",
            """
            CREATE INDEX IF NOT EXISTS idx_signal_history_symbol_time
            ON signal_history (symbol, timestamp DESC);

            CREATE INDEX IF NOT EXISTS idx_signal_history_time
            ON signal_history (timestamp DESC)
            """
        ),

        # Users Table
        (
            "users table",
            """
            CREATE TABLE IF NOT EXISTS users (
                id                  BIGSERIAL       PRIMARY KEY,
                email               VARCHAR(255)    UNIQUE NOT NULL,
                created_at          TIMESTAMPTZ     DEFAULT NOW(),
                last_login          TIMESTAMPTZ,
                is_active           BOOLEAN         DEFAULT true,
                plan                VARCHAR(20)     DEFAULT 'free',
                supabase_user_id    UUID            UNIQUE
            );
            """
        ),

        # User alerts table
        (
            "user_alerts table",
            """
            CREATE TABLE IF NOT EXISTS user_alerts (
                id                  BIGSERIAL       PRIMARY KEY,
                user_id             BIGINT          REFERENCES users(id),
                symbol              VARCHAR(20),
                market_cap_tier     VARCHAR(20),
                threshold_tier      VARCHAR(20),
                alter_channel       VARCHAR(20) DEFAULT 'telegram',
                telegram_chat_id    VARCHAR(50),
                min_rho             DOUBLE PRECISION DEFAULT 1.0,
                is_active           BOOLEAN DEFAULT true,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                last_triggered      TIMESTAMPTZ
            );
            """
        ),

        # User subscriptions table
        (
            "user_subscriptions table",
            """
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id                          BIGSERIAL     PRIMARY KEY,
                user_id                     BIGINT        REFERENCES users(id),
                plan                        VARCHAR(20)   NOT NULL,
                status                      VARCHAR(20)   NOT NULL,
                started_at                  TIMESTAMPTZ   DEFAULT NOW(),
                expires_at                  TIMESTAMPTZ,
                paystack_customer_code      VARCHAR(100),
                paystack_subscription_code  VARCHAR(100),
                paystack_authorization_code VARCHAR(100),
                stripe_customer_id          VARCHAR(100),
                stripe_sub_id               VARCHAR(100)
            );
            """
        ),
    ]

    with get_connection() as conn:
        with conn.cursor() as cur:
            for name, sql in statements:
                try:
                    log(f"Creating {name}...")
                    cur.execute(sql)
                except Exception as e:
                    log(f"Error on {name}: {e}")
                    raise
        conn.commit()

    log(f"\nAll Tables Created Successfully!!!")


def populate_coin_universe_table(coins):
    """
    This inserts coin metadata in the coin_universe database table.
    """
    if not coins:
        return 0
    
    sql = """
            INSERT INTO coin_universe (
                symbol, name, coingecko_id, market_cap, 
                market_cap_rank, market_cap_tier, has_spot_market,
                is_active, last_updated)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (symbol) DO UPDATE SET
                name                = EXCLUDED.name,
                coingecko_id        = EXCLUDED.coingecko_id,
                market_cap          = EXCLUDED.market_cap,
                market_cap_rank     = EXCLUDED.market_cap_rank,
                market_cap_tier     = EXCLUDED.market_cap_tier,
                has_spot_market     = EXCLUDED.has_spot_market,
                is_active           = EXCLUDED.is_active,
                last_updated        = NOW()
        """
    
    rows = [
        (
            c['symbol'],
            c.get('name', ''),
            c.get('coingecko_id', ''),
            c.get('market_cap', 0),
            c.get('market_cap_rank', 9999),
            c.get('market_cap_tier', 'Unknown'),
            c.get('has_spot_market', True),
            c.get('is_active', True)
        )
        for c in coins
    ]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()

    return len(rows)


def seed_coin_universe_table_from_json(json_path=None):
    """
    This function reads "market_cap_classification.json" file and populates
    the coin_universe database table using the helper function above.
    """
    if json_path is None:
        json_path = os.path.join(BASE_DIR, 'market_cap_classification.json')

    with open(json_path, 'r') as f:
        data = json.load(f)

    coins = []
    for tier in ('large_cap', 'mid_cap', 'small_cap'):
        for coin in data[tier]:
            coins.append({
                'symbol': coin['symbol'],
                'name': coin['name'],
                'coingecko_id': coin['coingecko_id'],
                'market_cap': coin['market_cap'],
                'market_cap_rank': coin['rank'],
                'market_cap_tier': tier,
                'has_spot_market': True
            })

    inserted = populate_coin_universe_table(coins)
    log(f"Upserted {inserted} coins into coin_universe database table")
    return inserted


def is_already_loaded(symbol, table):
    sql = f"""SELECT 1 FROM {table} WHERE symbol = %s LIMIT 1"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (symbol,))
            return cur.fetchone() is not None


def get_already_loaded_symbols(table):
    """
    This function returns a set of symbols that already have data in the given table.
    """
    sql = f"SELECT DISTINCT symbol FROM {table}"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    return {row['symbol'] for row in rows}


def insert_funding_rates(days=90):
    """
    This function migrates only the last N days from the funding_rates CSV 
    files into the funding_rates table in the database.
    """
    cutoff_ms = now_ms() - (days * 24 * 60 * 60 * 1000)

    already_loaded = get_already_loaded_symbols('funding_rates')
    remaining = [s for s in ALL_COINS if s not in already_loaded]

    log(f"Loading last {days} days of historical funding rates for {len(remaining)} coins...")

    total_inserted = 0
    missing = []

    for symbol in remaining:
        csv_path = os.path.join(DATA_DIR, symbol, f"{symbol}_funding_rates.csv")

        if not os.path.exists(csv_path):
            log(f"WARNING: No funding rates CSV found for {symbol}, skipping...")
            missing.append(symbol)
            continue

        try:
            df = pd.read_csv(csv_path)

            df = df[df['timestamp_ms'] >= cutoff_ms]

            if df.empty:
                log(f"{symbol}: no data in last {days} days, skipping...")
                continue

            rows = [
                (
                    str(row['symbol']) if 'symbol' in df.columns else symbol,
                    int(row['timestamp_ms']),
                    str(row['timestamp']),
                    float(row['funding_rate'])
                )
                for _, row in df.iterrows()
            ]

            sql = """
                INSERT INTO funding_rates
                    (symbol, timestamp_ms, timestamp, funding_rate)
                VALUES
                    (%s, %s, %s, %s)
                ON CONFLICT (symbol, timestamp_ms) DO NOTHING
            """

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(sql, rows)
                conn.commit()

            total_inserted += len(rows)
            log(f"{symbol}: inserted {len(rows)} rows")

        except Exception as e:
            log(f"ERROR on {symbol}: {e}")
            missing.append(symbol)

    log(f"\nDone. Total rows inserted: {total_inserted}")

    if missing:
        log(f"Missing or failed CSVs for {len(missing)} coins: {missing}")

    return total_inserted


def insert_prices(price_type, database_table, csv_suffix, days=90):
    """
    This function migrates only the last N days from the perp_prices
    and spot_prices CSV files into their respective tables in the database.
    """
    cutoff_ms = now_ms() - (days * 24 * 60 * 60 * 1000)
    already_loaded = get_already_loaded_symbols(database_table)
    remaining = [s for s in ALL_COINS if s not in already_loaded]

    log(f"Loading last {days} days of {price_type} prices for {len(remaining)} coins")

    total_inserted = 0
    missing = []
    CHUNK_SIZE = 200 

    for symbol in remaining:
        csv_path = os.path.join(DATA_DIR, symbol, f"{symbol}_{csv_suffix}.csv")

        if not os.path.exists(csv_path):
            missing.append(symbol)
            continue

        try:
            df = pd.read_csv(
                csv_path,
                usecols=['timestamp_ms', 'timestamp', 'open', 'high',
                         'low', 'close', 'volume'],
                dtype={
                    'timestamp_ms': 'int64',
                    'open': 'float64', 'high': 'float64',
                    'low':  'float64', 'close':'float64',
                    'volume': 'float64',
                }
            )
            df = df[df['timestamp_ms'] >= cutoff_ms]

            if df.empty:
                log(f"  {symbol}: no data in last {days} days, skipping")
                continue

            rows = [
                (symbol, int(r.timestamp_ms), r.timestamp,
                 r.open, r.high, r.low, r.close, r.volume)
                for r in df.itertuples(index=False)
            ]

            sql = f"""
                INSERT INTO {database_table}
                    (symbol, timestamp_ms, timestamp,
                     open, high, low, close, volume)
                VALUES %s
                ON CONFLICT (symbol, timestamp_ms) DO NOTHING
            """

            symbol_inserted = 0
            for i in range(0, len(rows), CHUNK_SIZE):
                chunk = rows[i : i + CHUNK_SIZE]
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SET LOCAL statement_timeout = '120s'")
                        execute_values(cur, sql, chunk, page_size=100)
                    conn.commit()
                symbol_inserted += len(chunk)

            total_inserted += symbol_inserted
            log(f"  {symbol}: inserted {symbol_inserted:,} rows "
                f"({len(rows)//CHUNK_SIZE + 1} chunks)")

        except Exception as e:
            log(f"  {symbol}: ERROR — {e}")
            missing.append(symbol)

    log(f"\nDone. Total inserted: {total_inserted:,}")
    if missing:
        log(f"Missing/failed: {missing}")

    return total_inserted


def get_coin_universe_from_database():
    """
    This function returns coin info from the database.
    This would work with the FastAPI backend to retrieve coin data for
    display on the frontend.
    """
    sql = """
        SELECT
            symbol, name, coingecko_id,
            market_cap, market_cap_rank,
            market_cap_tier, has_spot_market,
            is_active
        FROM coin_universe
        WHERE is_active = true
        ORDER BY market_cap_rank ASC NULLS LAST
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    return [dict(row) for row in rows]
    

if __name__ == "__main__":
    # log(f"Setting up Supabase database...")
    # create_tables()

    # log(f"Inserting coin info into the coin_universe database table...")
    # seed_coin_universe_table_from_json()

    # log(f"\nLoading historical funding rates...")
    # insert_funding_rates(days=90)

    log(f"\nLoading historical perp prices...")
    insert_prices('perp', 'perp_prices', 'perp_hourly', days=90)

    log(f"\nLoading historical spot prices...")
    insert_prices('spot', 'spot_prices', 'spot_hourly', days=90)
