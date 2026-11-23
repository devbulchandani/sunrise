import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getEvent } from "../services/api";
import type { EventDetail } from "../types";
import { formatTimestamp, relativeTime } from "../lib/format";
import { cn } from "../lib/cn";
import {
  ArrowUpRight,
  Clock,
  External,
  Globe,
  Layers,
  Radar,
  Shield,
  Sparkle,
} from "../components/icons";
import {
  ApiErrorBanner,
  Button,
  ConfidenceMeter,
  EmptyState,
  Panel,
  PanelHeader,
  Pill,
  Skeleton,
  StatBar,
} from "../components/ui";
import { CategoryChip, SentimentChip, UrgencyBadge } from "../components/chips";
import { RadialGauge, TONE_HEX, type Tone } from "../components/Sparkline";

function impactColor(impact: number | string): string {
  const numeric = Number(impact);
  if (Number.isNaN(numeric)) {
    const normalized = String(impact).toLowerCase();
    if (normalized.includes("pos") || normalized === "bullish") return "text-bull";
    if (normalized.includes("neg") || normalized === "bearish") return "text-bear";
    return "text-ink-dim";
  }
  if (numeric > 0) return "text-bull";
  if (numeric < 0) return "text-bear";
  return "text-ink-dim";
}

function confidenceOf(value: number | string | null | undefined): number | null {
  if (value == null || !Number.isFinite(Number(value))) return null;
  const numeric = Number(value);
  return Math.round(numeric <= 1 ? numeric * 100 : numeric);
}

