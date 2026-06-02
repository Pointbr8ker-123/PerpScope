import sys
import os
import psycopg2
import psycopg2.extras

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from backend.database.db_config import SUPABASE_DATABASE_URL
from src.utils import log_info, log_err

def get_supabase_connection():
    """
    This functions opens a connection to my Supabase PostgreSQL database.

    Used by: user auth, alerts, subscriptions, coin_universe
    
    Tables here: users, user_alerts, user_subscriptions,
                 coin_universe, collection_progress
    """
    return psycopg2.connect(
        SUPABASE_DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def create_supabase_tables():
    """
    This function creates all the tables in dependency order.
    """
    
    statements = [
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

        # Alert state table
        (
            "alert_state table",
            """
            CREATE TABLE IF NOT EXISTS alert_state (
                id                    BIGSERIAL     PRIMARY KEY,
                user_id               BIGINT        REFERENCES users(id),
                symbol                VARCHAR(20)   NOT NULL,
                state                 VARCHAR(20)   NOT NULL DEFAULT 'NEUTRAL',
                opened_at             TIMESTAMPTZ,
                entry_rho             DOUBLE PRECISION,
                last_alert_rho        DOUBLE PRECISION,
                last_alerted_at       TIMESTAMPTZ,
                UNIQUE (user_id, symbol)
            );
            """
        ),
        (
            "create alert_state_user index",
            """
            CREATE INDEX IF NOT EXISTS idx_alert_state_user
            ON alert_state (user_id, state)
            """
        )
    ]

    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            for name, sql in statements:
                try:
                    log_info(f"Creating {name}...")
                    cur.execute(sql)
                except Exception as e:
                    log_err(f"Error on {name}: {e}")
                    raise
        conn.commit()

    log_info(f"\nAll Supabase Tables Created Successfully!!!")


def alter_table(table_name, old_column_name, new_column_name):
    sql = f"""
        ALTER TABLE {table_name}
        RENAME COLUMN {old_column_name} TO {new_column_name}
    """
    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    log_info(f"Successfully changed the column name in {table_name} database table")


def add_column(table_name, column_name, data_type):
    sql = f"""
        ALTER TABLE {table_name}
        ADD COLUMN IF NOT EXISTS {column_name} {data_type}
    """
    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    log_info(f"Successfully added the column '{column_name}' to the {table_name} database table")


if __name__ == "__main__":
    # create_supabase_tables()

    # alter_table("user_alerts", "alter_channel", "alert_channel")

    add_column("users", "telegram_chat_id", "VARCHAR(50)")
