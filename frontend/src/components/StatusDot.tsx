import type { HealthStatus } from "../types";

const HEALTH_STYLES: Record<string, { dot: string; text: string; pulse?: string }> = {
  HEALTHY: { dot: "bg-bull", text: "text-bull" },
  DEGRADED: {
    dot: "bg-amber",
    text: "text-amber",
    pulse: "animate-live-dot",
  },
  FAILED: { dot: "bg-bear", text: "text-bear", pulse: "animate-live-dot" },
  HEALING: { dot: "bg-heal", text: "text-heal", pulse: "animate-heal-dot" },
};

export function StatusDot({
  status,
  label,
  size = "md",
}: {
  status: HealthStatus | string | null | undefined;
  label?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  const key = (status || "").toUpperCase();
  const style = HEALTH_STYLES[key] ?? { dot: "bg-ink-faint", text: "text-ink-faint" };
  const dims =
    size === "lg" ? "h-3 w-3" : size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2";
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={`${dims} rounded-full ${style.dot} ${style.pulse ?? ""} shrink-0`}
      />
      {label !== false && (
        <span
          className={`font-mono text-xs font-semibold tracking-wider ${style.text}`}
        >
          {key || "UNKNOWN"}
        </span>
      )}
    </span>
  );
}

export function LiveDot({ connected }: { connected: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          connected ? "bg-bull animate-live-dot" : "bg-bear"
        }`}
      />
      <span
        className={`font-mono text-[10px] uppercase tracking-[0.15em] ${
          connected ? "text-bull" : "text-bear"
        }`}
      >
        {connected ? "Live" : "Offline"}
      </span>
    </span>
  );
}
