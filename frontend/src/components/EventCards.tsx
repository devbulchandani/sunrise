import { Link } from "react-router-dom";
import type { MarketEvent } from "../types";
import { impactWord, relativeTime } from "../lib/format";
import { useNow } from "../hooks/usePolling";
import { cn } from "../lib/cn";
import { RadialGauge } from "./Sparkline";
import { CategoryChip, SentimentChip, UrgencyBadge } from "./chips";
import { ArrowUpRight, Clock, Layers } from "./icons";

function EventMeta({ event }: { event: MarketEvent }) {
  useNow(30_000);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
      {event.market_impact && (
        <span>
          AI impact{" "}
          <span className="text-ink-dim">{impactWord(event.market_impact)}</span>
        </span>
      )}
      {event.confidence != null && (
        <span>
          AI confidence{" "}
          <span className="text-ink-dim">{Math.round(Number(event.confidence))}%</span>
        </span>
      )}
      {event.article_count != null && (
        <span className="inline-flex items-center gap-1.5">
          <Layers className="h-3 w-3" />
          {event.article_count} {event.article_count === 1 ? "source" : "sources"}
        </span>
      )}
      <span className="inline-flex items-center gap-1.5">
        <Clock className="h-3 w-3" />
        {relativeTime(event.last_updated_at ?? event.first_detected_at)}
      </span>
    </div>
  );
}

export function CriticalCard({
  event,
  index = 0,
}: {
  event: MarketEvent;
  index?: number;
}) {
  const urgency = Math.round(event.urgency ?? 0);
  return (
    <Link
      to={`/events/${event.id}`}
      style={{ animationDelay: `${Math.min(index * 80, 400)}ms` }}
      className="panel panel-hover group block overflow-hidden !rounded-3xl animate-rise"
    >
      <div className="grid gap-0 md:grid-cols-[220px_1fr]">
        <div className="relative flex flex-col items-center justify-center gap-4 overflow-hidden border-b border-edge/70 bg-gradient-to-b from-bear/[0.09] to-transparent px-6 py-7 md:border-b-0 md:border-r">
          <div className="absolute -left-12 -top-12 h-32 w-32 rounded-full bg-bear/10 blur-3xl" />
          <RadialGauge
            value={urgency}
            size={148}
            stroke={7}
            tone="bear"
            label={`Urgency ${urgency} of 100`}
          >
            <span className="num text-4xl font-semibold leading-none text-bear">
              {urgency}
            </span>
            <span className="label mt-2">Urgency</span>
          </RadialGauge>
          <span className="label">Critical signal</span>
        </div>

        <div className="min-w-0 p-6 sm:p-7">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <UrgencyBadge urgency={event.urgency} showScore />
            <CategoryChip category={event.category} />
            <SentimentChip sentiment={event.sentiment} />
          </div>
          <h3 className="display text-[clamp(1.5rem,2.7vw,2.35rem)] leading-[1.08] text-ink transition-colors group-hover:text-white">
            {event.headline}
          </h3>
          {(event.summary || event.ai_summary) && (
            <p className="mt-3 line-clamp-3 max-w-[62ch] text-sm leading-6 text-ink-dim">
              {event.summary || event.ai_summary}
            </p>
          )}
          {event.affected_markets?.length ? (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {event.affected_markets.slice(0, 5).map((market) => (
                <span
                  key={market}
                  className="rounded-md border border-bear/20 bg-bear/[0.06] px-2 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-bear/90"
                >
                  {market}
                </span>
              ))}
            </div>
          ) : null}
          <div className="mt-5 flex items-end justify-between gap-4">
            <EventMeta event={event} />
            <ArrowUpRight className="h-5 w-5 shrink-0 text-ink-faint transition-all duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-bear" />
          </div>
        </div>
      </div>
    </Link>
  );
}

export function HighImpactCard({
  event,
  index = 0,
}: {
  event: MarketEvent;
  index?: number;
}) {
  const urgency = Math.max(0, Math.min(100, Math.round(event.urgency ?? 0)));
  return (
    <Link
      to={`/events/${event.id}`}
      style={{ animationDelay: `${Math.min(index * 60, 350)}ms` }}
      className="panel panel-hover group flex h-full flex-col p-5 animate-rise"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <UrgencyBadge urgency={event.urgency} showScore />
        <CategoryChip category={event.category} />
      </div>
      <h3 className="text-[15px] font-medium leading-6 text-ink transition-colors group-hover:text-white">
        {event.headline}
      </h3>
      {(event.summary || event.ai_summary) && (
        <p className="mt-2 line-clamp-2 text-xs leading-5 text-ink-dim">
          {event.summary || event.ai_summary}
        </p>
      )}
      {event.affected_markets?.length ? (
        <p className="mt-3 truncate font-mono text-[10px] uppercase tracking-[0.1em] text-amber/80">
          {event.affected_markets.slice(0, 3).join(" · ")}
        </p>
      ) : null}
      <div className="mt-auto pt-4">
        <EventMeta event={event} />
        <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-surface-3">
          <div
            className="h-full rounded-full bg-gradient-to-r from-amber/40 to-amber transition-all duration-700"
            style={{ width: `${urgency}%` }}
          />
        </div>
      </div>
    </Link>
  );
}

export function DevelopingRow({ event }: { event: MarketEvent }) {
  const urgency = Math.round(event.urgency ?? 0);
  const s = (event.sentiment || "").toUpperCase();
  const glyphColor = s.includes("BEAR")
    ? "text-bear"
    : s.includes("BULL")
      ? "text-bull"
      : "text-ink-faint";
  const tierColor =
    urgency >= 61 ? "text-amber" : urgency >= 41 ? "text-info" : "text-ink-dim";

  return (
    <Link
      to={`/events/${event.id}`}
      className="group grid grid-cols-[38px_1fr_auto] items-center gap-3 border-b border-edge/60 px-3 py-3 transition-colors last:border-b-0 hover:bg-white/[0.025] sm:grid-cols-[38px_1fr_auto_auto] sm:gap-4"
    >
      <div className="flex flex-col items-start gap-1">
        <span className={cn("num text-sm font-semibold leading-none", tierColor)}>
          {urgency}
        </span>
        <span className="h-1 w-5 overflow-hidden rounded-full bg-surface-3">
          <span
            className="block h-full rounded-full bg-current opacity-70"
            style={{ width: `${urgency}%` }}
          />
        </span>
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className={cn("text-[9px] leading-none", glyphColor)}>
            {s.includes("BEAR") ? "▼" : s.includes("BULL") ? "▲" : "■"}
          </span>
          <p className="truncate text-sm text-ink-dim transition-colors group-hover:text-ink">
            {event.headline}
          </p>
        </div>
        <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
          {(event.category || "other").replace(/_/g, " ")}
          {event.affected_markets?.length
            ? ` · ${event.affected_markets.slice(0, 2).join(" · ")}`
            : ""}
        </p>
      </div>
      <span className="hidden font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint sm:inline">
        {event.article_count ?? 0} src
      </span>
      <span className="whitespace-nowrap font-mono text-[10px] text-ink-faint">
        {relativeTime(event.last_updated_at ?? event.first_detected_at)}
      </span>
    </Link>
  );
}
