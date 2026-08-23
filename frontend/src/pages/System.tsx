import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getStats } from "../services/api";
import { usePolling } from "../hooks/usePolling";
import type { SystemStats as Stats } from "../types";
import { ApiErrorBanner, Card, SectionLabel, Spinner } from "../components/ui";
import { StatusDot } from "../components/StatusDot";
import { formatNumber } from "../lib/format";

const POLL_MS = 30_000;

function MetricTile({
  label,
  value,
  accent = "text-ink",
}: {
  label: string;
  value: number | null | undefined;
  accent?: string;
}) {
  return (
    <Card className="!p-4">
      <p className="label-caps mb-2">{label}</p>
      <p className={`font-mono text-3xl font-bold tabular-nums ${accent}`}>
        {formatNumber(value)}
      </p>
    </Card>
  );
}

const chartAxis = {
  stroke: "#5a6472",
  fontSize: 11,
  fontFamily: "'JetBrains Mono', monospace",
};

function DarkTooltip({
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
    <div className="rounded border border-edge-bright bg-base px-3 py-2 font-mono text-xs shadow-lg">
      <p className="mb-1 text-ink-faint">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="text-amber">
          {p.name}: {formatNumber(p.value)}
        </p>
      ))}
    </div>
  );
}

export default function System() {
  const fetcher = () => getStats();
  const { data, error, loading, refresh } = usePolling(fetcher, POLL_MS);

  const pipeline = data
    ? [
        { name: "Processed", value: data.jobs_processed ?? 0 },
        { name: "Pending", value: data.jobs_pending ?? 0 },
        { name: "Failed", value: data.jobs_failed ?? 0 },
      ]
    : [];

  const output = data
    ? [
        { name: "Articles", value: data.articles_scraped ?? 0 },
        { name: "Events", value: data.events_detected ?? 0 },
        { name: "Alerts", value: data.alerts_sent ?? 0 },
      ]
    : [];

  const resilience = data
    ? [
        { name: "Failures", value: data.scraper_failures ?? 0 },
        { name: "Healings", value: data.scraper_healings ?? 0 },
        { name: "LLM calls", value: data.llm_calls ?? 0 },
      ]
    : [];

  return (
    <div className="mx-auto max-w-[1600px] px-5 py-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-mono text-xl font-bold tracking-[0.2em] text-ink">
            SYSTEM
          </h1>
          <p className="mt-1 text-xs text-ink-faint">
            Pipeline throughput and autonomous-recovery counters
          </p>
        </div>
        <div className="flex items-center gap-4">
          <StatusDot status={error ? "FAILED" : "HEALTHY"} label={false} />
          <span className="font-mono text-xs text-ink-faint">
            backend {error ? "unreachable" : "reachable"}
          </span>
        </div>
      </div>

      <ApiErrorBanner error={error} onRetry={refresh} />

      {loading && !data ? (
        <div className="flex items-center gap-2 py-24 text-sm text-ink-faint">
          <Spinner /> Loading system stats…
        </div>
      ) : !data ? null : (
        <div className="space-y-8">
          <section>
            <SectionLabel>Key Metrics</SectionLabel>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-7">
              <MetricTile label="Articles Scraped" value={data.articles_scraped} />
              <MetricTile label="Events Detected" value={data.events_detected} />
              <MetricTile label="Alerts Sent" value={data.alerts_sent} />
              <MetricTile
                label="Healings"
                value={data.scraper_healings}
                accent="text-heal"
              />
              <MetricTile
                label="Scraper Failures"
                value={data.scraper_failures}
                accent="text-bear"
              />
              <MetricTile label="LLM Calls" value={data.llm_calls} />
              <MetricTile
                label="Jobs Pending"
                value={data.jobs_pending}
                accent="text-amber"
              />
            </div>
          </section>

          <section>
            <SectionLabel>Job Pipeline</SectionLabel>
            <Card>
              <ChartBlock data={pipeline} color="#f59e0b" height={220} />
            </Card>
          </section>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <section>
              <SectionLabel>Output Volume</SectionLabel>
              <Card>
                <ChartBlock data={output} color="#10b981" height={200} />
              </Card>
            </section>
            <section>
              <SectionLabel>Resilience &amp; AI</SectionLabel>
              <Card>
                <ChartBlock data={resilience} color="#a855f7" height={200} />
              </Card>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}

function ChartBlock({
  data,
  color,
  height,
}: {
  data: Array<{ name: string; value: number }>;
  color: string;
  height: number;
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#1c2530" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ ...chartAxis }}
            tickLine={false}
            axisLine={{ stroke: "#1c2530" }}
          />
          <YAxis
            tick={{ ...chartAxis }}
            tickLine={false}
            axisLine={false}
            width={56}
          />
          <Tooltip content={<DarkTooltip />} cursor={{ fill: "rgba(245,158,11,0.06)" }} />
          <Bar dataKey="value" fill={color} radius={[3, 3, 0, 0]} maxBarSize={64} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
