import pandas as pd
from backend.database.connection import get_connection


PERIODS_PER_YEAR = 1095

def annualize_funding_rate(rate_per_8hr):
    """
    This function converts the 8hr funding rate to annualized percentage.
    """
    return rate_per_8hr * PERIODS_PER_YEAR * 100


def get_funding_signal(annualized_rate):
    """
    This function converts the annualized funding rate into signal.
    """
    if annualized_rate > 10: # +10% is the top quartile of positive funding
        return "LONGS_OVERHEATED"
    elif annualized_rate < -5: # -5% is bottom decile of all funding periods
        return "SHORTS_OVERHEATED"
    else:
        return "NEUTRAL"
    

def get_latest_funding_rates(symbols=None):
    """
    This pulls funding rates from the database, and returns:
    symbol, rate_per_8hr, annualized_rate, and signal of a particular coin.
    """
    if symbols:
        placeholders = ', '.join(['%s'] * len(symbols))
        symbol_clause = f"AND symbol IN ({placeholders})"
        params = tuple(symbols)
    else:
        symbol_clause = ""
        params = None

    sql = f"""
        SELECT DISTINCT ON (symbol)
            symbol,
            funding_rate    AS rate_per_8hr
        FROM funding_rates
        WHERE 1=1 {symbol_clause}
        ORDER BY symbol, timestamp_ms DESC
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(columns=['symbol', 'rate_per_8hr', 
                                     'annualized_rate', 'signal'])
    
    df = pd.DataFrame([dict(r) for r in rows])

    df['annualized_rate'] =df['rate_per_8hr'].apply(annualize_funding_rate)

    df['signal'] = df['annualized_rate'].apply(get_funding_signal)

    return df


if __name__ == "__main__":
    ...