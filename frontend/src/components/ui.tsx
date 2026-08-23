import type { ReactNode } from "react";

/** Small caps uppercase section header with tracking — used on every page. */
export function SectionLabel({
  children,
  right,
}: {
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="label-caps">{children}</h2>
      {right && <div>{right}</div>}
    </div>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-md border border-edge bg-surface p-4 animate-fade-in ${className}`}
    >
      {children}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-md border border-dashed border-edge px-6 py-10 text-center animate-fade-in">
      <p className="font-mono text-sm text-ink-dim">{title}</p>
      {hint && <p className="mt-1 text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`h-4 w-4 animate-spin text-ink-faint ${className}`}
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        className="opacity-20"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        d="M22 12a10 10 0 0 0-10-10"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Banner shown when the API is unreachable, with a retry action. */
export function ApiErrorBanner({
  error,
  onRetry,
}: {
  error: Error | null;
  onRetry?: () => void;
}) {
  if (!error) return null;
  const unreachable = error.message === "API unreachable";
  return (
    <div className="mb-4 flex items-center justify-between rounded-md border border-bear/40 bg-bear/10 px-4 py-2.5 animate-fade-in">
      <p className="font-mono text-xs text-bear">
        {unreachable
          ? "API UNREACHABLE — backend not responding at /api. Data shown may be stale."
          : `API ERROR — ${error.message}`}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded border border-bear/50 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-bear transition-colors hover:bg-bear/20"
        >
          Retry
        </button>
      )}
    </div>
  );
}

/** Horizontal confidence meter, 0–100. */
export function ConfidenceMeter({
  value,
  label = "Confidence",
}: {
  value: number | null | undefined;
  label?: string;
}) {
  const v = Math.max(0, Math.min(100, Math.round(value ?? 0)));
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="label-caps">{label}</span>
        <span className="font-mono text-lg font-semibold text-amber">{v}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-gradient-to-r from-amber/40 to-amber transition-all duration-500"
          style={{ width: `${v}%` }}
        />
      </div>
    </div>
  );
}

/** Urgency gauge 0–100 rendered as a gradient bar with a position marker. */
export function UrgencyGauge({ urgency }: { urgency: number | null | undefined }) {
  const u = Math.max(0, Math.min(100, Math.round(urgency ?? 0)));
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="label-caps">Urgency</span>
        <span className="font-mono text-lg font-semibold text-amber">
          {u}
          <span className="text-xs text-ink-faint">/100</span>
        </span>
      </div>
      <div className="relative h-1.5 w-full overflow-hidden rounded-full">
        <div className="absolute inset-0 bg-gradient-to-r from-emerald-500 via-amber to-bear opacity-80" />
        <div
          className="absolute top-[-3px] h-[13px] w-[3px] rounded-sm bg-white shadow-[0_0_6px_rgba(255,255,255,0.8)] transition-all duration-500"
          style={{ left: `calc(${u}% - 1.5px)` }}
        />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[9px] uppercase tracking-widest text-ink-faint">
        <span>Calm</span>
        <span>Severe</span>
      </div>
    </div>
  );
}
