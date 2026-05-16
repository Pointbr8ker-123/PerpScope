import { SIGNALS, type SignalKey, type Tier } from "@/lib/api";
import { cn } from "@/lib/utils";

const tierStyles: Record<Tier, string> = {
  LARGE: "bg-[#3B82F6]/12 text-[#60A5FA] border-[#3B82F6]/25",
  MID: "bg-[#8B5CF6]/12 text-[#A78BFA] border-[#8B5CF6]/25",
  SMALL: "bg-[#10B981]/12 text-[#34D399] border-[#10B981]/25",
};
const tierLabel: Record<Tier, string> = { LARGE: "Large Cap", MID: "Mid Cap", SMALL: "Small Cap" };

export function TierBadge({ tier, className }: { tier: Tier; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium", tierStyles[tier], className)}>
      {tierLabel[tier]}
    </span>
  );
}

export function SignalBadge({
  signal, size = "sm", pulse = true, description,
}: { signal: SignalKey; size?: "xs" | "sm" | "md" | "lg"; pulse?: boolean; description?: string }) {
  const s = SIGNALS[signal];
  const isActive = signal !== "NEUTRAL";
  const ringClass =
    signal === "SHORT_PERP_LONG_SPOT" ? "bg-[#EF4444]/10 border-[#EF4444]/35 text-[#FCA5A5]" :
    signal === "LONG_PERP_SHORT_SPOT" ? "bg-[#3B82F6]/10 border-[#3B82F6]/35 text-[#93C5FD]" :
    "bg-[#475569]/15 border-[#475569]/30 text-[#94A3B8]";
  const sizeClass = {
    xs: "text-[10px] px-1.5 py-0.5 gap-1",
    sm: "text-xs px-2 py-1 gap-1.5",
    md: "text-sm px-2.5 py-1.5 gap-2",
    lg: "text-base px-3.5 py-2 gap-2.5",
  }[size];
  return (
    <div className="inline-flex flex-col items-start">
      <span className={cn("inline-flex items-center rounded-md border font-medium", sizeClass, ringClass)}>
        <span
          className={cn("inline-block rounded-full", size === "lg" ? "h-2 w-2" : "h-1.5 w-1.5", isActive && pulse && "pulse-dot")}
          style={{ background: s.color, color: s.color }}
        />
        <span className="font-mono leading-none">{s.icon}</span>
        <span>{s.label}</span>
      </span>
      {description && <span className="mt-1 text-xs text-muted-foreground">{description}</span>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("relative overflow-hidden rounded-md bg-elevated/60", className)}><div className="shimmer absolute inset-0" /></div>;
}
