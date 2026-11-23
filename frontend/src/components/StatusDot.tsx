import type { HealthStatus } from "../types";
import { cn } from "../lib/cn";

const HEALTH_STYLES: Record<
  string,
  { dot: string; text: string; ring: string; pulse?: string }
> = {
  HEALTHY: { dot: "bg-bull", text: "text-bull", ring: "bg-bull/20" },
  DEGRADED: {
    dot: "bg-amber",
    text: "text-amber",
    ring: "bg-amber/20",
    pulse: "animate-pulse-soft",
  },
  FAILED: {
    dot: "bg-bear",
    text: "text-bear",
    ring: "bg-bear/20",
    pulse: "animate-pulse-soft",
  },
  HEALING: {
    dot: "bg-heal",
    text: "text-heal",
    ring: "bg-heal/20",
    pulse: "animate-pulse-soft",
  },
};

export function StatusDot({
  status,
  label = true,
  size = "md",
}: {
  status: HealthStatus | string | null | undefined;
  label?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  const key = (status || "").toUpperCase();
  const style =
    HEALTH_STYLES[key] ?? {
      dot: "bg-ink-faint",
      text: "text-ink-faint",
      ring: "bg-ink-faint/15",
    };
  const dotSize =
    size === "lg" ? "h-2.5 w-2.5" : size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2";
  const ringSize =
    size === "lg" ? "h-5 w-5" : size === "sm" ? "h-3 w-3" : "h-4 w-4";

  return (
    <span className="inline-flex items-center gap-2">
      <span className={cn("relative flex items-center justify-center", ringSize)}>
        <span className={cn("absolute inset-0 rounded-full", style.ring)} />
        <span
          className={cn(
            "relative rounded-full",
            dotSize,
            style.dot,
            style.pulse,
          )}
        />
      </span>
      {label && (
        <span
          className={cn(
            "font-mono text-[10px] font-semibold uppercase tracking-[0.14em]",
            style.text,
          )}
        >
          {key || "UNKNOWN"}
        </span>
      )}
    </span>
  );
}

export function LiveDot({ connected }: { connected: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-2.5 py-1",
        connected
          ? "border-bull/25 bg-bull/[0.07] text-bull"
          : "border-bear/25 bg-bear/[0.07] text-bear",
      )}
      title={connected ? "Live stream connected" : "Live stream offline"}
    >
      <span className="relative flex h-1.5 w-1.5">
        {connected && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-bull opacity-50" />
        )}
        <span
          className={cn(
            "relative inline-flex h-1.5 w-1.5 rounded-full",
            connected ? "bg-bull" : "bg-bear",
          )}
        />
      </span>
      <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.16em]">
        {connected ? "Live" : "Offline"}
      </span>
    </span>
  );
}
