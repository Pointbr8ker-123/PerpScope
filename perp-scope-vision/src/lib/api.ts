import axios from "axios";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) || "";

export const SIGNALS = {
  SHORT_PERP_LONG_SPOT: { label: "Short Perp", icon: "↓", color: "#EF4444" },
  LONG_PERP_SHORT_SPOT: { label: "Long Perp", icon: "↑", color: "#3B82F6" },
  NEUTRAL: { label: "Neutral", icon: "→", color: "#475569" },
} as const;

export type SignalKey = keyof typeof SIGNALS;
export type Tier = "LARGE" | "MID" | "SMALL";

export interface Opportunity {
  symbol: string;
  name: string;
  tier: Tier;
  mc_rank: number;
  rho_annual: number;
  premium: number;
  perp_price: number;
  signal: SignalKey;
}
export interface Stats {
  coins_monitored: number;
  active_opportunities: number;
  mean_rho: number;
  small_large_ratio: number;
}
export interface CoinDetail {
  symbol: string; name: string; tier: Tier; mc_rank: number;
  rho_annual: number; premium: number; perp_price: number;
  signal: SignalKey; mean_abs_rho_90d: number; pct_time_opportunity: number;
}
export interface HistoryPoint { date: string; rho: number; signal: SignalKey; }
export interface FundingPoint { date: string; funding: number; annualized: number; }
export interface ResearchSummary {
  ratio_small_large: number;
  tiers: { tier: Tier; count: number; mean_abs_rho: number; max_abs_rho: number }[];
  scatter: { symbol: string; name: string; tier: Tier; rank: number; mean_abs_rho: number }[];
}

// --- mock data fallback ---
const rng = (seed: number) => { let s = seed; return () => (s = (s * 9301 + 49297) % 233280) / 233280; };
const COINS = [
  ["BTC", "Bitcoin", "LARGE", 1], ["ETH", "Ethereum", "LARGE", 2], ["SOL", "Solana", "LARGE", 5],
  ["BNB", "BNB", "LARGE", 4], ["XRP", "XRP", "LARGE", 6], ["DOGE", "Dogecoin", "MID", 8],
  ["AVAX", "Avalanche", "MID", 15], ["LINK", "Chainlink", "MID", 12], ["DOT", "Polkadot", "MID", 18],
  ["MATIC", "Polygon", "MID", 22], ["ARB", "Arbitrum", "MID", 35], ["OP", "Optimism", "MID", 42],
  ["INJ", "Injective", "MID", 48], ["SUI", "Sui", "MID", 55], ["TIA", "Celestia", "MID", 78],
  ["SEI", "Sei", "SMALL", 88], ["JTO", "Jito", "SMALL", 120], ["PYTH", "Pyth", "SMALL", 95],
  ["WIF", "dogwifhat", "SMALL", 110], ["BONK", "Bonk", "SMALL", 145], ["JUP", "Jupiter", "SMALL", 102],
  ["RNDR", "Render", "MID", 38], ["FET", "Fetch.ai", "MID", 45], ["NEAR", "NEAR", "MID", 25],
  ["APT", "Aptos", "MID", 32], ["ATOM", "Cosmos", "MID", 28], ["FTM", "Fantom", "SMALL", 65],
  ["LDO", "Lido DAO", "MID", 40], ["UNI", "Uniswap", "MID", 19], ["AAVE", "Aave", "MID", 50],
] as const;

