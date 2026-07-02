# backend/routers/automation.py
#
# Automation trigger endpoints called by cron-job.org on schedule.
# Protected by CRON_SECRET environment variable.
#
# Endpoints:
#   POST /trigger/prices    -> hourly price update (5 * * * *)
#   POST /trigger/funding   -> 8-hour funding update (10 0,8,16 * * *)
#   GET  /health            -> keep-alive + database connectivity check

import os
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from backend.database.connection import get_connection
from src.config import ALL_COINS
from src.update_data import run_price_update, run_funding_rates_update
from src.utils import log_info


router = APIRouter(tags=["automation"])


def verify_cron_secret(key):
    """
    This function verifies that the automation request came from 
    my cron job and raises HTTP 403 if the key is wrong or missing.
    """
    expected_key = os.getenv('CRON_SECRET')

    if not expected_key:
        raise HTTPException(
            status_code=500,
            detail="CRON_SECRET environment variable not configured"
        )
    
    if key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid secret key"
        )
    

@router.post("/trigger/funding")
async def trigger_funding_update(
    background_tasks: BackgroundTasks,
    key=Query(..., description="Secret key for authorization")
):
    """
    This function is triggered by cron-job every 8hrs
    for funding rates update.
    """
    verify_cron_secret(key)
    background_tasks.add_task(run_funding_rates_update)
    log_info("Funding rate update triggered by cron-job")

    return {
        "status":   "accepted",
        "message":  "Funding rate update started in background",
        "pipeline": "funding"
    }


@router.post("/trigger/prices")
async def trigger_price_update(
    background_tasks: BackgroundTasks,
    key=Query(..., description="Secret key for authorization")
):
    """
    This function is triggered by cron-job every hour
    to update perp and spot prices.
    """
    verify_cron_secret(key)
    background_tasks.add_task(run_price_update)
    log_info("Perp and spot prices updates triggered by cron-job")

    return {
        "status":   "accepted",
        "message":  "Perp and spot prices updates started in background",
        "pipeline": "prices"
    }


@router.get("/health")
async def health_check():
    """
    This function is called by cron-job every 10 mins to keep Render warm.
    """
    db_status = "unknown"

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status":       "ok",
        "database":     db_status,
        "coins_loaded": len(ALL_COINS),
        "timestamp":    datetime.now(timezone.utc).isoformat()
    }
