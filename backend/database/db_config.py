import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_DATABASE_URL = os.getenv('DATABASE_URL')
TIMESCALE_DATABASE_URL= os.getenv('TIMESCALE_URL')

SUPABASE_URL      = os.getenv("SUPABASE_URL")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL")