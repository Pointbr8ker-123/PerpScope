# backend/main.py
#
# This is the main application entry point.
# This script pieces together the FastAPI app from the different routers.
# Each router handles a distinct area:
#
#   analytics.py  - market data endpoints consumed by the frontend
#   auth.py       - user authentication and alert management
#   automation.py - cron trigger endpoints and health check
#   webhooks.py   - Telegram bot webhook handler
#   debug.py      - diagnostic data check


import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.utils import log_info
from backend.routers import analytics, auth, automation, debug, webhooks
from backend.database.db_config import load_market_cap_data

# -------------------------------------- APP SETUP ----------------------------------------------
async def lifespan(app: FastAPI):
    # startup
    log_info("PerpScope API starting up...")
    load_market_cap_data()
    log_info("Startup complete!")

    yield

    # shutdown
    log_info("Cleaning up...")


app = FastAPI(
    title="PerpScope API",
    description=(
        "Altcoin perpetual futures analytics API."
        "Implements no-arbitrage pricing from He, Manela, Ross & von Wachter (2024)"
    ),
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware, 
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://perpscope-frontend.nwosudavid13.workers.dev",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


# ------------------------------ ROUTER REG. ---------------------------
app.include_router(analytics.router)
app.include_router(auth.router)
app.include_router(automation.router)
app.include_router(debug.router)
app.include_router(webhooks.router)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
