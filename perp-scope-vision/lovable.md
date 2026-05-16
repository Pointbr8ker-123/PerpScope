# PerpScope — Lovable Context File

## Project Overview
PerpScope is an altcoin perpetual futures analytics platform that monitors 
funding rate deviations from theoretical no-arbitrage fair values across 
300+ Bybit perpetual contracts.

Based on: He, Manela, Ross & von Wachter (2024) "Fundamentals of Perpetual Futures"

## Backend
FastAPI backend deployed on Render (Frankfurt EU region).
Database: Supabase PostgreSQL.
Data source: Bybit API.

## API Base URL
Set via VITE_API_URL environment variable.
Local: http://localhost:8000
Production: https://[render-service-name].onrender.com

## API Endpoints and Response Shapes

GET /api/stats
Returns: { coins_monitored, active_opportunities, mean_rho, small_large_ratio }

GET /api/opportunities?threshold=retail&tier=all
Returns: Opportunity[] where Opportunity has:
{ symbol, name, tier (LARGE|MID|SMALL), mc_rank, rho_annual, 
  premium, perp_price, signal (SHORT_PERP_LONG_SPOT|LONG_PERP_SHORT_SPOT|NEUTRAL) }

GET /api/coin/:symbol
Returns: CoinDetail (same fields as Opportunity plus mean_abs_rho_90d, pct_time_opportunity)

GET /api/history/:symbol?days=90
Returns: HistoryPoint[] where each has { date (YYYY-MM-DD), rho, signal }

GET /api/funding/:symbol?days=90
Returns: FundingPoint[] where each has { date, funding, annualized }

GET /api/research/summary?days=90
Returns: { ratio_small_large, tiers: [{tier, count, mean_abs_rho, max_abs_rho}], 
           scatter: [{symbol, name, tier, rank, mean_abs_rho}] }

## Key Domain Concepts
- ρ (rho): annualized deviation from no-arbitrage fair value
- Positive ρ: futures overpriced → SHORT_PERP_LONG_SPOT signal
- Negative ρ: futures underpriced → LONG_PERP_SHORT_SPOT signal
- Thresholds: retail=1.794%, fund=1.143%, institution=0.532%, mm=0%
- Tiers: LARGE (rank 1-20), MID (rank 21-100), SMALL (rank 101+)
- Data updates: prices every hour, funding rates every 8 hours

## Design Decisions
- Dark mode default, full light mode support
- Monospace font (JetBrains Mono) for all financial numbers
- Signal colors: red=#EF4444 (short), blue=#3B82F6 (long), gray=#475569 (neutral)
- Tier colors: blue (Large), purple (Mid), green (Small)