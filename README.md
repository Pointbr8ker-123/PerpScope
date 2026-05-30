# PerpScope — Altcoin Perpetual Futures Analytics

> Real-time funding rate deviation analytics across 200+ altcoin perpetual futures.

- **Live Platform:** https://perpscope-frontend.nwosudavid13.workers.dev/
- **Research Basis:** He, Manela, Ross & von Wachter (2024) — 
*Fundamentals of Perpetual Futures:* https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4301150

---

## How PerpScope Works

PerpScope monitors the gap between perpetual futures prices and their
theoretical no-arbitrage fair values accross 200+ altcoins on Bybit.

When the gap exceeds the trading cost thresholds, a funding rate arbitrage opportunity exists: short the overpriced perpetual, long the spot, collect funding rate payments until prices converge.

PerpScope calculates the value of this "gap" or deviation (ρ) in real time for every monitored coin and alerts traders when opportunities appear.


## Features

- **Real-time mispricing detection** — Monitors 300+ altcoin perpetual futures to identify when contract prices deviate from spot prices
- **Opportunity leaderboard** — Ranked list showing which coins have the largest current mispricing
- **Deep dive analytics** — Historical charts for each coin showing mispricing trends and funding rates over time
- **Market cap research** — Compare how large, mid, and small cap coins behave differently (small caps show larger deviations)
- **Telegram alerts** — Receive phone notifications when opportunities open, intensify, or close (no need to watch the dashboard 24/7)
- **User accounts** — Save your alert preferences and get personalised notifications based on your thresholds

---

## Research Foundation

This project implements and extends the no-arbitrage pricing framework from:

> He, Z., Manela, A., Ross, O., & von Wachter, V. (2024).
> *Fundamentals of Perpetual Futures.*
> SSRN Working Paper. https://ssrn.com/abstract=4301150

The core deviation measure (ρ) from Equation 21 of that paper:

ρ = κ × (F−S)/F + sign(ι−r) × γ − r

Annualized by multiplying by 1095 (i.e 3 funding periods/day x 365 days/year)

**Parameters:**
- κ = 1 (Bybit premium scaling constant)
- ι = 0.0001 (8-hour interest component, 0.01%)
- γ = 0.0005 (clamp width, 0.05%)
- r ≈ 0.0000548 (risk-free rate proxy, ~6% annual stablecoin lending)

**Original research contribution:**

This project extends He et al.'s framework — originally applied to 5
large-cap coins — to a universe of 300+ altcoins, testing whether funding
rate deviation magnitude varies systematically with market capitalisation.
Early results suggest small-cap altcoins exhibit 3-7× higher mean |ρ|
than large-cap coins, consistent with reduced arbitrage capital in less
liquid markets.

---

### Architecture

- **cron-job.org** (free)
  - Triggers price updates (hourly)
  - Triggers funding rate updates (every 8 hours)
  - HTTP POST to FastAPI backend

- **FastAPI Backend** (Render, Frankfurt EU)
  - Data endpoints for frontend (`/api/opportunities`, `/api/coin/{symbol}`)
  - Automation trigger endpoints (`/trigger/prices`, `/trigger/funding`)
  - User authentication via Supabase JWT
  - Telegram webhook for bot commands (`/webhook/telegram`)

- **Databases**
  - **TimescaleDB**: Time-series storage for perp prices, spot prices, funding rates
  - **Supabase PostgreSQL**: User accounts, alert preferences, authentication

- **Data Pipeline** (`src/`)
  - `collect_historical.py`: One-time historical data pull from Bybit
  - `update_data.py`: Incremental 8-hour (funding) and hourly (price) updates
  - `calculate_rho.py`: Core ρ (rho) deviation calculation engine
  - `telegram_alerts.py`: State-machine alert engine (open/close/intensify)

- **Bybit API**
  - Source of all market data
  - Perpetual futures OHLCV, spot OHLCV, and 8-hour funding rates
  - Covers 300+ USDT-margined altcoin contracts
---

## Repository Structure
```
perpscope/
│
├── backend/                     # FastAPI backend (deployed on Render)
│   ├── database/
│   │   ├── timescale.py         # TimescaleDB connection + price queries
│   │   └── supabase.py          # Supabase connection + user queries
│   ├── main.py                  # FastAPI app — all API endpoints
│   └── requirements.txt
│
├── src/                         # Data pipeline
│   ├── config.py                # Coin universe, constants, paths
│   ├── collect_historical.py    # One-time historical data collection
│   ├── update_data.py           # Incremental hourly/8hr updates
│   ├── calculate_rho.py         # He et al. ρ deviation formula
│   ├── calculate_funding.py     # Funding rate display calculations
│   ├── get_universe.py          # Bybit perpetual contract discovery
│   ├── get_market_caps.py       # CoinGecko market cap classification
│   ├── telegram_alerts.py       # State-machine alert engine
│   ├── utils.py                 # Shared utilities (timestamps, custom logging)
│   └── setup_webhook.py         # One-time Telegram webhook registration
│
├── tests/
│   ├── test_calculate_rho.py    # Unit tests for ρ calculation
│   ├── test_connection.py       # Tests connection to Bybit API
│   └── test_api_endpoints.py    # Integration tests for API endpoints
│
├── .github/
│   └── workflows/
│       ├── update_prices.yml    # Hourly price update (GitHub Actions backup)
│       └── update_funding.yml   # 8-hour funding rate update (backup)
│
├── coin_universe.json           # Discovered Bybit perpetual contracts
├── market_cap_classification.json # CoinGecko tier classification
├── .gitignore
└── README.md
```
---

## Alert System Design

The Telegram alert engine uses three states — neutral, active, closing — 
so it only messages you when an opportunity actually opens, strengthens, 
or closes, so as to avoid spamming the user:

NEUTRAL → ACTIVE:   "Opportunity opened" alert sent immediately
ACTIVE  → CLOSING:  Waits one additional check (avoids false closes)
CLOSING → NEUTRAL:  "Opportunity closed" alert sent (confirmed close)
CLOSING → ACTIVE:   Brief dip detected, recovers silently
ACTIVE  → ACTIVE:   "Intensified" alert only if ρ increases >50%

Users can configure alerts with these three parameters:
- **Market cap tier** — Large/Mid/Small Cap or all
- **Fee tier** — based on the user's actual trading costs (retail/fund/institution)
- **Min ρ** — how big the deviation (ρ) needs to be to get an alert

This ensures every alert represents a genuinely profitable opportunity
for that specific user.

---