function mockOpportunities(): Opportunity[] {
  const r = rng(7);
  return COINS.map(([symbol, name, tier, rank]) => {
    const tierMult = tier === "SMALL" ? 3 : tier === "MID" ? 1.6 : 0.7;
    const rho = (r() - 0.5) * 4 * tierMult;
    const sig: SignalKey = rho > 0.5 ? "SHORT_PERP_LONG_SPOT" : rho < -0.3 ? "LONG_PERP_SHORT_SPOT" : "NEUTRAL";
    return {
      symbol, name, tier: tier as Tier, mc_rank: rank,
      rho_annual: rho, premium: rho * 0.15,
      perp_price: ({ BTC: 67234.21, ETH: 3421.55, SOL: 168.42 } as Record<string, number>)[symbol] ?? r() * 50,
      signal: sig,
    };
  });
}
function mockStats(): Stats {
  const ops = mockOpportunities();
  const active = ops.filter(o => o.signal !== "NEUTRAL").length;
  const meanAbs = ops.reduce((a, o) => a + Math.abs(o.rho_annual), 0) / ops.length;
  return { coins_monitored: ops.length, active_opportunities: active, mean_rho: meanAbs, small_large_ratio: 3.2 };
}
function mockHistory(symbol: string, days: number): HistoryPoint[] {
  const r = rng(symbol.charCodeAt(0) * 13);
  const out: HistoryPoint[] = []; let v = 0;
  for (let i = days - 1; i >= 0; i--) {
    v = v * 0.7 + (r() - 0.5) * 1.5;
    const d = new Date(); d.setDate(d.getDate() - i);
    const sig: SignalKey = v > 0.5 ? "SHORT_PERP_LONG_SPOT" : v < -0.3 ? "LONG_PERP_SHORT_SPOT" : "NEUTRAL";
    out.push({ date: d.toISOString().slice(0, 10), rho: v, signal: sig });
  }
  return out;
}
function mockFunding(symbol: string, days: number): FundingPoint[] {
  return mockHistory(symbol, days).map(p => ({ date: p.date, funding: p.rho / 1095, annualized: p.rho * 0.8 }));
}
function mockResearch(): ResearchSummary {
  const ops = mockOpportunities();
  const tiers: Tier[] = ["LARGE", "MID", "SMALL"];
  const tierData = tiers.map(t => {
    const subset = ops.filter(o => o.tier === t);
    const abs = subset.map(o => Math.abs(o.rho_annual));
    return { tier: t, count: subset.length, mean_abs_rho: abs.reduce((a, b) => a + b, 0) / abs.length, max_abs_rho: Math.max(...abs) };
  });
  return {
    ratio_small_large: tierData[2].mean_abs_rho / tierData[0].mean_abs_rho,
    tiers: tierData,
    scatter: ops.map(o => ({ symbol: o.symbol, name: o.name, tier: o.tier, rank: o.mc_rank, mean_abs_rho: Math.abs(o.rho_annual) })),
  };
}

async function call<T>(path: string, mock: () => T, extractData = false): Promise<T> {
  if (!BASE) return mock();
  try { 
    const r = await axios.get(`${BASE}${path}`);
    // If the response has a 'data' field that contains the actual data, extract it
    if (extractData && r.data && 'data' in r.data) {
      return r.data.data as T;
    }
    return r.data as T;
  } 
  catch { return mock(); }
}

export const api = {
  stats: () => call<Stats>("/api/stats", mockStats),
  opportunities: (threshold = "high", tier = "all") =>
    call<Opportunity[]>(`/api/opportunities?threshold=${threshold}&tier=${tier}`, mockOpportunities, true),
  coin: (symbol: string) =>
    call<CoinDetail>(`/api/coin/${symbol}`, () => {
      const o = mockOpportunities().find(x => x.symbol === symbol)!;
      return { ...o, mean_abs_rho_90d: Math.abs(o.rho_annual) * 0.8, pct_time_opportunity: 0.42 };
    }),
  history: (symbol: string, days = 90) => call<HistoryPoint[]>(`/api/history/${symbol}?days=${days}`, () => mockHistory(symbol, days)),
  funding: (symbol: string, days = 90) => call<FundingPoint[]>(`/api/funding/${symbol}?days=${days}`, () => mockFunding(symbol, days)),
  research: (days = 90) => call<ResearchSummary>(`/api/research/summary?days=${days}`, mockResearch),
};

export function rhoColor(rho: number): string {
  const a = Math.abs(rho);
  if (a > 2) return "#DC2626";
  if (a > 1) return "#EF4444";
  if (a > 0.5) return "#F97316";
  if (a > 0.2) return "#EAB308";
  return "#94A3B8";
}
export const fmtPct = (n: number, d = 2) => `${(n * 100).toFixed(d)}%`;
export const fmtPrice = (n: number) =>
  n >= 100 ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) :
  n >= 1 ? n.toFixed(3) : n.toFixed(5);
