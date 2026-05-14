import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_DATABASE_URL = os.getenv('DATABASE_URL')
TIMESCALE_DATABASE_URL= os.getenv('TIMESCALE_URL')