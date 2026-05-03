import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

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
    