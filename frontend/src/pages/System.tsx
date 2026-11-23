import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getEvents, getScraperHealth, getStats } from "../services/api";
import { usePolling } from "../hooks/usePolling";
import type { MarketEvent, ScraperHealth, SystemStats } from "../types";
import { formatNumber, relativeTime } from "../lib/format";
import { cn } from "../lib/cn";
import {
  ApiErrorBanner,
  EmptyState,
  Metric,
  Panel,
  PanelHeader,
  Pill,
  SectionLabel,
  Skeleton,
  StatBar,
} from "../components/ui";
import { StatusDot } from "../components/StatusDot";
import {
  Bell,
  Database,
  Layers,
  Radar,
  Sparkle,
  SunriseMark,
} from "../components/icons";

const POLL_MS = 30_000;

interface OpsData {
  stats: SystemStats;
  events: MarketEvent[];
  scrapers: ScraperHealth[];
}

const BUCKET_TONES = ["#68768A", "#A6B2C2", "#7DD3FC", "#F5A623", "#FF6B81"];

export default function SystemPage() {
  const fetcher = async (): Promise<OpsData> => {
    const [stats, events, scrapers] = await Promise.all([
      getStats(),
      getEvents({ limit: 200 }),
      getScraperHealth(),
    ]);
    return { stats, events, scrapers };
  };
  const { data, error, loading, refresh } = usePolling(fetcher, POLL_MS);

  const activity = useMemo(() => {
    const events = data?.events ?? [];
    const now = new Date();
    const start = new Date(now);
    start.setMinutes(0, 0, 0);
    start.setHours(start.getHours() - 23);
    const buckets = Array.from({ length: 24 }, (_, index) => {
      const at = new Date(start.getTime() + index * 3_600_000);
      return {
        hour: `${String(at.getHours()).padStart(2, "0")}:00`,
        signals: 0,
      };
    });
    for (const event of events) {
      const at = new Date(event.last_updated_at ?? event.first_detected_at ?? 0);
      const index = Math.floor((at.getTime() - start.getTime()) / 3_600_000);
      if (index >= 0 && index < 24) buckets[index].signals += 1;
    }
    return buckets;
  }, [data?.events]);

  const urgency = useMemo(() => {
    const events = data?.events ?? [];
    const bands = [
      { label: "Low", min: 0, max: 20, fill: BUCKET_TONES[0] },
      { label: "Moderate", min: 21, max: 40, fill: BUCKET_TONES[1] },
      { label: "Relevant", min: 41, max: 60, fill: BUCKET_TONES[2] },
      { label: "High", min: 61, max: 80, fill: BUCKET_TONES[3] },
      { label: "Critical", min: 81, max: 100, fill: BUCKET_TONES[4] },
    ];
    return bands.map((band) => ({
      ...band,
      count: events.filter((event) => {
        const value = event.urgency ?? 0;
        return value >= band.min && value <= band.max;
      }).length,
    }));
  }, [data?.events]);

  const stats = data?.stats;
  const scrapers = data?.scrapers ?? [];
  const pending = stats?.jobs_pending ?? 0;
  const failures = stats?.scraper_failures ?? 0;

  const pipeline = [
    { label: "Collect", value: stats?.articles_scraped ?? 0, icon: Database, hint: "articles indexed" },
    { label: "Cluster", value: stats?.events_detected ?? 0, icon: Radar, hint: "events mapped" },
    { label: "Analyze", value: stats?.llm_calls ?? 0, icon: Sparkle, hint: "model calls" },
    { label: "Notify", value: stats?.alerts_sent ?? 0, icon: Bell, hint: "alerts delivered" },
  ];

  return (
    <div className="mx-auto max-w-[1600px] px-5 pb-16 pt-6">
      <div className="mb-8 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="label-amber mb-3 flex items-center gap-2">
            <span className="h-px w-6 bg-amber/60" />
            Machine · 03
          </p>
          <h1 className="display text-[clamp(2rem,4vw,3.4rem)] leading-[0.98] text-ink">
            Operations
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-ink-dim">
            The machinery behind the desk: ingestion, clustering, model calls, and
            delivery. Counters are durable; nothing here is a sampled estimate.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Pill tone={pending > 0 ? "amber" : "bull"}>
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-40" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
            </span>
            {pending > 0 ? `${pending} queued` : "queue clear"}
          </Pill>
          <Pill tone={failures > 0 ? "bear" : "neutral"}>{formatNumber(failures)} failures</Pill>
        </div>
      </div>

      <ApiErrorBanner error={error} onRetry={refresh} />

      {loading && !data ? (
        <div className="space-y-6">
          <Skeleton className="h-28 w-full" />
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Skeleton className="h-80 lg:col-span-2" />
            <Skeleton className="h-80" />
          </div>
        </div>
      ) : !stats ? (
        <EmptyState
          icon={<SunriseMark className="h-4 w-4" />}
          title="No operations data yet."
          hint="The backend has not reported counters. Check the API and try again."
        />
      ) : (
        <>
          <Panel className="mb-6 overflow-hidden">
            <div className="grid grid-cols-2 divide-x divide-y divide-edge/70 sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
              <MetricCell label="Articles" value={formatNumber(stats.articles_scraped)} hint="In retention window" />
              <MetricCell label="Events" value={formatNumber(stats.events_detected)} hint="Clustered signals" />
              <MetricCell label="Alerts sent" value={formatNumber(stats.alerts_sent)} hint="All channels" />
              <MetricCell label="LLM calls" value={formatNumber(stats.llm_calls)} hint="Durable counter" accent="text-amber" />
              <MetricCell label="Failures" value={formatNumber(stats.scraper_failures)} hint="Run-level errors" accent="text-bear" />
              <MetricCell label="Pending" value={formatNumber(stats.jobs_pending)} hint="Queue depth" accent="text-heal" />
            </div>
          </Panel>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Panel className="overflow-hidden lg:col-span-2">
              <PanelHeader
                eyebrow="Throughput"
                title="Signals per hour"
                action={<Pill tone="neutral">Last 24 hours</Pill>}
              />
              <div className="h-[280px] p-4">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={activity} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="activityFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#F5A623" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#F5A623" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="hour"
                      tick={{ fill: "#68768A", fontSize: 9, fontFamily: "JetBrains Mono" }}
                      tickLine={false}
                      axisLine={{ stroke: "#1A2433" }}
                      interval={5}
                    />
                    <YAxis
                      tick={{ fill: "#68768A", fontSize: 9, fontFamily: "JetBrains Mono" }}
                      tickLine={false}
                      axisLine={false}
                      width={28}
                      allowDecimals={false}
                    />
                    <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#2A3A50", strokeDasharray: "3 3" }} />
                    <Area
                      type="monotone"
                      dataKey="signals"
                      stroke="#F5A623"
                      strokeWidth={1.8}
                      fill="url(#activityFill)"
                      dot={false}
                      activeDot={{ r: 3, fill: "#F5A623", stroke: "#05080D", strokeWidth: 2 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Panel>

            <Panel className="overflow-hidden">
              <PanelHeader
                eyebrow="Distribution"
                title="Urgency mix"
                action={<span className="num text-[11px] text-ink-faint">{data?.events.length ?? 0}</span>}
              />
              <div className="p-4">
                <div className="h-[190px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={urgency} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
                      <XAxis
                        dataKey="label"
                        tick={{ fill: "#68768A", fontSize: 8, fontFamily: "JetBrains Mono" }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis hide />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                      <Bar dataKey="count" radius={[3, 3, 0, 0]} maxBarSize={28}>
                        {urgency.map((entry) => (
                          <Cell key={entry.label} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-4 flex items-center justify-between border-t border-edge/70 pt-3">
                  <span className="label">Top bands</span>
                  <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.1em]">
                    <span className="flex items-center gap-1.5 text-ink-faint">
                      <span className="h-1.5 w-1.5 rounded-full bg-amber" />
                      High <span className="text-ink-dim">{urgency[3].count}</span>
                    </span>
                    <span className="flex items-center gap-1.5 text-ink-faint">
                      <span className="h-1.5 w-1.5 rounded-full bg-bear" />
                      Critical <span className="text-ink-dim">{urgency[4].count}</span>
                    </span>
                  </div>
                </div>
              </div>
            </Panel>
          </div>

          <section className="mt-10">
            <SectionLabel index="01">Pipeline</SectionLabel>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {pipeline.map((node, index) => {
                const Icon = node.icon;
                return (
                  <div key={node.label} className="relative">
                    <Panel className="h-full p-5">
                      <div className="mb-5 flex items-center justify-between">
                        <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-edge bg-surface-2 text-amber">
                          <Icon className="h-4 w-4" />
                        </span>
                        <span className="num text-[10px] text-ink-faint">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                      </div>
                      <p className="num text-2xl font-semibold text-ink">
                        {formatNumber(node.value)}
                      </p>
                      <p className="mt-1 text-xs text-ink-dim">{node.label}</p>
                      <p className="mt-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
                        {node.hint}
                      </p>
                    </Panel>
                    {index < pipeline.length - 1 && (
                      <span className="absolute -right-2.5 top-1/2 z-10 hidden -translate-y-1/2 text-edge-bright lg:block">
                        →
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            <p className="mt-3 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
              Lifetime totals from the operational counters.
            </p>
          </section>

          <section className="mt-10">
            <SectionLabel
              index="02"
              right={<Pill tone={scrapers.every((s) => s.health_status === "HEALTHY") ? "bull" : "amber"}>{scrapers.length} collectors</Pill>}
            >
              Source health
            </SectionLabel>
            <Panel className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse">
                  <thead>
                    <tr className="border-b border-edge/70">
                      {["Collector", "Status", "Success 24h", "Last run", "Articles", "Last error"].map((heading) => (
                        <th
                          key={heading}
                          className="px-5 py-3 text-left font-mono text-[9px] font-medium uppercase tracking-[0.14em] text-ink-faint"
                        >
                          {heading}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {scrapers.map((scraper) => (
                      <tr key={String(scraper.source_id)} className="border-b border-edge/50 last:border-b-0">
                        <td className="px-5 py-3">
                          <p className="text-xs text-ink">{scraper.name}</p>
                          <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                            {scraper.slug} · v{scraper.strategy_version ?? "?"}
                          </p>
                        </td>
                        <td className="px-5 py-3">
                          <StatusDot status={scraper.health_status} />
                        </td>
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-3">
                            <StatBar
                              value={(scraper.success_rate_24h ?? 0) * 100}
                              tone={(scraper.success_rate_24h ?? 0) >= 0.8 ? "bull" : (scraper.success_rate_24h ?? 0) >= 0.5 ? "amber" : "bear"}
                              height={3}
                              className="w-20"
                            />
                            <span className="num text-[10px] text-ink-dim">
                              {scraper.success_rate_24h != null
                                ? `${Math.round(scraper.success_rate_24h * 100)}%`
                                : "—"}
                            </span>
                          </div>
                        </td>
                        <td className="px-5 py-3 font-mono text-[10px] text-ink-faint">
                          {relativeTime(scraper.last_run_at)}
                        </td>
                        <td className="px-5 py-3 num text-[11px] text-ink-dim">
                          {scraper.last_articles_found ?? "—"}
                        </td>
                        <td className="px-5 py-3">
                          <span className={cn("font-mono text-[10px]", scraper.last_error_type ? "text-bear" : "text-ink-faint")}>
                            {scraper.last_error_type ?? "—"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </section>

          <section className="mt-10">
            <SectionLabel index="03">Model</SectionLabel>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <Panel className="p-5">
                <p className="label mb-2">Analysis provider</p>
                <p className="text-sm text-ink">OpenAI-compatible</p>
                <p className="mt-1 text-xs leading-5 text-ink-faint">
                  Provider-agnostic client with structured output validation. Falls back
                  cleanly when the model is unavailable.
                </p>
              </Panel>
              <Panel className="p-5">
                <p className="label mb-2">Model calls</p>
                <p className="num text-2xl font-semibold text-amber">{formatNumber(stats.llm_calls)}</p>
                <p className="mt-1 text-xs leading-5 text-ink-faint">
                  Counted at the client boundary, including healing candidates and
                  research passes.
                </p>
              </Panel>
              <Panel className="p-5">
                <p className="label mb-2">Interpretation guard</p>
                <p className="flex items-center gap-2 text-sm text-ink">
                  <Layers className="h-4 w-4 text-amber" />
                  Fact / read split
                </p>
                <p className="mt-1 text-xs leading-5 text-ink-faint">
                  Every event carries what happened and a separate, labelled interpretation
                  with confidence.
                </p>
              </Panel>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function MetricCell({
  label,
  value,
  hint,
  accent = "text-ink",
}: {
  label: string;
  value: string;
  hint: string;
  accent?: string;
}) {
  return (
    <div className="p-5">
      <Metric label={label} value={value} hint={hint} accent={accent} />
    </div>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number; name?: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-edge bg-surface px-3 py-2 shadow-xl">
      <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
        {label}
      </p>
      {payload.map((item, index) => (
        <p key={index} className="num text-xs text-amber">
          {formatNumber(item.value)} {item.name === "count" ? "signals" : ""}
        </p>
      ))}
    </div>
  );
}
