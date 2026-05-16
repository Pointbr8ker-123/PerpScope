import { cn } from "@/lib/utils";

function hash(s: string) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0; return Math.abs(h); }
const PALETTE = [
  ["#3B82F6", "#8B5CF6"], ["#F59E0B", "#EF4444"], ["#10B981", "#3B82F6"],
  ["#8B5CF6", "#EC4899"], ["#06B6D4", "#3B82F6"], ["#F97316", "#EAB308"],
  ["#A855F7", "#6366F1"], ["#14B8A6", "#10B981"],
];

export function CoinAvatar({ symbol, size = 32, className }: { symbol: string; size?: number; className?: string }) {
  const [c1, c2] = PALETTE[hash(symbol) % PALETTE.length];
  return (
    <div
      className={cn("grid shrink-0 place-items-center rounded-full font-bold text-white shadow-inner", className)}
      style={{
        width: size, height: size,
        background: `linear-gradient(135deg, ${c1}, ${c2})`,
        fontSize: size * 0.42,
        textShadow: "0 1px 2px rgba(0,0,0,0.3)",
      }}
    >
      {symbol[0]}
    </div>
  );
}
