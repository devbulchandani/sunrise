import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  getEvents,
  getScraperHealth,
  getStats,
} from "../services/api";
import { usePolling, useNow } from "../hooks/usePolling";
import { useEventStream } from "../hooks/useEventStream";
import type {
  MarketEvent,
  NewEventPayload,
  ScraperHealth,
  SystemStats,
} from "../types";
import { formatNumber, relativeTime, urgencyTier } from "../lib/format";
import { cn } from "../lib/cn";
import {
  ApiErrorBanner,
  Button,
  EmptyState,
  Panel,
  PanelHeader,
  Pill,
  SectionLabel,
  Skeleton,
  StatBar,
} from "../components/ui";
import { CriticalCard, DevelopingRow, HighImpactCard } from "../components/EventCards";
import { Ticker } from "../components/Ticker";
import { Sparkline, TONE_HEX, type Tone } from "../components/Sparkline";
import { StatusDot } from "../components/StatusDot";
import {
  ArrowUpRight,
  Globe,
  Radar,
  Server,
  Signal,
  Zap,
} from "../components/icons";

const POLL_MS = 30_000;
const FETCH_LIMIT = 120;

interface PulseData {
  events: MarketEvent[];
  stats: SystemStats;
  scrapers: ScraperHealth[];
}

export default function MarketPulse() {
  const [lastSync, setLastSync] = useState<number | null>(null);
  const fetcher = async (): Promise<PulseData> => {
    const [events, stats, scrapers] = await Promise.all([
      getEvents({ limit: FETCH_LIMIT }),
      getStats(),
      getScraperHealth(),
    ]);
    setLastSync(Date.now());
    return { events, stats, scrapers };
  };
  const { data, error, loading, refresh } = usePolling(fetcher, POLL_MS);

  const [incoming, setIncoming] = useState<MarketEvent[]>([]);
  useEventStream({
    onNew: (payload) => upsert(setIncoming, payload),
    onAlert: (payload) => upsert(setIncoming, payload),
  });

  const events = useMemo(() => {
    const seen = new Set<string>();
    const merged: MarketEvent[] = [];
    for (const event of [...incoming, ...(data?.events ?? [])]) {
      const key = String(event.id);
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(event);
    }
    return merged.sort(byRecency);
  }, [data?.events, incoming]);

  const scrapers = data?.scrapers ?? [];
  const stats = data?.stats;

  const critical = events.filter((event) => (event.urgency ?? 0) >= 81);
  const high = events.filter(
    (event) => (event.urgency ?? 0) >= 61 && (event.urgency ?? 0) < 81,
  );
  const developing = events.filter((event) => (event.urgency ?? 0) < 61);

  const online = scrapers.filter((scraper) => scraper.health_status === "HEALTHY").length;
  const avgUrgency = events.length
    ? Math.round(events.reduce((sum, event) => sum + (event.urgency ?? 0), 0) / events.length)
    : 0;
  const signalIndex = useMemo(() => {
    const top = [...events]
      .sort((a, b) => (b.urgency ?? 0) - (a.urgency ?? 0))
      .slice(0, 10);
    if (!top.length) return 0;
    return Math.round(top.reduce((sum, event) => sum + (event.urgency ?? 0), 0) / top.length);
  }, [events]);

  const todayCount = useMemo(() => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    return events.filter(
      (event) => new Date(event.last_updated_at ?? event.first_detected_at ?? 0) >= start,
    ).length;
  }, [events]);

  const buckets = useMemo(
    () =>
      [
        { key: "CRITICAL", label: "Critical 81+", min: 81, max: 100, tone: "bear" as Tone },
        { key: "HIGH", label: "High 61–80", min: 61, max: 80, tone: "amber" as Tone },
        { key: "RELEVANT", label: "Relevant 41–60", min: 41, max: 60, tone: "info" as Tone },
        { key: "MODERATE", label: "Moderate 21–40", min: 21, max: 40, tone: "ink" as Tone },
        { key: "LOW", label: "Low 0–20", min: 0, max: 20, tone: "ink" as Tone },
      ].map((bucket) => ({
        ...bucket,
        count: events.filter((event) => {
          const urgency = event.urgency ?? 0;
          return urgency >= bucket.min && urgency <= bucket.max;
        }).length,
      })),
    [events],
  );

  const topMarkets = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of events) {
      for (const market of event.affected_markets ?? []) {
        counts.set(market, (counts.get(market) ?? 0) + 1);
      }
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  }, [events]);

  const spark = useMemo(
    () =>
      [...events]
        .sort(
          (a, b) =>
            new Date(a.last_updated_at ?? a.first_detected_at ?? 0).getTime() -
            new Date(b.last_updated_at ?? b.first_detected_at ?? 0).getTime(),
        )
        .slice(-18)
        .map((event) => event.urgency ?? 0),
    [events],
  );

  const latest = events.slice(0, 5);

  return (
    <div>
      <div className="mx-auto max-w-[1600px] px-5 pt-6">
        <ApiErrorBanner error={error} onRetry={refresh} />
        {loading && !data ? <PulseSkeleton /> : <Hero
          signalIndex={signalIndex}
          spark={spark}
          critical={critical.length}
          high={high.length}
          online={online}
          totalSources={scrapers.length}
          avgUrgency={avgUrgency}
          todayCount={todayCount}
          totalEvents={stats?.events_detected}
          lastSync={lastSync}
        />}
      </div>

      <div className="mt-8">
        <Ticker events={events} />
      </div>

      <div className="mx-auto mt-8 grid max-w-[1600px] grid-cols-1 gap-6 px-5 pb-16 xl:grid-cols-12">
        <div className="space-y-10 xl:col-span-8">
          <section id="wire">
            <SectionLabel
              index="01"
              right={
                <span className="num text-[11px] text-bear">
                  {critical.length}
                </span>
              }
            >
              Critical signals
            </SectionLabel>
            {critical.length === 0 ? (
              <div className="flex flex-wrap items-center gap-3 rounded-xl border border-edge bg-surface/45 px-4 py-3.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-full border border-edge bg-surface-2 text-ink-faint">
                  <Radar className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <p className="text-xs font-medium text-ink">No critical signals right now.</p>
                  <p className="mt-0.5 text-[11px] text-ink-faint">
                    The desk is quiet. {high.length} high-impact signals are being tracked.
                  </p>
                </div>
                <a
                  href="#high"
                  className="ml-auto inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-amber hover:text-[#ffc25c]"
                >
                  See high impact <ArrowUpRight className="h-3 w-3" />
                </a>
              </div>
            ) : (
              <div className="stagger space-y-4">
                {critical.slice(0, 3).map((event, index) => (
                  <CriticalCard key={String(event.id)} event={event} index={index} />
                ))}
              </div>
            )}
          </section>

          <section id="high">
            <SectionLabel
              index="02"
              right={<span className="num text-[11px] text-amber">{high.length}</span>}
            >
              High impact
            </SectionLabel>
            {high.length === 0 ? (
              <EmptyState title="No high-impact signals right now." />
            ) : (
              <div className="stagger grid grid-cols-1 gap-4 md:grid-cols-2">
                {high.slice(0, 6).map((event, index) => (
                  <HighImpactCard key={String(event.id)} event={event} index={index} />
                ))}
              </div>
            )}
          </section>

          <section>
            <SectionLabel
              index="03"
              right={
                <Link
                  to="/system"
                  className="group inline-flex items-center gap-1.5 text-[11px] text-ink-dim transition-colors hover:text-amber"
                >
                  View the machine
                  <ArrowUpRight className="h-3 w-3" />
                </Link>
              }
            >
              Developing
            </SectionLabel>
            <Panel className="overflow-hidden">
              <PanelHeader
                eyebrow="Lower urgency"
                title="Signals still forming"
                action={
                  <Pill tone="neutral">
                    {Math.min(developing.length, 12)} of {developing.length}
                  </Pill>
                }
              />
              {developing.length === 0 ? (
                <div className="px-5 py-10">
                  <EmptyState title="Nothing developing yet." />
                </div>
              ) : (
                <div className="px-1 py-1">
                  {developing.slice(0, 12).map((event) => (
                    <DevelopingRow key={String(event.id)} event={event} />
                  ))}
                </div>
              )}
            </Panel>
          </section>
        </div>

        <aside className="space-y-5 xl:col-span-4">
          <Panel className="overflow-hidden">
            <PanelHeader
              eyebrow="Read"
              title="Urgency distribution"
              action={<span className="num text-[11px] text-ink-faint">{events.length} live</span>}
            />
            <div className="space-y-3.5 p-5">
              {buckets.map((bucket) => (
                <div key={bucket.key}>
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                      {bucket.label}
                    </span>
                    <span className="num text-[11px] text-ink-dim">{bucket.count}</span>
                  </div>
                  <StatBar
                    value={events.length ? (bucket.count / events.length) * 100 : 0}
                    tone={bucket.tone}
                    height={4}
                  />
                </div>
              ))}
              <div className="flex items-center justify-between border-t border-edge/70 pt-4">
                <span className="label">Median urgency</span>
                <span className="num text-sm font-semibold text-ink">
                  {median(events.map((event) => event.urgency ?? 0))}
                </span>
              </div>
            </div>
          </Panel>

          <Panel className="overflow-hidden">
            <PanelHeader
              eyebrow="Exposure"
              title="Most affected markets"
              action={<Globe className="h-4 w-4 text-ink-faint" />}
            />
            <div className="space-y-3 p-5">
              {topMarkets.length === 0 ? (
                <p className="text-xs text-ink-faint">No market mapping yet.</p>
              ) : (
                topMarkets.map(([market, count]) => (
                  <div key={market}>
                    <div className="mb-1.5 flex items-center justify-between gap-3">
                      <span className="truncate text-xs text-ink-dim">{market}</span>
                      <span className="num text-[10px] text-ink-faint">{count}</span>
                    </div>
                    <StatBar
                      value={(count / Math.max(topMarkets[0][1], 1)) * 100}
                      tone="amber"
                      height={3}
                    />
                  </div>
                ))
              )}
            </div>
          </Panel>

          <Panel className="overflow-hidden">
            <PanelHeader
              eyebrow="Fleet"
              title="Collector pulse"
              action={
                <Link
                  to="/scrapers"
                  className="group inline-flex items-center gap-1 text-[11px] text-ink-faint transition-colors hover:text-amber"
                >
                  All <ArrowUpRight className="h-3 w-3" />
                </Link>
              }
            />
            <div className="p-2">
              {scrapers.slice(0, 6).map((scraper) => (
                <Link
                  key={String(scraper.source_id)}
                  to="/scrapers"
                  className="flex items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-white/[0.03]"
                >
                  <StatusDot status={scraper.health_status} label={false} size="sm" />
                  <span className="min-w-0 flex-1 truncate text-xs text-ink-dim">
                    {scraper.name}
                  </span>
                  <span className="num text-[10px] text-ink-faint">
                    {scraper.last_articles_found ?? 0}
                  </span>
                </Link>
              ))}
              {scrapers.length === 0 && (
                <p className="px-3 py-4 text-xs text-ink-faint">No collectors online.</p>
              )}
            </div>
            <div className="flex items-center justify-between border-t border-edge/70 px-5 py-3">
              <span className="label">Online</span>
              <span className="num text-[11px] text-bull">
                {online}/{scrapers.length || 0}
              </span>
            </div>
          </Panel>

          <Panel className="overflow-hidden">
            <PanelHeader
              eyebrow="Live wire"
              title="Latest signals"
              action={<Zap className="h-4 w-4 text-amber" />}
            />
            <div className="p-2">
              {latest.length === 0 ? (
                <p className="px-3 py-4 text-xs text-ink-faint">Waiting for the next signal.</p>
              ) : (
                latest.map((event) => {
                  const tier = urgencyTier(event.urgency);
                  const tone =
                    tier === "CRITICAL"
                      ? "text-bear"
                      : tier === "HIGH"
                        ? "text-amber"
                        : "text-ink-faint";
                  return (
                    <Link
                      key={String(event.id)}
                      to={`/events/${event.id}`}
                      className="group block rounded-lg px-3 py-2.5 transition-colors hover:bg-white/[0.03]"
                    >
                      <div className="flex items-start gap-2.5">
                        <span className={cn("num mt-0.5 text-[11px] font-semibold", tone)}>
                          {Math.round(event.urgency ?? 0)}
                        </span>
                        <div className="min-w-0">
                          <p className="line-clamp-2 text-xs leading-5 text-ink-dim transition-colors group-hover:text-ink">
                            {event.headline}
                          </p>
                          <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                            {relativeTime(event.last_updated_at ?? event.first_detected_at)}
                          </p>
                        </div>
                      </div>
                    </Link>
                  );
                })
              )}
            </div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}

