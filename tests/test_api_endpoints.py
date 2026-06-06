import pytest
import requests
import numpy as np

BASE_URL = "http://localhost:8000"


def test_health():
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert data["status"] == "ok"

def test_stats_shape():
    r = requests.get(f"{BASE_URL}/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert "coins_monitored"      in data
    assert "active_opportunities" in data
    assert "mean_rho"             in data
    assert "small_large_ratio"    in data

def test_opportunities_returns():
    r = requests.get(f"{BASE_URL}/api/opportunities")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    first  = data[0]
    assert "symbol"     in first
    assert "perp_price" in first
    assert "spot_price" in first
    assert "premium"    in first
    assert "rho_annual" in first
    assert "signal"     in first
    assert "tier"       in first
    assert "mc_rank"    in first
    assert first["signal"] in (
        "SHORT_PERP_LONG_SPOT",
        "LONG_PERP_SHORT_SPOT",
        "NEUTRAL"
    )
    assert first["tier"] in (
        "LARGE", "MID", "SMALL"
    )

def test_opportunity_threshold_filter():
    r_high   = requests.get(f"{BASE_URL}/api/opportunities?threshold=high")
    r_no_fee = requests.get(f"{BASE_URL}/api/opportunities?threshold=no_fee")
    assert r_high.status_code   == 200
    assert r_no_fee.status_code == 200
    # No fee threshold should be 0, therefore should have more or equal opportunities
    high_opp   = [c for c in r_high.json() if c["signal"] != 'NEUTRAL']
    no_fee_opp = [c for c in r_no_fee.json() if c["signal"] != 'NEUTRAL']
    assert len(no_fee_opp) >= len(high_opp)

def test_history_shape():
    r = requests.get(f"{BASE_URL}/api/history/BTCUSDT?days=30")
    assert r.status_code == 200
    data = r.json()
    assert "symbol"      in data
    assert "days"        in data
    assert "data_points" in data
    assert "data"        in data

    history = data["data"][0]
    assert "date"       in history
    assert "rho"        in history
    assert "perp_price" in history
    assert "spot_price" in history
    assert "signal"     in history

def test_coin_detail():
    r = requests.get(f"{BASE_URL}/api/coin/BTCUSDT")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "BTCUSDT"
    assert "rho_annual" in data
    assert "mean_abs_rho_90d" in data
    assert not np.isnan(data["mean_abs_rho_90d"])

def test_research_summary():
    r = requests.get(f"{BASE_URL}/api/research/summary")
    assert r.status_code == 200
    data = r.json()
    assert "ratio_small_large" in data
    assert "tiers" in data
    assert "scatter" in data
    tiers_array = data["tiers"]
    assert len(tiers_array) > 0


if __name__ == "__main__":
    ...
