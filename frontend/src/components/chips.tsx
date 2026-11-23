import { cn } from "../lib/cn";
import { sentimentLabel, urgencyTier } from "../lib/format";
import type { UrgencyTier } from "../types";

const TIER_STYLES: Record<
  UrgencyTier,
  { label: string; className: string; dot: string }
> = {
  CRITICAL: {
    label: "Critical",
    className: "border-bear/35 bg-bear/10 text-bear",
    dot: "bg-bear",
  },
  HIGH: {
    label: "High",
    className: "border-amber/35 bg-amber/10 text-amber",
    dot: "bg-amber",
  },
  RELEVANT: {
    label: "Relevant",
    className: "border-info/30 bg-info/10 text-info",
    dot: "bg-info",
  },
  MODERATE: {
    label: "Moderate",
    className: "border-edge-bright bg-surface-2 text-ink-dim",
    dot: "bg-ink-faint",
  },
  LOW: {
    label: "Low",
    className: "border-edge bg-surface-2/60 text-ink-faint",
    dot: "bg-ink-faint/60",
  },
};

export function UrgencyBadge({
  urgency,
  showScore = false,
}: {
  urgency: number | null | undefined;
  showScore?: boolean;
}) {
  const tier = urgencyTier(urgency) as UrgencyTier;
  const style = TIER_STYLES[tier];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.12em]",
        style.className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} />
      {style.label}
      {showScore && (
        <span className="ml-0.5 tabular-nums opacity-70">{Math.round(urgency ?? 0)}</span>
      )}
    </span>
  );
}

const SENTIMENT_STYLES: Record<string, { className: string; glyph: string }> = {
  BULLISH: { className: "border-bull/30 bg-bull/10 text-bull", glyph: "▲" },
  BEARISH: { className: "border-bear/30 bg-bear/10 text-bear", glyph: "▼" },
  NEUTRAL: { className: "border-edge bg-surface-2/50 text-ink-faint", glyph: "■" },
};

export function SentimentChip({ sentiment }: { sentiment: string | null | undefined }) {
  const label = sentimentLabel(sentiment);
  const style = SENTIMENT_STYLES[label];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10px] font-medium uppercase tracking-[0.12em]",
        style.className,
      )}
    >
      <span className="text-[8px] leading-none">{style.glyph}</span>
      {label}
    </span>
  );
}

export function CategoryChip({
  category,
  className,
}: {
  category: string | null | undefined;
  className?: string;
}) {
  if (!category) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-edge bg-transparent px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-dim",
        className,
      )}
    >
      {category.replace(/_/g, " ")}
    </span>
  );
}

export function MarketChip({ market }: { market: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-edge bg-surface-2/50 px-2 py-1 text-[11px] text-ink-dim">
      {market}
    </span>
  );
}
