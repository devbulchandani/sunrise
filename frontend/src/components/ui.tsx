import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "../lib/cn";
import {
  AlertTriangle,
  ArrowRight,
  Refresh,
} from "./icons";
import { RadialGauge, TONE_HEX, type Tone } from "./Sparkline";

/* ---------------------------------------------------------------- surfaces */

export function Panel({
  children,
  className,
  hover = false,
  id,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  id?: string;
  as?: "div" | "section" | "article" | "aside";
}) {
  return (
    <Tag id={id} className={cn("panel", hover && "panel-hover", className)}>
      {children}
    </Tag>
  );
}

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("panel p-4", className)}>{children}</div>;
}

export function PanelHeader({
  eyebrow,
  title,
  action,
  className,
}: {
  eyebrow?: string;
  title: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 border-b border-edge/70 px-5 py-4",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow && <p className="label mb-1">{eyebrow}</p>}
        <div className="text-sm font-medium text-ink">{title}</div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function SectionLabel({
  children,
  index,
  right,
}: {
  children: ReactNode;
  index?: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div className="flex items-baseline gap-3">
        {index && <span className="num text-[10px] text-amber/70">{index}</span>}
        <h2 className="label">{children}</h2>
      </div>
      {right}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  meta,
  actions,
}: {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0 max-w-3xl">
        <p className="label-amber mb-3 flex items-center gap-2">
          <span className="h-px w-6 bg-amber/60" />
          {eyebrow}
        </p>
        <h1 className="display text-[clamp(2rem,4vw,3.4rem)] leading-[0.98] text-ink">
          {title}
        </h1>
        {description && (
          <p className="mt-4 max-w-xl text-sm leading-6 text-ink-dim">{description}</p>
        )}
        {meta && <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/* ---------------------------------------------------------------- controls */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "border border-amber bg-amber text-base hover:bg-[#ffb43a] hover:border-[#ffb43a]",
  secondary:
    "border border-edge bg-surface-2/60 text-ink hover:border-edge-bright hover:bg-surface-3",
  ghost: "border border-transparent text-ink-dim hover:bg-white/[0.05] hover:text-ink",
  danger: "border border-bear/40 bg-bear/10 text-bear hover:bg-bear/15",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-4 text-sm",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
}) {
  return (
    <button
      className={cn(
        "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-lg font-medium transition-all duration-200 ease-out active:scale-[0.985] disabled:pointer-events-none disabled:opacity-45",
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function IconButton({
  label,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-edge bg-surface-2/50 text-ink-dim transition-all duration-200 hover:border-edge-bright hover:text-ink active:scale-[0.96] disabled:opacity-40",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-edge bg-surface-2 px-1.5 font-mono text-[10px] text-ink-faint">
      {children}
    </kbd>
  );
}

/* ---------------------------------------------------------------- indicators */

const PILL_TONES: Record<string, string> = {
  neutral: "border-edge bg-surface-2/60 text-ink-dim",
  amber: "border-amber/30 bg-amber/10 text-amber",
  bull: "border-bull/30 bg-bull/10 text-bull",
  bear: "border-bear/30 bg-bear/10 text-bear",
  heal: "border-heal/30 bg-heal/10 text-heal",
  info: "border-info/30 bg-info/10 text-info",
};

export function Pill({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: keyof typeof PILL_TONES;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10px] font-medium uppercase tracking-[0.12em]",
        PILL_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Metric({
  label,
  value,
  hint,
  accent = "text-ink",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  accent?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="label mb-2">{label}</p>
      <p className={cn("num text-2xl font-semibold leading-none", accent)}>{value}</p>
      {hint && <p className="mt-2 truncate text-[11px] text-ink-faint">{hint}</p>}
    </div>
  );
}

export function StatBar({
  value,
  tone = "amber",
  height = 4,
  className,
}: {
  value: number;
  tone?: Tone;
  height?: number;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      className={cn("w-full overflow-hidden rounded-full bg-surface-3", className)}
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full transition-all duration-700 ease-out-expo"
        style={{
          width: `${clamped}%`,
          background: `linear-gradient(90deg, ${TONE_HEX[tone]}66, ${TONE_HEX[tone]})`,
        }}
      />
    </div>
  );
}

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
      <div className="mb-2 flex items-baseline justify-between">
        <span className="label">{label}</span>
        <span className="num text-lg font-semibold text-ink">{v}%</span>
      </div>
      <div className="flex gap-1" aria-hidden="true">
        {Array.from({ length: 10 }).map((_, index) => (
          <span
            key={index}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-colors duration-500",
              index < Math.round(v / 10) ? "bg-amber" : "bg-surface-3",
            )}
          />
        ))}
      </div>
    </div>
  );
}

export function UrgencyGauge({ urgency }: { urgency: number | null | undefined }) {
  const value = Math.max(0, Math.min(100, Math.round(urgency ?? 0)));
  const tone: Tone = value >= 81 ? "bear" : value >= 61 ? "amber" : "info";
  return (
    <div className="flex items-center gap-4">
      <RadialGauge value={value} size={76} stroke={5} tone={tone} label={`Urgency ${value} of 100`}>
        <span className="num text-lg font-semibold" style={{ color: TONE_HEX[tone] }}>
          {value}
        </span>
      </RadialGauge>
      <div>
        <p className="label mb-1">Urgency</p>
        <p className="text-sm text-ink-dim">
          {value >= 81
            ? "Critical"
            : value >= 61
              ? "High impact"
              : value >= 41
                ? "Relevant"
                : value >= 21
                  ? "Moderate"
                  : "Low"}
        </p>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- states */

export function EmptyState({
  title,
  hint,
  icon,
  action,
}: {
  title: string;
  hint?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-edge bg-surface/40 px-6 py-12 text-center">
      {icon && (
        <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-full border border-edge bg-surface-2 text-ink-faint">
          {icon}
        </div>
      )}
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint && <p className="mt-1.5 max-w-sm text-xs leading-5 text-ink-faint">{hint}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-edge-bright border-t-amber",
        className,
      )}
      role="status"
      aria-label="Loading"
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-lg bg-gradient-to-r from-surface-2 via-surface-3 to-surface-2",
        className,
      )}
    />
  );
}

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
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-bear/30 bg-bear/[0.07] px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <AlertTriangle className="h-4 w-4 shrink-0 text-bear" />
        <p className="text-xs text-bear">
          {unreachable
            ? "API unreachable — the backend is not responding. Showing the last known data."
            : `Request failed — ${error.message}`}
        </p>
      </div>
      {onRetry && (
        <Button size="sm" variant="danger" onClick={onRetry}>
          <Refresh className="h-3.5 w-3.5" />
          Retry
        </Button>
      )}
    </div>
  );
}

export function Divider({ className }: { className?: string }) {
  return <div className={cn("h-px w-full bg-edge", className)} />;
}

export function ArrowLink({
  href,
  children,
  external = false,
  className,
}: {
  href: string;
  children: ReactNode;
  external?: boolean;
  className?: string;
}) {
  return (
    <a
      href={href}
      {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
      className={cn(
        "group inline-flex items-center gap-1.5 text-xs font-medium text-amber transition-colors hover:text-[#ffc25c]",
        className,
      )}
    >
      {children}
      <ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
    </a>
  );
}
