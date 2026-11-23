import type { Sentiment, UrgencyTier } from "../types";

/** Relative time like "3m ago", "2h ago", "5d ago". */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = Date.now() - then;
  if (diff < 0) return "just now";
  const s = Math.floor(diff / 1000);
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function formatTimeShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function urgencyTier(urgency: number | null | undefined): UrgencyTier {
  const u = urgency ?? 0;
  if (u >= 81) return "CRITICAL";
  if (u >= 61) return "HIGH";
  if (u >= 41) return "RELEVANT";
  if (u >= 21) return "MODERATE";
  return "LOW";
}

export function sentimentLabel(s: string | null | undefined): Sentiment {
  const v = (s || "").toUpperCase();
  if (v.includes("BULL")) return "BULLISH";
  if (v.includes("BEAR") || v.includes("NEG")) return "BEARISH";
  return "NEUTRAL";
}

/** Normalizes a score that may arrive as 0–1 or 0–100. */
export function pct(value: number | null | undefined): number | null {
  if (value == null || Number.isNaN(Number(value))) return null;
  const n = Number(value);
  return n <= 1 ? Math.round(n * 100) : Math.round(n);
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US").format(n);
}

export function formatCurrency(
  value: number | null | undefined,
  currency = "INR",
): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(Number(value));
}

export function signedCurrency(
  value: number | null | undefined,
  currency = "INR",
): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const prefix = Number(value) > 0 ? "+" : "";
  return `${prefix}${formatCurrency(value, currency)}`;
}

const IMPACT_ICON_WORD: Record<string, string> = {
  positive: "tailwind",
  negative: "headwind",
  neutral: "neutral",
  bullish: "tailwind",
  bearish: "headwind",
};

/**
 * Human label for an AI-estimated impact. "positive"/"negative" are the model's
 * asset directions; LOW/MEDIUM/HIGH/CRITICAL is the overall market impact.
 */
export function impactWord(value: string | number | null | undefined): string {
  if (value == null) return "unknown";
  const raw = String(value).trim().toLowerCase();
  if (!raw) return "unknown";
  return IMPACT_ICON_WORD[raw] ?? raw.replace(/_/g, " ").toUpperCase();
}

/** Tone class for an AI-estimated asset direction. */
export function impactTone(value: string | number | null | undefined): "bull" | "bear" | "ink" {
  const word = impactWord(value);
  if (word === "tailwind") return "bull";
  if (word === "headwind") return "bear";
  return "ink";
}