export default function EventDetail() {
  const { id } = useParams<{ id: string }>();
  const [event, setEvent] = useState<EventDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getEvent(id!)
      .then((next) => {
        if (!cancelled) setEvent(next);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="mx-auto max-w-[1400px] space-y-6 px-5 pb-16 pt-6">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-[320px] w-full !rounded-3xl" />
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          <Skeleton className="h-72 xl:col-span-8" />
          <Skeleton className="h-72 xl:col-span-4" />
        </div>
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="mx-auto max-w-[900px] px-5 pb-16 pt-6">
        <ApiErrorBanner error={error ? new Error(error) : null} />
        <EmptyState
          icon={<Radar className="h-4 w-4" />}
          title="This signal is not available."
          hint="It may have been pruned by retention, or the link is incomplete."
          action={
            <Link to="/">
              <Button variant="primary">Back to the pulse</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const urgency = Math.max(0, Math.min(100, Math.round(event.urgency ?? 0)));
  const tone: Tone = urgency >= 81 ? "bear" : urgency >= 61 ? "amber" : "info";
  const primarySource = event.sources?.[0];
  const sourceHref = primarySource?.article_url || primarySource?.url || undefined;

  return (
    <div className="mx-auto max-w-[1400px] px-5 pb-16 pt-6">
      <Link
        to="/"
        className="group mb-5 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint transition-colors hover:text-amber"
      >
        <span className="transition-transform duration-200 group-hover:-translate-x-0.5">←</span>
        Market pulse
      </Link>

      <header className="relative overflow-hidden rounded-3xl border border-edge bg-surface/60 bg-dawn p-6 shadow-panel sm:p-9">
        <div className="pointer-events-none absolute inset-0 grid-lines opacity-60" aria-hidden="true" />
        <div className="relative">
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <UrgencyBadge urgency={event.urgency} showScore />
            <CategoryChip category={event.category} />
            <SentimentChip sentiment={event.sentiment} />
            {event.analysis_status && (
              <Pill tone={event.analysis_status === "DONE" ? "bull" : "neutral"}>
                {event.analysis_status}
              </Pill>
            )}
          </div>

          <h1 className="display max-w-4xl text-[clamp(2rem,4.2vw,3.8rem)] leading-[1.02] text-ink">
            {event.headline}
          </h1>

          <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[10px] uppercase tracking-[0.13em] text-ink-faint">
            <span className="inline-flex items-center gap-1.5">
              <Clock className="h-3 w-3" />
              First detected {relativeTime(event.first_detected_at)}
            </span>
            <span>{formatTimestamp(event.first_detected_at)}</span>
            {event.last_updated_at && <span>Updated {formatTimestamp(event.last_updated_at)}</span>}
            <span className="inline-flex items-center gap-1.5">
              <Layers className="h-3 w-3" />
              {event.article_count ?? 0} {event.article_count === 1 ? "article" : "articles"}
            </span>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            {event.affected_markets?.slice(0, 6).map((market) => (
              <span
                key={market}
                className="rounded-md border border-edge bg-base/40 px-2.5 py-1 text-[11px] text-ink-dim"
              >
                {market}
              </span>
            ))}
            {sourceHref && (
              <a
                href={sourceHref}
                target="_blank"
                rel="noreferrer"
                className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-amber/30 bg-amber/[0.08] px-3 py-1.5 text-xs font-medium text-amber transition-colors hover:border-amber/60 hover:bg-amber/15"
              >
                Open source <External className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
        </div>
      </header>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="space-y-5 xl:col-span-8">
          <Panel className="overflow-hidden">
            <PanelHeader
              eyebrow="01 · Fact"
              title="What happened"
              action={<Pill tone="bull">Fact</Pill>}
            />
            <div className="p-5 sm:p-6">
              <p className="max-w-[68ch] text-[15px] leading-7 text-ink">
                {event.summary || event.ai_summary || "No factual summary is available yet."}
              </p>
            </div>
          </Panel>

          <Panel className="overflow-hidden border-amber/20">
            <PanelHeader
              eyebrow="02 · Interpretation"
              title="Why it may matter"
              action={<Pill tone="amber"><Sparkle className="h-3 w-3" /> AI read</Pill>}
            />
            <div className="p-5 sm:p-6">
              <p className="max-w-[68ch] text-[15px] leading-7 text-ink-dim">
                {event.reason || event.ai_summary || "The model has not produced an interpretation yet."}
              </p>
              <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                This is interpretation, not a prediction. Model confidence{" "}
                {event.confidence != null ? `${Math.round(Number(event.confidence))}%` : "n/a"}.
              </p>
            </div>
          </Panel>

          <Panel className="overflow-hidden">
            <PanelHeader eyebrow="03 · Assessment" title="How the desk read it" />
            <div className="grid grid-cols-2 gap-px bg-edge/70 sm:grid-cols-4">
              <Assessment label="Sentiment" value={event.sentiment ?? "—"} />
              <Assessment label="Impact" value={event.market_impact ?? "—"} />
              <Assessment label="Confidence" value={event.confidence != null ? `${event.confidence}%` : "—"} />
              <Assessment label="Category" value={(event.category ?? "—").replace(/_/g, " ")} />
            </div>
          </Panel>

          {event.market_context?.results?.length ? (
            <Panel className="overflow-hidden">
              <PanelHeader
                eyebrow="04 · Research"
                title="Market context"
                action={<Pill tone="info">Live research</Pill>}
              />
              <div className="p-5 sm:p-6">
                <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                  Verified via {event.market_context.queries?.join(" · ")}
                </p>
                <ul className="mt-4 divide-y divide-edge/60">
                  {event.market_context.results.slice(0, 6).map((result, index) => (
                    <li key={`${result.url}-${index}`}>
                      <a
                        href={result.url}
                        target="_blank"
                        rel="noreferrer"
                        className="group flex items-start gap-3 py-3 transition-colors"
                      >
                        <span className="num mt-0.5 text-[10px] text-ink-faint">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-sm text-ink-dim transition-colors group-hover:text-ink">
                            {result.title || result.url}
                          </span>
                          {result.snippet && (
                            <span className="mt-1 line-clamp-2 block text-xs leading-5 text-ink-faint">
                              {result.snippet}
                            </span>
                          )}
                        </span>
                        <ArrowUpRight className="ml-auto h-3.5 w-3.5 shrink-0 text-ink-faint transition-all group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-amber" />
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            </Panel>
          ) : null}

          {event.ipo_research ? (
            <Panel className="overflow-hidden">
              <PanelHeader
                eyebrow="05 · Deep dive"
                title={`${event.ipo_research.company_name || "Company"} · IPO research`}
                action={<Pill tone="info">AI research</Pill>}
              />
              <div className="space-y-5 p-5 sm:p-6">
                <p className="max-w-[68ch] text-sm leading-7 text-ink">
                  {event.ipo_research.company_overview}
                </p>
                {event.ipo_research.business_model && (
                  <div>
                    <p className="label mb-2">Business model</p>
                    <p className="text-sm leading-6 text-ink-dim">
                      {event.ipo_research.business_model}
                    </p>
                  </div>
                )}
                {!!event.ipo_research.key_financials?.length && (
                  <div>
                    <p className="label mb-2">Key financials</p>
                    <ul className="space-y-1.5">
                      {event.ipo_research.key_financials.map((item) => (
                        <li key={item} className="flex gap-2 text-sm text-ink-dim">
                          <span className="text-ink-faint">—</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-xl border border-bull/20 bg-bull/[0.05] p-4">
                    <p className="label mb-2 text-bull">Strengths</p>
                    <ul className="space-y-1.5">
                      {(event.ipo_research.strengths || []).map((item) => (
                        <li key={item} className="text-xs leading-5 text-ink-dim">
                          <span className="mr-1.5 text-bull">+</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="rounded-xl border border-bear/20 bg-bear/[0.05] p-4">
                    <p className="label mb-2 text-bear">Risks</p>
                    <ul className="space-y-1.5">
                      {(event.ipo_research.risks || []).map((item) => (
                        <li key={item} className="text-xs leading-5 text-ink-dim">
                          <span className="mr-1.5 text-bear">−</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
                {event.ipo_research.valuation_notes && (
                  <div>
                    <p className="label mb-2">Valuation notes</p>
                    <p className="text-sm leading-6 text-ink-dim">
                      {event.ipo_research.valuation_notes}
                    </p>
                  </div>
                )}
                {!!event.ipo_research.considerations?.length && (
                  <div className="rounded-xl border border-amber/25 bg-amber/[0.06] p-4">
                    <p className="label mb-2 text-amber">Considerations</p>
                    <ul className="space-y-1.5">
                      {event.ipo_research.considerations.map((item) => (
                        <li key={item} className="text-xs leading-5 text-ink-dim">
                          • {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                  Research confidence {event.ipo_research.research_confidence ?? "?"}% ·
                  {event.ipo_research.sources_used?.length
                    ? ` ${event.ipo_research.sources_used.length} sources`
                    : " no external sources"}
                </p>
              </div>
            </Panel>
          ) : null}

          <Panel className="overflow-hidden">
            <PanelHeader
              eyebrow="Coverage"
              title="Article timeline"
              action={<Pill tone="neutral">{event.articles?.length ?? 0} collected</Pill>}
            />
            {!event.articles?.length ? (
              <div className="p-5">
                <EmptyState title="No articles attached yet." />
              </div>
            ) : (
              <ol className="p-5 sm:p-6">
                {[...event.articles]
                  .sort(
                    (a, b) =>
                      new Date(a.published_at ?? a.scraped_at ?? 0).getTime() -
                      new Date(b.published_at ?? b.scraped_at ?? 0).getTime(),
                  )
                  .map((article, index, all) => (
                    <li key={String(article.id)} className="relative flex gap-4 pb-5 last:pb-0">
                      {index < all.length - 1 && (
                        <span className="absolute left-[5px] top-4 h-full w-px bg-edge" aria-hidden="true" />
                      )}
                      <span className="relative mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full border border-amber/70 bg-base" />
                      <div className="min-w-0">
                        <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">
                          {formatTimestamp(article.published_at ?? article.scraped_at)}
                          {article.source_name && (
                            <span className="ml-2 text-amber/80">{article.source_name}</span>
                          )}
                        </p>
                        <a
                          href={article.url ?? "#"}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-1 block text-sm leading-6 text-ink-dim transition-colors hover:text-ink"
                        >
                          {article.title}
                        </a>
                      </div>
                    </li>
                  ))}
              </ol>
            )}
          </Panel>
        </div>

        <aside className="space-y-5 xl:col-span-4">
          <Panel className="overflow-hidden">
            <PanelHeader eyebrow="Signal" title="Urgency" />
            <div className="flex flex-col items-center px-5 py-6">
              <RadialGauge
                value={urgency}
                size={196}
                stroke={9}
                tone={tone}
                label={`Urgency ${urgency} of 100`}
              >
                <span className="num text-5xl font-semibold leading-none" style={{ color: TONE_HEX[tone] }}>
                  {urgency}
                </span>
                <span className="label mt-2">out of 100</span>
              </RadialGauge>
              <p className="mt-4 text-center text-xs leading-5 text-ink-faint">
                {urgency >= 81
                  ? "Critical — the desk would push this immediately."
                  : urgency >= 61
                    ? "High impact — above the alert floor."
                    : "Below the push floor. Tracked, not broadcast."}
              </p>
            </div>
            <div className="border-t border-edge/70 p-5">
              <ConfidenceMeter value={event.confidence} />
            </div>
          </Panel>

          <Panel className="overflow-hidden">
            <PanelHeader
              eyebrow="Exposure"
              title="Affected assets"
              action={<Pill tone="neutral">{event.affected_assets?.length ?? 0}</Pill>}
            />
            <div className="p-5">
              {!event.affected_assets?.length ? (
                <p className="text-xs text-ink-faint">No asset mapping available.</p>
              ) : (
                <ul className="space-y-3">
                  {event.affected_assets.map((asset) => {
                    const confidence = confidenceOf(asset.confidence);
                    return (
                      <li key={asset.symbol}>
                        <div className="mb-1.5 flex items-center justify-between">
                          <span className="num text-xs font-semibold text-ink">{asset.symbol}</span>
                          <span className={cn("font-mono text-[10px] uppercase", impactColor(asset.impact))}>
                            {String(asset.impact)}
                          </span>
                        </div>
                        <StatBar
                          value={confidence ?? 50}
                          tone={
                            String(asset.impact).toLowerCase().includes("pos")
                              ? "bull"
                              : String(asset.impact).toLowerCase().includes("neg")
                                ? "bear"
                                : "ink"
                          }
                          height={3}
                        />
                        {confidence != null && (
                          <p className="mt-1 font-mono text-[9px] text-ink-faint">
                            {confidence}% confidence
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </Panel>

          <Panel className="overflow-hidden">
            <PanelHeader eyebrow="Coverage" title="Sources" />
            <div className="p-2">
              {!event.sources?.length ? (
                <p className="px-3 py-4 text-xs text-ink-faint">No source records attached.</p>
              ) : (
                event.sources.map((source, index) => (
                  <a
                    key={`${source.id}-${index}`}
                    href={source.article_url || source.url || "#"}
                    target="_blank"
                    rel="noreferrer"
                    className="group flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-white/[0.03]"
                  >
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-edge bg-surface-2 font-mono text-[10px] font-semibold text-amber">
                      {String(source.name ?? "S").slice(0, 1).toUpperCase()}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs text-ink-dim transition-colors group-hover:text-ink">
                        {source.name ?? source.url ?? `Source #${source.id}`}
                      </span>
                      <span className="mt-0.5 block font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                        {String(source.type ?? "source")}
                        {source.credibility != null
                          ? ` · ${Math.round(Number(source.credibility) * 100)}% credibility`
                          : ""}
                      </span>
                    </span>
                    <External className="h-3.5 w-3.5 shrink-0 text-ink-faint transition-colors group-hover:text-amber" />
                  </a>
                ))
              )}
            </div>
          </Panel>

          <Panel className="overflow-hidden">
            <PanelHeader eyebrow="Guardrail" title="Read with care" />
            <div className="flex gap-3 p-5">
              <Shield className="mt-0.5 h-4 w-4 shrink-0 text-amber" />
              <p className="text-xs leading-5 text-ink-faint">
                Facts come from public sources. Interpretation is model output and can be
                wrong. Sunrise never recommends buying or selling a security.
              </p>
            </div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}

function Assessment({ label, value }: { label: string; value: string }) {
  const display =
    value === "—" || /^\d/.test(value)
      ? value
      : value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
  return (
    <div className="bg-surface px-4 py-4">
      <p className="label mb-1.5">{label}</p>
      <p className="truncate text-sm font-medium text-ink">{display}</p>
    </div>
  );
}
