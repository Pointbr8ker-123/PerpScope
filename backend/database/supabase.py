import sys
import os
import psycopg2

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from backend.db_config import SUPABASE_DATABASE_URL
from src.utils import log

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
    ]

    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            for name, sql in statements:
                try:
                    log(f"Creating {name}...")
                    cur.execute(sql)
                except Exception as e:
                    log(f"Error on {name}: {e}")
                    raise
        conn.commit()

    log(f"\nAll Supabase Tables Created Successfully!!!")


if __name__ == "__main__":
    create_supabase_tables()
