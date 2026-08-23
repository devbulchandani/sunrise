import { sentimentLabel, urgencyTier } from "../lib/format";

const TIER_STYLES: Record<string, string> = {
  CRITICAL: "border-bear/60 bg-bear/10 text-bear",
  HIGH: "border-amber/60 bg-amber/10 text-amber",
  MODERATE: "border-sky-500/50 bg-sky-500/10 text-sky-400",
  RELEVANT: "border-edge-bright bg-surface-2 text-ink-dim",
};

export function UrgencyBadge({ urgency }: { urgency: number | null | undefined }) {
  const tier = urgencyTier(urgency);
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 font-mono text-[10px] font-bold tracking-[0.12em] ${
        TIER_STYLES[tier]
      }`}
    >
      {tier}
    </span>
  );
}

const SENTIMENT_STYLES: Record<string, string> = {
  BULLISH: "border-bull/50 bg-bull/10 text-bull",
  BEARISH: "border-bear/50 bg-bear/10 text-bear",
  NEUTRAL: "border-edge-bright bg-surface-2 text-ink-dim",
};

export function SentimentChip({
  sentiment,
}: {
  sentiment: string | null | undefined;
}) {
  const s = sentimentLabel(sentiment);
  const glyph = s === "BULLISH" ? "▲" : s === "BEARISH" ? "▼" : "■";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-[0.1em] ${
        SENTIMENT_STYLES[s]
      }`}
    >
      <span className="text-[8px] leading-none">{glyph}</span>
      {s}
    </span>
  );
}

export function CategoryChip({ category }: { category: string | null | undefined }) {
  if (!category) return null;
  return (
    <span className="inline-block rounded border border-edge bg-transparent px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-dim">
      {category.replace(/_/g, " ")}
    </span>
  );
}
