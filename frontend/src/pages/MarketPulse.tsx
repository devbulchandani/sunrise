import { useMemo, useState } from "react";
import { getEvents } from "../services/api";
import { usePolling, useNow } from "../hooks/usePolling";
import { useEventStream } from "../hooks/useEventStream";
import type { MarketEvent, NewEventPayload } from "../types";
import {
  ApiErrorBanner,
  EmptyState,
  SectionLabel,
  Spinner,
} from "../components/ui";
import {
  CriticalCard,
  DevelopingRow,
  HighImpactCard,
} from "../components/EventCards";
import { formatTimestamp } from "../lib/format";

const POLL_MS = 30_000;
const FETCH_LIMIT = 120;

function byRecency(a: MarketEvent, b: MarketEvent): number {
  const ta = new Date(a.last_updated_at ?? a.first_detected_at ?? 0).getTime();
  const tb = new Date(b.last_updated_at ?? b.first_detected_at ?? 0).getTime();
  if (tb !== ta) return tb - ta;
  return (b.urgency ?? 0) - (a.urgency ?? 0);
}

export default function MarketPulse() {
  const fetcher = () => getEvents({ limit: FETCH_LIMIT });
  const { data, error, loading, refresh } = usePolling(fetcher, POLL_MS);

  // Events delivered instantly over SSE; reconciled away on next poll.
  const [incoming, setIncoming] = useState<MarketEvent[]>([]);
  useEventStream({
    onNew: (p) => upsert(setIncoming, p),
    onAlert: (p) => upsert(setIncoming, p),
  });

  const events = useMemo(() => {
    const seen = new Set<string>();
    const merged: MarketEvent[] = [];
    for (const e of [...incoming, ...(data ?? [])]) {
      const key = String(e.id);
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(e);
    }
    return merged.sort(byRecency);
  }, [data, incoming]);

  const critical = events.filter((e) => (e.urgency ?? 0) >= 81);
  const high = events
    .filter((e) => (e.urgency ?? 0) >= 61 && (e.urgency ?? 0) < 81)
    .slice(0, 6);
  const developing = events.filter((e) => (e.urgency ?? 0) < 61).slice(0, 14);

  return (
    <div className="mx-auto max-w-[1600px] px-5 py-6">
      {/* Hero row */}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-mono text-xl font-bold tracking-[0.2em] text-ink">
            GLOBAL MARKET PULSE
          </h1>
          <p className="mt-1 text-xs text-ink-faint">
            Autonomous detection across {events.length} tracked events · polling
            every {POLL_MS / 1000}s
          </p>
        </div>
        <LastUpdated />
      </div>

      <ApiErrorBanner error={error} onRetry={refresh} />

      {loading && !data ? (
        <div className="flex items-center gap-2 py-24 text-sm text-ink-faint">
          <Spinner /> Loading market intelligence…
        </div>
      ) : (
        <div className="space-y-8">
          <section>
            <SectionLabel
              right={
                <span className="font-mono text-xs text-bear">
                  {critical.length}
                </span>
              }
            >
              Critical Events — Urgency 81+
            </SectionLabel>
            {critical.length === 0 ? (
              <EmptyState
                title="No critical events — markets are quiet."
                hint="Critical alerts (urgency ≥ 81) appear here instantly via the live stream."
              />
            ) : (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
                {critical.map((e, i) => (
                  <CriticalCard key={String(e.id)} event={e} index={i} />
                ))}
              </div>
            )}
          </section>

          <section>
            <SectionLabel
              right={
                <span className="font-mono text-xs text-amber">{high.length}</span>
              }
            >
              High Impact — Urgency 61–80
            </SectionLabel>
            {high.length === 0 ? (
              <EmptyState title="No high-impact events right now." />
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                {high.map((e, i) => (
                  <HighImpactCard key={String(e.id)} event={e} index={i} />
                ))}
              </div>
            )}
          </section>

          <section>
            <SectionLabel>Developing — Lower Urgency</SectionLabel>
            {developing.length === 0 ? (
              <EmptyState
                title="Nothing developing yet."
                hint="Lower-urgency detections will stream in as scrapers report."
              />
            ) : (
              <div className="rounded-md border border-edge bg-surface/50 px-2 py-2 animate-fade-in">
                {developing.map((e) => (
                  <DevelopingRow key={String(e.id)} event={e} />
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function upsert(
  set: React.Dispatch<React.SetStateAction<MarketEvent[]>>,
  e: NewEventPayload,
) {
  set((list) => {
    const idx = list.findIndex((x) => String(x.id) === String(e.id));
    if (idx >= 0) {
      const next = [...list];
      next[idx] = e;
      return next;
    }
    return [e, ...list];
  });
}

function LastUpdated() {
  const now = useNow(1_000);
  return (
    <div className="text-right">
      <p className="label-caps">Last updated</p>
      <p className="font-mono text-sm text-amber">
        {formatTimestamp(new Date(now).toISOString()).slice(11)} UTC
      </p>
    </div>
  );
}
