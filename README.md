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


## Architecture
┌─────────────────────────────────────────────────────────┐
│  cron-job.org (free)                                    │
│  Triggers price updates (hourly) and                    │
│  funding rate updates (every 8 hours)                   │
└────────────────────┬────────────────────────────────────┘
│ HTTP POST
┌────────────────────▼────────────────────────────────────┐
│  FastAPI Backend (Render, Frankfurt EU)                 │
│  backend/main.py                                        │
│  · Data endpoints for frontend                          │
│  · Automation trigger endpoints                         │
│  · User authentication via Supabase JWT                 │
│  · Telegram webhook for bot commands                    │
└──────────┬──────────────────────────────────────────────┘
│                          │
┌──────────▼──────────┐   ┌──────────▼──────────────────┐
│  TimescaleDB        │   │  Supabase PostgreSQL         │
│  Price + funding    │   │  Users, alerts, auth         │
│  rate time-series   │   │                              │
└─────────────────────┘   └──────────────────────────────┘
▲
┌──────────┴──────────────────────────────────────────────┐
│  Data Pipeline (src/)                                   │
│  · collect_historical.py — one-time historical pull     │
│  · update_data.py — incremental 8-hour/hourly updates   │
│  · calculate_rho.py — ρ deviation engine                │
│  · telegram_alerts.py — state-machine alert engine      │
└─────────────────────────────────────────────────────────┘
▲
┌──────────┴──────────────────────────────────────────────┐
│  Bybit API (api.bybit.com)                              │
│  Perpetual futures + spot OHLCV + funding rates         │
│  300+ USDT-margined contracts                           │
└─────────────────────────────────────────────────────────┘

---