function Hero({
  signalIndex,
  spark,
  critical,
  high,
  online,
  totalSources,
  avgUrgency,
  todayCount,
  totalEvents,
  lastSync,
}: {
  signalIndex: number;
  spark: number[];
  critical: number;
  high: number;
  online: number;
  totalSources: number;
  avgUrgency: number;
  todayCount: number;
  totalEvents: number | null | undefined;
  lastSync: number | null;
}) {
  useNow(1_000);
  const tone: Tone = signalIndex >= 81 ? "bear" : signalIndex >= 61 ? "amber" : "info";
  const date = new Intl.DateTimeFormat("en-IN", {
    weekday: "long",
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  }).format(new Date());

  return (
    <section className="relative overflow-hidden rounded-3xl border border-edge bg-surface/60 bg-dawn px-6 py-8 shadow-panel sm:px-9 sm:py-10">
      <div className="pointer-events-none absolute inset-0 grid-lines opacity-60" aria-hidden="true" />
      <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-amber/[0.07] blur-3xl" aria-hidden="true" />
      <div className="relative grid gap-10 lg:grid-cols-[1.25fr_0.75fr] lg:gap-12">
        <div className="flex flex-col justify-between">
          <div>
            <div className="mb-6 flex flex-wrap items-center gap-3">
              <Pill tone="amber">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber opacity-50" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber" />
                </span>
                Autonomous desk
              </Pill>
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
                {date} · IST
              </span>
            </div>
            <h1 className="display text-[clamp(2.6rem,5.4vw,4.9rem)] leading-[0.92] text-ink">
              The market,
              <br />
              <span className="italic text-amber">before it moves.</span>
            </h1>
            <p className="mt-5 max-w-xl text-sm leading-6 text-ink-dim">
              Sunrise reads public financial sources, isolates the events that move
              markets, and writes the interpretation next to the fact. No noise, no
              predictions — just the signal, early.
            </p>
          </div>

          <div className="mt-8 flex flex-col gap-5">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-[10px] uppercase tracking-[0.13em] text-ink-faint">
              <span className="inline-flex items-center gap-2">
                <span className="h-1 w-1 rounded-full bg-bull" />
                {online}/{totalSources || 10} collectors online
              </span>
              <span>{formatNumber(totalEvents ?? 0)} events indexed</span>
              <span>{todayCount} today</span>
              <span>
                Synced{" "}
                {lastSync ? relativeTime(new Date(lastSync).toISOString()) : "just now"}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2.5">
              <a href="#wire">
                <Button variant="primary">
                  Read the live wire
                  <ArrowUpRight className="h-4 w-4" />
                </Button>
              </a>
              <Link to="/scrapers">
                <Button variant="secondary">
                  <Server className="h-4 w-4" />
                  Collector health
                </Button>
              </Link>
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
          <div className="rounded-2xl border border-edge-bright/60 bg-base/50 p-5 backdrop-blur-sm sm:col-span-2 lg:col-span-1">
            <div className="flex items-start justify-between">
              <div>
                <p className="label">Signal index</p>
                <p className="mt-1 text-[11px] text-ink-faint">Top 10 events · 0–100</p>
              </div>
              <Signal className="h-4 w-4 text-ink-faint" />
            </div>
            <div className="mt-4 flex items-end gap-5">
              <div className="relative h-16 min-w-0 flex-1">
                <Sparkline data={spark} width={150} height={64} tone={tone} />
                <div className="mt-1 flex justify-between font-mono text-[8px] uppercase tracking-[0.12em] text-ink-faint">
                  <span>18 events ago</span>
                  <span>now</span>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <p className="num text-4xl font-semibold leading-none" style={{ color: TONE_HEX[tone] }}>
                  {String(signalIndex).padStart(2, "0")}
                </p>
                <p className="label mt-2">
                  {signalIndex >= 81
                    ? "Critical"
                    : signalIndex >= 61
                      ? "Elevated"
                      : signalIndex >= 41
                        ? "Relevant"
                        : "Calm"}
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <MiniStat label="Critical" value={critical} tone="text-bear" />
            <MiniStat label="High" value={high} tone="text-amber" />
            <MiniStat label="Avg urgency" value={avgUrgency} tone="text-ink" />
            <MiniStat label="Online" value={`${online}/${totalSources || 10}`} tone="text-bull" />
          </div>
        </div>
      </div>
    </section>
  );
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: string;
}) {
  return (
    <div className="rounded-xl border border-edge bg-base/40 p-4">
      <p className="label mb-2">{label}</p>
      <p className={cn("num text-xl font-semibold leading-none", tone)}>{value}</p>
    </div>
  );
}

function PulseSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-[420px] w-full !rounded-3xl" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Skeleton className="h-44" />
        <Skeleton className="h-44" />
        <Skeleton className="h-44" />
      </div>
    </div>
  );
}

function byRecency(a: MarketEvent, b: MarketEvent): number {
  const ta = new Date(a.last_updated_at ?? a.first_detected_at ?? 0).getTime();
  const tb = new Date(b.last_updated_at ?? b.first_detected_at ?? 0).getTime();
  if (tb !== ta) return tb - ta;
  return (b.urgency ?? 0) - (a.urgency ?? 0);
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return Math.round(
    sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2,
  );
}

function upsert(
  set: React.Dispatch<React.SetStateAction<MarketEvent[]>>,
  event: NewEventPayload,
) {
  set((list) => {
    const index = list.findIndex((item) => String(item.id) === String(event.id));
    if (index >= 0) {
      const next = [...list];
      next[index] = event;
      return next;
    }
    return [event, ...list];
  });
}
