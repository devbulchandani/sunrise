import { Link } from "react-router-dom";
import type { MarketEvent } from "../types";
import { urgencyTier } from "../lib/format";
import { cn } from "../lib/cn";
import { ArrowUpRight } from "./icons";

function TickerItem({ event, duplicate }: { event: MarketEvent; duplicate?: boolean }) {
  const tier = urgencyTier(event.urgency);
  const tone =
    tier === "CRITICAL"
      ? "text-bear"
      : tier === "HIGH"
        ? "text-amber"
        : "text-ink-dim";
  return (
    <Link
      to={`/events/${event.id}`}
      tabIndex={duplicate ? -1 : 0}
      aria-hidden={duplicate || undefined}
      className="group flex shrink-0 items-center gap-3 border-r border-edge/70 px-5 py-2.5 transition-colors hover:bg-white/[0.03]"
    >
      <span className={cn("num text-[11px] font-semibold", tone)}>
        {Math.round(event.urgency ?? 0)}
      </span>
      <span className="max-w-[42ch] truncate text-xs text-ink-dim transition-colors group-hover:text-ink">
        {event.headline}
      </span>
      <span className="hidden font-mono text-[9px] uppercase tracking-[0.14em] text-ink-faint lg:inline">
        {(event.category || "other").replace(/_/g, " ")}
      </span>
      <ArrowUpRight className="h-3 w-3 shrink-0 text-ink-faint transition-all duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-amber" />
    </Link>
  );
}

export function Ticker({ events }: { events: MarketEvent[] }) {
  const items = events.filter((event) => event.headline).slice(0, 12);
  if (items.length === 0) return null;

  return (
    <div className="group ticker-pause relative flex overflow-hidden border-y border-edge bg-base-soft/80">
      <div className="z-10 flex shrink-0 items-center gap-2 border-r border-edge bg-base-soft px-4">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-bull opacity-40" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-bull" />
        </span>
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-faint">
          Wire
        </span>
      </div>
      <div className="mask-x relative flex-1 overflow-hidden">
        <div className="ticker-track flex w-max motion-reduce:animate-none">
          {[0, 1].map((copy) => (
            <div key={copy} className="flex" aria-hidden={copy === 1 || undefined}>
              {items.map((event) => (
                <TickerItem key={`${copy}-${event.id}`} event={event} duplicate={copy === 1} />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
