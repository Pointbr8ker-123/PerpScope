import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ZAxis,
} from "recharts";
import { api, fmtPct, type Tier } from "@/lib/api";
import { Navbar } from "@/components/perpscope/navbar";
import { Footer } from "@/routes/index";
import { TierBadge, Skeleton } from "@/components/perpscope/badges";

export const Route = createFileRoute("/research")({
  head: () => ({
    meta: [
      { title: "Research View — PerpScope" },
      { name: "description", content: "Quantitative research on funding rate deviations across market cap tiers." },
    ],
  }),
  component: ResearchPage,
});

const TIER_COLOR: Record<Tier, string> = { LARGE: "#3B82F6", MID: "#8B5CF6", SMALL: "#10B981" };
const TIER_LABEL: Record<Tier, string> = { LARGE: "Large Cap", MID: "Mid Cap", SMALL: "Small Cap" };

function Pill({ active, onClick, children }: any) {
  return (
    <button onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${active ? "bg-primary text-primary-foreground" : "bg-elevated text-muted-foreground hover:text-foreground"}`}>
      {children}
    </button>
  );
}

function ResearchPage() {
  const [days, setDays] = useState<30 | 60 | 90 | 180>(90);
  const [methodOpen, setMethodOpen] = useState(false);
  const q = useQuery({ queryKey: ["research", days], queryFn: () => api.research(days) });

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-purple/15 text-purple"><BookOpen className="h-5 w-5" /></span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Research View</h1>
            <p className="text-sm text-muted-foreground">Following He, Manela, Ross &amp; von Wachter (2024) · cross-sectional funding deviation analysis</p>
          </div>
        </div>

        {q.data && (
          <div className="glass-card mt-6 border-l-4 border-l-primary p-5 animate-fade-up">
            <div className="text-xs font-medium uppercase tracking-wider text-primary">Key Finding</div>
            <div className="mt-2 text-base">
              Small-cap altcoins show <span className="font-mono text-lg font-bold text-foreground" data-num>{q.data.ratio_small_large.toFixed(2)}×</span> higher mean absolute ρ deviation than large-cap coins.
            </div>
          </div>
        )}

        <div className="mt-6 flex gap-1.5">
          {[30, 60, 90, 180].map(d => <Pill key={d} active={days === d} onClick={() => setDays(d as any)}>{d}d</Pill>)}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
          {q.isLoading ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-44" />) :
            q.data?.tiers.map(t => (
              <div key={t.tier} className="glass-card p-5 animate-fade-up">
                <TierBadge tier={t.tier} />
                <div className="mt-3 text-xs text-muted-foreground"><span className="font-mono text-foreground" data-num>{t.count}</span> coins</div>
                <div className="mt-3 font-mono text-4xl font-bold tracking-tight" data-num style={{ color: TIER_COLOR[t.tier] }}>
                  {fmtPct(t.mean_abs_rho, 1)}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">Mean |ρ| annualized</div>
                <div className="my-4 border-t border-border" />
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Max |ρ|</span>
                  <span className="font-mono font-semibold" data-num>{fmtPct(t.max_abs_rho, 1)}</span>
                </div>
              </div>
            ))
          }
        </div>

        <div className="glass-card mt-6 p-5 animate-fade-up">
          <div className="mb-1 text-base font-semibold">Market Cap Rank vs Mean |ρ|</div>
          <div className="mb-4 text-xs text-muted-foreground">Smaller coins exhibit systematically larger funding deviations — a cross-sectional anomaly</div>
          <div className="h-[420px] w-full">
            {q.isLoading ? <Skeleton className="h-full w-full" /> : (
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 12, right: 24, bottom: 12, left: 12 }}>
                  <CartesianGrid stroke="var(--color-border)" opacity={0.4} />
                  <XAxis type="number" dataKey="rank" name="Rank" stroke="var(--color-muted-foreground)" fontSize={11} tickLine={false}
                    label={{ value: "Market Cap Rank", position: "insideBottom", offset: -2, fontSize: 11, fill: "var(--color-muted-foreground)" }} />
                  <YAxis type="number" dataKey="mean_abs_rho" name="Mean |ρ|" stroke="var(--color-muted-foreground)" fontSize={11} tickLine={false}
                    tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                    label={{ value: "Mean |ρ|", angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--color-muted-foreground)" }} />
                  <ZAxis range={[80, 80]} />
                  <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ active, payload }: any) => {
                    if (!active || !payload?.[0]) return null;
                    const p = payload[0].payload;
                    return (
                      <div className="rounded-md border border-border bg-card/95 px-3 py-2 text-xs shadow-xl backdrop-blur">
                        <div className="font-semibold text-foreground">{p.symbol} <span className="font-normal text-muted-foreground">· {p.name}</span></div>
                        <div className="mt-1 flex items-center gap-2"><TierBadge tier={p.tier} /></div>
                        <div className="mt-1 text-muted-foreground">Rank: <span className="font-mono text-foreground" data-num>#{p.rank}</span></div>
                        <div className="text-muted-foreground">Mean |ρ|: <span className="font-mono text-foreground" data-num>{fmtPct(p.mean_abs_rho, 2)}</span></div>
                      </div>
                    );
                  }} />
                  {(["LARGE", "MID", "SMALL"] as Tier[]).map(t => (
                    <Scatter key={t} name={TIER_LABEL[t]} data={(q.data?.scatter ?? []).filter(s => s.tier === t)} fill={TIER_COLOR[t]} fillOpacity={0.75} />
                  ))}
                </ScatterChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="glass-card mt-6 animate-fade-up">
          <button onClick={() => setMethodOpen(o => !o)} className="flex w-full items-center justify-between p-5">
            <span className="text-base font-semibold">Methodology</span>
            {methodOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          {methodOpen && (
            <div className="space-y-4 border-t border-border p-5 text-sm leading-relaxed text-muted-foreground">
              <div>
                <div className="text-xs uppercase tracking-wider text-foreground">Research Question</div>
                <p className="mt-1">Do small-cap altcoin perpetuals systematically exhibit larger funding-rate deviations than large-cap perpetuals, after annualization?</p>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-foreground">Formula</div>
                <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-bg-secondary p-3 font-mono text-xs text-foreground">{`ρ_annual = funding_rate × periods_per_year
periods_per_year = 365 × (24 / funding_interval_hours)
opportunity := |ρ_annual| > threshold(fees, slippage)`}</pre>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-foreground">Parameters</div>
                <ul className="mt-1 list-inside list-disc space-y-1">
                  <li>funding_rate: 8-hour funding paid by perp longs to shorts (or vice versa)</li>
                  <li>threshold: cost-adjusted cutoff per fee tier (retail / fund / institution / MM)</li>
                  <li>tier: LARGE (rank ≤ 10), MID (11–60), SMALL (61+)</li>
                </ul>
              </div>
              <div className="text-xs">
                He, Z., Manela, A., Ross, O., &amp; von Wachter, V. (2024). <em>Cross-Sectional Variation in Crypto Perpetual Funding Rates</em>.
              </div>
            </div>
          )}
        </div>
      </main>
      <Footer />
    </div>
  );
}
