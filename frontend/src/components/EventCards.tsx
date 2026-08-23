import { Link } from "react-router-dom";
import type { MarketEvent } from "../types";
import { relativeTime } from "../lib/format";
import { useNow } from "../hooks/usePolling";
import {
  CategoryChip,
  SentimentChip,
  UrgencyBadge,
} from "./chips";

function EventMeta({ event }: { event: MarketEvent }) {
  const now = useNow(30_000);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-ink-faint">
      {event.market_impact != null && (
        <span>
          IMPACT{" "}
          <span className="text-ink-dim">
            {Math.round(Number(event.market_impact))}
          </span>
        </span>
      )}
      {event.confidence != null && (
        <span>
          CONF{" "}
          <span className="text-ink-dim">
            {Math.round(Number(event.confidence))}%
          </span>
        </span>
      )}
      {event.article_count != null && (
        <span>
          SRC <span className="text-ink-dim">{event.article_count}</span>
        </span>
      )}
      <span title={event.last_updated_at ?? undefined}>
        {relativeTime(event.last_updated_at ?? event.first_detected_at)}
        <span className="hidden">{now}</span>
      </span>
    </div>
  );
}

/** CRITICAL tier — urgency ≥ 81, red/orange glow border. */
export function CriticalCard({
  event,
  index = 0,
}: {
  event: MarketEvent;
  index?: number;
}) {
  const bearish =
    (event.sentiment || "").toUpperCase().includes("BEAR");
  return (
    <Link
      to={`/events/${event.id}`}
      style={{ animationDelay: `${Math.min(index * 60, 400)}ms` }}
      className={`block rounded-md border bg-surface p-5 animate-fade-in-up transition-transform duration-150 hover:-translate-y-0.5 ${
        bearish
          ? "border-bear/60 shadow-[0_0_24px_rgba(239,68,68,0.15)] hover:shadow-[0_0_32px_rgba(239,68,68,0.28)]"
          : "border-amber/60 shadow-[0_0_24px_rgba(245,158,11,0.14)] hover:shadow-[0_0_32px_rgba(245,158,11,0.26)]"
      }`}
    >
      <div className="mb-2.5 flex items-center gap-2">
        <UrgencyBadge urgency={event.urgency} />
        <CategoryChip category={event.category} />
        <SentimentChip sentiment={event.sentiment} />
      </div>
      <h3 className="text-lg font-semibold leading-snug text-ink">
        {event.headline}
      </h3>
      {(event.ai_summary || event.summary) && (
        <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-ink-dim">
          {event.ai_summary || event.summary}
        </p>
      )}
      {event.affected_markets?.length ? (
        <p className="mt-1.5 font-mono text-[11px] tracking-wide text-amber/90">
          {event.affected_markets.slice(0, 4).join(" · ")}
        </p>
      ) : null}
      <div className="mt-3">
        <EventMeta event={event} />
      </div>
    </Link>
  );
}

/** HIGH tier — urgency 61–80. */
export function HighImpactCard({
  event,
  index = 0,
}: {
  event: MarketEvent;
  index?: number;
}) {
  return (
    <Link
      to={`/events/${event.id}`}
      style={{ animationDelay: `${Math.min(index * 50, 350)}ms` }}
      className="block rounded-md border border-edge bg-surface p-4 animate-fade-in-up transition-colors hover:border-edge-bright"
    >
      <div className="mb-2 flex items-center gap-2">
        <UrgencyBadge urgency={event.urgency} />
        <CategoryChip category={event.category} />
        <SentimentChip sentiment={event.sentiment} />
      </div>
      <h3 className="font-semibold leading-snug text-ink">
        {event.headline}
      </h3>
      {(event.ai_summary || event.summary) && (
        <p className="mt-1.5 line-clamp-2 text-sm text-ink-dim">
          {event.ai_summary || event.summary}
        </p>
      )}
      <div className="mt-2.5">
        <EventMeta event={event} />
      </div>
    </Link>
  );
}

/** DEVELOPING tier — compact timeline row. */
export function DevelopingRow({
  event,
}: {
  event: MarketEvent;
}) {
  const s = (event.sentiment || "").toUpperCase();
  const glyphColor = s.includes("BEAR")
    ? "text-bear"
    : s.includes("BULL")
      ? "text-bull"
      : "text-ink-faint";
  return (
    <Link
      to={`/events/${event.id}`}
      className="group flex items-center gap-3 border-l-2 border-edge py-2 pl-3 pr-2 transition-colors hover:border-amber/60 hover:bg-surface"
    >
      <span className={`font-mono text-[10px] ${glyphColor}`}>
        {s.includes("BEAR") ? "▼" : s.includes("BULL") ? "▲" : "■"}
      </span>
      <span className="w-10 shrink-0 font-mono text-[11px] text-amber/80">
        {event.urgency != null ? Math.round(Number(event.urgency)) : "—"}
      </span>
      <span className="min-w-0 flex-1 truncate text-sm text-ink-dim transition-colors group-hover:text-ink">
        {event.headline}
      </span>
      <span className="hidden shrink-0 rounded border border-edge px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-ink-faint sm:inline-block">
        {(event.category || "").replace(/_/g, " ") || "general"}
      </span>
      <RowTime ts={event.last_updated_at ?? event.first_detected_at} />
    </Link>
  );
}

function RowTime({ ts }: { ts: string | null | undefined }) {
  useNow(30_000);
  return (
    <span className="shrink-0 font-mono text-[11px] text-ink-faint">
      {relativeTime(ts)}
    </span>
  );
}
