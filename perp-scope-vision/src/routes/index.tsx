import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, useEffect } from "react";
import { Layers, Zap, BarChart3, TrendingUp, Search, ArrowUpDown, ArrowUp, ArrowDown, Inbox, AlertCircle } from "lucide-react";
import { api, fmtPct, fmtPrice, rhoColor, type Opportunity, type Tier } from "@/lib/api";
import { Navbar } from "@/components/perpscope/navbar";
import { SignalBadge, TierBadge, Skeleton } from "@/components/perpscope/badges";
import { CoinAvatar } from "@/components/perpscope/coin-avatar";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "PerpScope — Funding Rate Deviations Across Perpetual Futures" },
      { name: "description", content: "Research-grade analytics for altcoin perpetual futures funding rate deviations." },
      { property: "og:title", content: "PerpScope — Perpetual Futures Analytics" },
      { property: "og:description", content: "Monitor funding rate deviations across altcoin perpetual futures markets." },
    ],
  }),
  component: Dashboard,
});

const REFRESH_MS = 60_000;

function StatCard({ icon: Icon, color, label, value, sub }: {
  icon: any; color: string; label: string; value: string; sub: string;
}) {
  return (
    <div className="glass-card animate-fade-up p-5">
      <div className="flex items-center justify-between">
        <div className="grid h-10 w-10 place-items-center rounded-lg" style={{ background: `${color}1A`, color }}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <div className="mt-4 text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-2xl font-bold tracking-tight text-foreground">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{sub}</div>
    </div>
  );
}

type SortKey = keyof Opportunity;

