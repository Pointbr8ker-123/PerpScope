# backend/routers/auth.py
#
# User authentication and alert management endpoints.
# All endpoints require a valid Supabase JWT token.
#
# Endpoints:
#   GET    /api/user/profile          -> current user profile
#   POST   /api/user/telegram         -> save Telegram chat_id
#   GET    /api/user/alerts           -> list user's alerts
#   POST   /api/user/alerts           -> create new alert
#   DELETE /api/user/alerts/{id}      -> delete an alert

import httpx
from jose import jwt, JWTError, jwk
from fastapi import APIRouter, HTTPException, Depends, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.database.db_config import SUPABASE_JWKS_URL
from backend.database.connection import get_connection

from src.telegram_alerts import send_message
from src.utils import log_info


router = APIRouter(prefix="/api", tags=["auth"])

security = HTTPBearer()

_jwks_cache = None

async def get_jwks():
    """
    This function fetches JWKS from supabase endpoint without caching.
    """
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient() as client:
            response = await client.get(SUPABASE_JWKS_URL)
            response.raise_for_status()
            _jwks_cache = response.json()

    return _jwks_cache


def get_signing_key(kid: str, jwks_data: dict):
    """
    This function extracts the public key for the given key ID
    """
    for key in jwks_data.get("keys", []):
        if key.get("kid") == kid:
            return jwk.construct(key).to_pem()
    raise ValueError(f"Key with kid {kid} not found")


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    This function verifies the Supabase JWT usin JWKS
    """
    token = credentials.credentials

    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Invalid token: missing kid")
        
        jwks_data = await get_jwks()
        signing_key = get_signing_key(kid, jwks_data)

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["ES256"],
            options={"verify_aud": False}
        )
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def get_current_user_db_id(user=Depends(get_current_user)):
    """
    This function gets the internal database ID from the users table
    for the currently authenticated user.
    """
    supabase_uid = user.get("sub")

    sql = """
        SELECT
            id, 
            email,
            plan,
            telegram_chat_id
        FROM users
        WHERE supabase_user_id = %s
            AND is_active = true
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (supabase_uid,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="User not found in database"
        )
    
    return dict(row)


# ------------------------------ USER MANAGEMENT ENDPOINTS ---------------------------------
@router.get("/user/profile")
async def get_profile(user=Depends(get_current_user_db_id)):
    """
    This function returns the current user's profile.
    """
    return {
        "id":                 user['id'],
        "email":              user['email'],
        "plan":               user['plan'],
        "telegram_connected": user['telegram_chat_id'] is not None,
    }


@router.post("/user/telegram")
async def connect_telegram(body: dict = Body(...), 
                           user=Depends(get_current_user_db_id)
):
    """
    This function saves the user's telegram chat id.
    """
    chat_id = body.get("chat_id", "").strip()

    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id is required")
    
    sql = """
        UPDATE users
        SET telegram_chat_id = %s
        WHERE id = %s
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, user['id']))
        conn.commit()

    send_message(chat_id, (
        "✅ *PerpScope Telegram connected!*\n\n"
        "You will receive alerts here when opportunities are detected.\n"
        "Manage alerts at: perpscope-frontend.nwosudavid13.workers.dev/account"
    ))

    return {"status": "ok", "message": "Telegram connected"}


@router.get("/user/telegram")
async def get_telegram_status(user=Depends(get_current_user_db_id)):
    """
    This function returns whether the user has connected Telegram.
    """
    return {
        "connected": user['telegram_chat_id'] is not None,
        "chat_id":   user['telegram_chat_id'],
    }


# ------------------------------ ALERT ENDPOINTS -------------------------------
@router.get("/user/alerts")
async def get_alerts(user=Depends(get_current_user_db_id)):
    """This function returns all alerts for the current user"""
    sql = """
        SELECT
            id,
            symbol, 
            market_cap_tier,
            threshold_tier,
            min_rho,
            is_active,
            created_at,
            last_triggered
        FROM user_alerts
        WHERE user_id = %s
        ORDER BY created_at DESC
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user['id'],))
            rows = cur.fetchall()

    return [dict(r) for r in rows]


@router.post("/user/alerts")
async def create_alert(body: dict = Body(...), 
                       user=Depends(get_current_user_db_id)
):
    """This function creates a new alert for the current user."""
    log_info(f"Alert creation body: {body}")

    symbol = body.get('symbol') or None
    
    tier_raw = body.get('tier') or body.get('market_cap_tier') or 'ALL'
    market_cap_tier = None if tier_raw == 'ALL' else tier_raw

    threshold_raw = (
        body.get('threshold') or
        body.get('threshold_tier') or
        'RETAIL'
    )

    threshold_map = {
        'RETAIL':       'high',
        'FUND':         'medium',
        'INSTITUTION':  'low',
        'MARKET_MAKER': 'no_fee',
        'MM':           'no_fee',
        'HIGH':         'high',
        'MEDIUM':       'medium',
        'LOW':          'low',
        'NO_FEE':       'no_fee',
    }

    threshold_tier = threshold_map.get(threshold_raw.upper(), 'high')

    min_rho_raw = body.get('min_rho')

    if min_rho_raw is None:
        min_rho = 1.0
    else:
        try:
            min_rho = float(min_rho_raw)
        except(TypeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail=f"min_rho must be a number. Received: {min_rho_raw!r}"
            )
        
        if min_rho < 0:
            raise HTTPException(
                status_code=422,
                detail="min_rho must be positive."
            )
        
        if min_rho > 5.0:
            raise HTTPException(
                status_code=422,
                detail=f"min_rho value {min_rho} seems unusually large. "
                       f"Maximum allowed is 5.0 (500% annualized)."
            )

    if user['plan'] == "free":
        count_sql = "SELECT COUNT(*) as c FROM user_alerts WHERE user_id = %s AND is_active = true"
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, (user['id'],))
                row = cur.fetchone()
        if row['c'] >= 3:
            raise HTTPException(
                status_code=403,
                detail="Free plan limited to 3 active alerts. Upgrade to Pro for unlimited alerts."
            )
        
    sql = """
        INSERT INTO user_alerts
            (user_id, symbol, market_cap_tier, threshold_tier,
            alert_channel, min_rho, is_active)
        VALUES
            (%s, %s, %s, %s, 'telegram', %s, true)
        RETURNING id
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                user['id'],
                symbol,
                market_cap_tier,
                threshold_tier,
                min_rho
            ))
            new_id = cur.fetchone()['id']
        conn.commit()

    return {"id": new_id, "status": "created"}


@router.delete("/user/alerts/{alert_id}")
async def delete_alert(alert_id, user=Depends(get_current_user_db_id)):
    """
    This function deletes one of the current user's alerts.
    """
    sql = """
        DELETE FROM user_alerts
        WHERE id = %s AND user_id = %s
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (alert_id, user['id']))
            deleted = cur.rowcount
        conn.commit()

    if deleted == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Alert {alert_id} not found or does not belong to this user"
        )

    return {"status": "deleted"}