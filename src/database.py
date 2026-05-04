import json
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv
from utils import log

from config import BASE_DIR

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
                timstamp        TIMESTAMPTZ         NOT NULL,
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
                timstamp        TIMESTAMPTZ         NOT NULL,
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
                timstamp        TIMESTAMPTZ         NOT NULL,
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


if __name__ == "__main__":
    # log(f"Setting up Supabase database...")
    # create_tables()

    log(f"Inserting coin info into the coin_universe database table...")
    seed_coin_universe_table_from_json()