function Dashboard() {
  const [threshold, setThreshold] = useState("high");
  const [tier, setTier] = useState<"all" | Tier>("all");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("rho_annual");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [countdown, setCountdown] = useState(REFRESH_MS / 1000);

  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats, refetchInterval: REFRESH_MS });
  const ops = useQuery({
    queryKey: ["ops", threshold, tier],
    queryFn: () => api.opportunities(threshold, tier),
    refetchInterval: REFRESH_MS,
  });

  useEffect(() => {
    const t = setInterval(() => setCountdown(c => (c <= 1 ? REFRESH_MS / 1000 : c - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  const rows = useMemo(() => {
    const data = ops.data ?? [];
    const filtered = query
      ? data.filter(o => o.symbol.toLowerCase().includes(query.toLowerCase()) || o.name.toLowerCase().includes(query.toLowerCase()))
      : data;
    const tierFilt = tier === "all" ? filtered : filtered.filter(o => o.tier === tier);
    const sorted = [...tierFilt].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") return sortDir === "asc" ? av - bv : bv - av;
      return sortDir === "asc" ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
    if (sortKey === "rho_annual") sorted.sort((a, b) => sortDir === "asc" ? Math.abs(a.rho_annual) - Math.abs(b.rho_annual) : Math.abs(b.rho_annual) - Math.abs(a.rho_annual));
    return sorted;
  }, [ops.data, query, tier, sortKey, sortDir]);

  function toggleSort(k: SortKey) {
    if (sortKey === k) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir("desc"); }
  }

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">Perpetual Futures Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">Funding rate deviations across Bybit altcoin perpetuals · annualized ρ</p>
        </div>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {stats.isLoading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32" />) : stats.data && (
            <>
              <StatCard icon={Layers} color="#3B82F6" label="Coins Monitored" value={String(stats.data.coins_monitored)} sub="Bybit perpetuals" />
              <StatCard icon={Zap} color="#F59E0B" label="Active Opportunities" value={String(stats.data.active_opportunities)} sub="Above retail threshold" />
              <StatCard icon={BarChart3} color="#8B5CF6" label="Mean |ρ|" value={fmtPct(stats.data.mean_rho, 1)} sub="Annualized deviation" />
              <StatCard icon={TrendingUp} color="#10B981" label="Small / Large Cap" value={`${stats.data.small_large_ratio.toFixed(2)}×`} sub="Research finding" />
            </>
          )}
        </div>

        <div className="glass-card mt-8 overflow-hidden animate-fade-up">
          <div className="flex flex-col gap-2 border-b border-border p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-base font-semibold">Funding Rate Opportunities</h2>
              <p className="text-xs text-muted-foreground">Coins ranked by absolute ρ deviation from neutral</p>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-50" /><span className="relative inline-flex h-2 w-2 rounded-full bg-primary" /></span>
              <span>Refresh in <span className="font-mono text-foreground" data-num>{countdown}s</span></span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
            <div className="relative min-w-[200px] flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={query} onChange={e => setQuery(e.target.value)}
                placeholder="Search symbol or name…"
                className="h-9 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/30"
              />
            </div>
            <select value={threshold} onChange={e => setThreshold(e.target.value)}
              className="h-9 rounded-md border border-border bg-background px-3 text-sm outline-none focus:border-primary">
              <option value="high">Retail fees</option>
              <option value="medium">Fund fees</option>
              <option value="low">Institution fees</option>
              <option value="no_fee">Market Maker</option>
            </select>
            <select value={tier} onChange={e => setTier(e.target.value as any)}
              className="h-9 rounded-md border border-border bg-background px-3 text-sm outline-none focus:border-primary">
              <option value="all">All Tiers</option>
              <option value="LARGE">Large Cap</option>
              <option value="MID">Mid Cap</option>
              <option value="SMALL">Small Cap</option>
            </select>
            <div className="ml-auto text-xs text-muted-foreground">
              <span className="font-mono text-foreground" data-num>{rows.length}</span> results · updated <span className="font-mono" data-num>{new Date().toLocaleTimeString()}</span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead>
                <tr className="border-b border-border bg-bg-secondary/40 text-xs uppercase tracking-wider text-muted-foreground">
                  <Th label="Symbol" onClick={() => toggleSort("symbol")} active={sortKey === "symbol"} dir={sortDir} />
                  <Th label="Tier" onClick={() => toggleSort("tier")} active={sortKey === "tier"} dir={sortDir} />
                  <Th label="MC Rank" onClick={() => toggleSort("mc_rank")} active={sortKey === "mc_rank"} dir={sortDir} right />
                  <Th label="ρ (Annual)" onClick={() => toggleSort("rho_annual")} active={sortKey === "rho_annual"} dir={sortDir} right />
                  <Th label="Premium" onClick={() => toggleSort("premium")} active={sortKey === "premium"} dir={sortDir} right />
                  <Th label="Perp Price" onClick={() => toggleSort("perp_price")} active={sortKey === "perp_price"} dir={sortDir} right />
                  <Th label="Signal" onClick={() => toggleSort("signal")} active={sortKey === "signal"} dir={sortDir} />
                </tr>
              </thead>
              <tbody>
                {ops.isLoading && Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i} className="border-b border-border/60"><td colSpan={7} className="p-3"><Skeleton className="h-8 w-full" /></td></tr>
                ))}
                {ops.isError && (
                  <tr><td colSpan={7} className="py-16">
                    <div className="flex flex-col items-center gap-3 text-muted-foreground">
                      <AlertCircle className="h-8 w-8 text-destructive" />
                      <div className="text-sm">Failed to load opportunities.</div>
                      <button onClick={() => ops.refetch()} className="rounded-md border border-border px-3 py-1.5 text-xs hover:border-primary">Retry</button>
                    </div>
                  </td></tr>
                )}
                {!ops.isLoading && !ops.isError && rows.length === 0 && (
                  <tr><td colSpan={7} className="py-16">
                    <div className="flex flex-col items-center gap-2 text-muted-foreground">
                      <Inbox className="h-8 w-8" /><div className="text-sm">No opportunities match your filters.</div>
                    </div>
                  </td></tr>
                )}
                {rows.map((o, i) => {
                  const rowCls = o.signal === "SHORT_PERP_LONG_SPOT" ? "signal-row-short" : o.signal === "LONG_PERP_SHORT_SPOT" ? "signal-row-long" : "";
                  return (
                    <tr key={o.symbol} className={`group cursor-pointer border-b border-border/50 transition-colors hover:bg-primary/[0.04] ${rowCls} ${i % 2 ? "bg-bg-secondary/20" : ""}`}>
                      <td className="p-0">
                        <Link to="/coin/$symbol" params={{ symbol: o.symbol }} className="flex items-center gap-3 px-4 py-3">
                          <CoinAvatar symbol={o.symbol} size={32} />
                          <div>
                            <div className="font-semibold text-foreground">{o.symbol}</div>
                            <div className="text-xs text-muted-foreground">{o.name}</div>
                          </div>
                        </Link>
                      </td>
                      <td className="px-4"><TierBadge tier={o.tier} /></td>
                      <td className="px-4 text-right font-mono text-muted-foreground" data-num>#{o.mc_rank}</td>
                      <td className="px-4 text-right font-mono font-bold" data-num style={{ color: rhoColor(o.rho_annual) }}>
                        {o.rho_annual >= 0 ? "+" : ""}{fmtPct(o.rho_annual, 1)}
                      </td>
                      <td className="px-4 text-right font-mono text-xs text-muted-foreground" data-num>{fmtPct(o.premium, 2)}</td>
                      <td className="px-4 text-right font-mono" data-num>${fmtPrice(o.perp_price)}</td>
                      <td className="px-4 py-3"><SignalBadge signal={o.signal} size="sm" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

function Th({ label, onClick, active, dir, right }: { label: string; onClick: () => void; active: boolean; dir: "asc" | "desc"; right?: boolean }) {
  const Icon = !active ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th className={`px-4 py-3 font-medium ${right ? "text-right" : "text-left"}`}>
      <button onClick={onClick} className={`inline-flex items-center gap-1 transition-colors hover:text-foreground ${active ? "text-foreground" : ""}`}>
        {label} <Icon className="h-3 w-3 opacity-60" />
      </button>
    </th>
  );
}

export function Footer() {
  return (
    <footer className="mt-16 border-t border-border py-6">
      <div className="mx-auto max-w-[1440px] px-4 text-center text-xs text-muted-foreground sm:px-6 lg:px-8">
        PerpScope · Research tool · Data: Bybit · Not financial advice
      </div>
    </footer>
  );
}
