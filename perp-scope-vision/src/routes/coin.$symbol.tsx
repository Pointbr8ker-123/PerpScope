import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { ArrowLeft } from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";
import { api, fmtPct, fmtPrice, rhoColor, SIGNALS } from "@/lib/api";
import { Navbar } from "@/components/perpscope/navbar";
import { Footer } from "@/routes/index";
import { SignalBadge, TierBadge, Skeleton } from "@/components/perpscope/badges";
import { CoinAvatar } from "@/components/perpscope/coin-avatar";

export const Route = createFileRoute("/coin/$symbol")({
  head: ({ params }) => ({ meta: [{ title: `${params.symbol} — PerpScope` }] }),
  component: CoinPage,
});

type Tab = "rho" | "funding";
type Days = 30 | 60 | 90 | 180;

function Card({ children, className = "" }: any) {
  return <div className={`glass-card animate-fade-up ${className}`}>{children}</div>;
}

function Metric({ label, value, color, sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <Card className="p-5">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-2 font-mono text-2xl font-bold tracking-tight" data-num style={{ color: color ?? "var(--foreground)" }}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </Card>
  );
}

function Pill({ active, onClick, children }: any) {
  return (
    <button onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${active ? "bg-primary text-primary-foreground" : "bg-elevated text-muted-foreground hover:text-foreground"}`}>
      {children}
    </button>
  );
}

function CoinPage() {
  const { symbol } = Route.useParams();
  const [tab, setTab] = useState<Tab>("rho");
  const [days, setDays] = useState<Days>(90);

  const coin = useQuery({ queryKey: ["coin", symbol], queryFn: () => api.coin(symbol) });
  const history = useQuery({ queryKey: ["history", symbol, days], queryFn: () => api.history(symbol, days) });
  const funding = useQuery({ queryKey: ["funding", symbol, days], queryFn: () => api.funding(symbol, days) });

  const stats = useMemo(() => {
    const d = history.data ?? [];
    if (!d.length) return null;
    const rs = d.map(p => p.rho);
    const mean = rs.reduce((a, b) => a + b, 0) / rs.length;
    const sd = Math.sqrt(rs.reduce((a, b) => a + (b - mean) ** 2, 0) / rs.length);
    const above = (t: number) => rs.filter(r => Math.abs(r) > t).length / rs.length;
    return { mean, max: Math.max(...rs), min: Math.min(...rs), sd, t20: above(0.2), t50: above(0.5), t100: above(1) };
  }, [history.data]);

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
        <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to Dashboard
        </Link>

        <div className="mt-4 flex flex-wrap items-center gap-4">
          <CoinAvatar symbol={symbol} size={48} />
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight">{coin.data?.name ?? symbol}</h1>
              <span className="font-mono text-lg text-muted-foreground">{symbol}</span>
              {coin.data && <TierBadge tier={coin.data.tier} />}
              {coin.data && <span className="font-mono text-sm text-muted-foreground" data-num>#{coin.data.mc_rank}</span>}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">Last updated <span className="font-mono" data-num>{new Date().toLocaleTimeString()}</span></div>
          </div>
          {coin.data && (
            <SignalBadge signal={coin.data.signal} size="lg"
              description={coin.data.signal === "NEUTRAL" ? "No actionable deviation" : "Active opportunity above threshold"} />
          )}
        </div>

        <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {coin.isLoading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />) : coin.data && (
            <>
              <Metric label="Current ρ" value={`${coin.data.rho_annual >= 0 ? "+" : ""}${fmtPct(coin.data.rho_annual, 2)}`} color={rhoColor(coin.data.rho_annual)} sub="Annualized" />
              <Metric label="Futures Premium" value={fmtPct(coin.data.premium, 3)} sub="Perp vs spot" />
              <Metric label="Mean |ρ| 90d" value={fmtPct(coin.data.mean_abs_rho_90d, 2)} sub="Historical average" />
              <Metric label="% Time as Opportunity" value={fmtPct(coin.data.pct_time_opportunity, 1)} color={coin.data.pct_time_opportunity > 0.5 ? "#10B981" : undefined} sub="Above threshold" />
            </>
          )}
        </div>

        <Card className="mt-6 p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-1.5">
              <Pill active={tab === "rho"} onClick={() => setTab("rho")}>ρ Deviation</Pill>
              <Pill active={tab === "funding"} onClick={() => setTab("funding")}>Funding Rate</Pill>
            </div>
            <div className="flex gap-1.5">
              {[30, 60, 90, 180].map(d => (
                <Pill key={d} active={days === d} onClick={() => setDays(d as Days)}>{d}d</Pill>
              ))}
            </div>
          </div>

          <div className="h-[360px] w-full">
            {tab === "rho" ? <RhoChart data={history.data ?? []} loading={history.isLoading} /> : <FundingChart data={funding.data ?? []} loading={funding.isLoading} />}
          </div>
        </Card>

        {coin.data && coin.data.signal !== "NEUTRAL" && (
          <Card className="mt-6 border-l-4 border-l-primary p-5">
            <div className="text-sm font-semibold text-foreground">Strategy Explanation</div>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {coin.data.signal === "SHORT_PERP_LONG_SPOT" ? (
                <>The perpetual contract is trading at a significant premium to spot, with annualized funding deviation of <span className="font-mono font-semibold text-foreground" data-num>{fmtPct(coin.data.rho_annual, 2)}</span>. Long holders are paying shorts. A delta-neutral position is constructed by <strong className="text-[#EF4444]">shorting the perpetual</strong> and <strong className="text-foreground">buying the spot</strong> in equal notional. The funding payments are collected as yield while market direction risk is hedged.</>
              ) : (
                <>The perpetual contract is trading at a discount to spot, with annualized funding deviation of <span className="font-mono font-semibold text-foreground" data-num>{fmtPct(coin.data.rho_annual, 2)}</span>. Shorts are paying longs. A delta-neutral position is constructed by <strong className="text-[#3B82F6]">longing the perpetual</strong> and <strong className="text-foreground">borrow-selling the spot</strong>. The funding payments are collected as yield while market direction risk is hedged.</>
              )}
            </p>
          </Card>
        )}

        {stats && (
          <Card className="mt-6 p-5">
            <div className="mb-4 text-sm font-semibold">Position Summary · {days}d window</div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px] text-sm">
                <tbody>
                  {[
                    ["Mean ρ", fmtPct(stats.mean, 2)],
                    ["Max ρ", fmtPct(stats.max, 2)],
                    ["Min ρ", fmtPct(stats.min, 2)],
                    ["Std deviation", fmtPct(stats.sd, 2)],
                    ["% time |ρ| > 20%", fmtPct(stats.t20, 1)],
                    ["% time |ρ| > 50%", fmtPct(stats.t50, 1)],
                    ["% time |ρ| > 100%", fmtPct(stats.t100, 1)],
                  ].map(([k, v]) => (
                    <tr key={k} className="border-b border-border/40">
                      <td className="py-2.5 text-muted-foreground">{k}</td>
                      <td className="py-2.5 text-right font-mono font-medium" data-num>{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </main>
      <Footer />
    </div>
  );
}

function ChartTooltip({ active, payload, label, suffix = "" }: any) {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  const sig = payload[0].payload?.signal;
  return (
    <div className="rounded-md border border-border bg-card/95 px-3 py-2 text-xs shadow-xl backdrop-blur">
      <div className="text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono font-semibold text-foreground" data-num>{(v * 100).toFixed(2)}{suffix}</div>
      {sig && <div className="mt-1 text-[10px] uppercase tracking-wider" style={{ color: SIGNALS[sig as keyof typeof SIGNALS].color }}>{SIGNALS[sig as keyof typeof SIGNALS].label}</div>}
    </div>
  );
}

function RhoChart({ data, loading }: { data: any[]; loading: boolean }) {
  if (loading) return <Skeleton className="h-full w-full" />;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="rho-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8B5CF6" stopOpacity={0.5} />
            <stop offset="100%" stopColor="#8B5CF6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.5} vertical={false} />
        <XAxis dataKey="date" stroke="var(--color-muted-foreground)" fontSize={11} tickLine={false} axisLine={false} minTickGap={40} />
        <YAxis stroke="var(--color-muted-foreground)" fontSize={11} tickLine={false} axisLine={false} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
        <ReferenceLine y={0} stroke="var(--color-border-strong)" />
        <ReferenceLine y={0.5} stroke="#EF4444" strokeDasharray="4 4" opacity={0.5} />
        <ReferenceLine y={-0.3} stroke="#3B82F6" strokeDasharray="4 4" opacity={0.5} />
        <Tooltip content={<ChartTooltip suffix="%" />} />
        <Area type="monotone" dataKey="rho" stroke="#8B5CF6" strokeWidth={2} fill="url(#rho-fill)" activeDot={{ r: 4, fill: "#A78BFA" }} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function FundingChart({ data, loading }: { data: any[]; loading: boolean }) {
  if (loading) return <Skeleton className="h-full w-full" />;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.5} vertical={false} />
        <XAxis dataKey="date" stroke="var(--color-muted-foreground)" fontSize={11} tickLine={false} axisLine={false} minTickGap={40} />
        <YAxis stroke="var(--color-muted-foreground)" fontSize={11} tickLine={false} axisLine={false} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
        <ReferenceLine y={0} stroke="var(--color-border-strong)" />
        <Tooltip content={<ChartTooltip suffix="%" />} cursor={{ fill: "rgba(59,130,246,0.06)" }} />
        <Bar dataKey="annualized" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => {
            const color = d.annualized > 0.1 ? "#EF4444" : d.annualized > 0 ? "#10B981" : "#3B82F6";
            return <Cell key={i} fill={color} />;
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
