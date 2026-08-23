import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getEvent } from "../services/api";
import type { EventDetail } from "../types";
import {
  Card,
  ConfidenceMeter,
  EmptyState,
  SectionLabel,
  Spinner,
  UrgencyGauge,
} from "../components/ui";
import {
  CategoryChip,
  SentimentChip,
  UrgencyBadge,
} from "../components/chips";
import { formatTimestamp, relativeTime } from "../lib/format";

function impactColor(impact: number | string): string {
  const n = Number(impact);
  if (Number.isNaN(n)) return "border-edge-bright bg-surface-2 text-ink-dim";
  if (n > 0) return "border-bull/50 bg-bull/10 text-bull";
  if (n < 0) return "border-bear/50 bg-bear/10 text-bear";
  return "border-edge-bright bg-surface-2 text-ink-dim";
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
      .then((e) => {
        if (!cancelled) setEvent(e);
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

  return (
    <div className="mx-auto max-w-[1200px] px-5 py-6">
      <Link
        to="/"
        className="mb-5 inline-flex items-center gap-2 rounded border border-edge px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-ink-dim transition-colors hover:border-edge-bright hover:text-ink"
      >
        ← Back to Market Pulse
      </Link>

      {loading ? (
        <div className="flex items-center gap-2 py-24 text-sm text-ink-faint">
          <Spinner /> Loading event…
        </div>
      ) : error || !event ? (
        <EmptyState
          title={error ?? "Event not found."}
          hint="It may have been pruned or is still being analyzed."
        />
      ) : (
        <div className="space-y-6 animate-fade-in">
          {/* Header */}
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <UrgencyBadge urgency={event.urgency} />
              <CategoryChip category={event.category} />
              <SentimentChip sentiment={event.sentiment} />
              {event.analysis_status && (
                <span className="rounded border border-edge px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-widest text-ink-faint">
                  analysis: {event.analysis_status}
                </span>
              )}
            </div>
            <h1 className="text-2xl font-bold leading-tight text-ink">
              {event.headline}
            </h1>
            <p className="mt-2 font-mono text-xs text-ink-faint">
              First detected {relativeTime(event.first_detected_at)} ·{" "}
              {formatTimestamp(event.first_detected_at)}
              {event.last_updated_at &&
                ` · updated ${formatTimestamp(event.last_updated_at)}`}
              {event.article_count != null && ` · ${event.article_count} articles`}
            </p>
          </div>

          {/* WHAT HAPPENED */}
          <section>
            <SectionLabel>What Happened</SectionLabel>
            <Card>
              <p className="text-sm leading-relaxed text-ink">
                {event.summary || "No factual summary available yet."}
              </p>
            </Card>
          </section>

          {/* WHY IT MAY MATTER — AI interpretation, explicitly labeled */}
          {(event.ai_summary || event.reason) && (
            <section>
              <SectionLabel
                right={
                  <span className="rounded border border-heal/50 bg-heal/10 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-heal">
                    AI Interpretation — not fact
                  </span>
                }
              >
                Why It May Matter
              </SectionLabel>
              <Card className="border-heal/20">
                <p className="text-sm leading-relaxed text-ink-dim">
                  {event.ai_summary || event.reason}
                </p>
              </Card>
            </section>
          )}

          {/* AI ASSESSMENT */}
          <section>
            <SectionLabel>AI Assessment</SectionLabel>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Card>
                <ConfidenceMeter value={event.confidence} label="Model Confidence" />
              </Card>
              <Card>
                <UrgencyGauge urgency={event.urgency} />
              </Card>
            </div>
          </section>

          {/* AFFECTED MARKETS */}
          {event.affected_markets?.length ? (
            <section>
              <SectionLabel>Markets Potentially Affected</SectionLabel>
              <div className="flex flex-wrap gap-2">
                {event.affected_markets.map((m) => (
                  <span
                    key={m}
                    className="rounded border border-edge bg-surface px-3 py-1.5 text-xs font-medium tracking-wide text-ink"
                  >
                    {m}
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          {/* AFFECTED ASSETS */}
          <section>
            <SectionLabel>Affected Assets</SectionLabel>
            {!event.affected_assets?.length ? (
              <EmptyState title="No asset mapping available for this event." />
            ) : (
              <div className="flex flex-wrap gap-2">
                {event.affected_assets.map((a) => {
                  const conf =
                    a.confidence != null && Number.isFinite(Number(a.confidence))
                      ? Math.round(
                          Number(a.confidence) <= 1
                            ? Number(a.confidence) * 100
                            : Number(a.confidence),
                        )
                      : null;
                  return (
                    <div
                      key={a.symbol}
                      className={`flex items-center gap-2 rounded border px-3 py-2 ${impactColor(
                        a.impact,
                      )}`}
                    >
                      <span className="font-mono text-sm font-bold">{a.symbol}</span>
                      <span className="font-mono text-xs opacity-80">
                        {Number(a.impact) > 0
                          ? `+${a.impact}`
                          : String(a.impact)}
                      </span>
                      {conf != null && (
                        <span className="font-mono text-[10px] opacity-60">
                          {conf}%
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* SOURCES */}
          <section>
            <SectionLabel>Sources</SectionLabel>
            {!event.sources?.length ? (
              <EmptyState title="No source records attached." />
            ) : (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {event.sources.map((s, i) => (
                  <a
                    key={`${s.id}-${i}`}
                    href={s.url ?? "#"}
                    target="_blank"
                    rel="noreferrer"
                    className="group flex items-center justify-between rounded-md border border-edge bg-surface px-3 py-2.5 transition-colors hover:border-edge-bright"
                  >
                    <span className="truncate text-sm text-ink-dim group-hover:text-ink">
                      {s.name ?? s.url ?? `Source #${s.id}`}
                    </span>
                    <svg
                      className="ml-2 h-3 w-3 shrink-0 text-ink-faint"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M7 17L17 7M7 7h10v10" />
                    </svg>
                  </a>
                ))}
              </div>
            )}
          </section>

          {/* ARTICLES TIMELINE */}
          <section>
            <SectionLabel>Articles Timeline</SectionLabel>
            {!event.articles?.length ? (
              <EmptyState title="No articles collected yet." />
            ) : (
              <div className="space-y-0">
                {[...event.articles]
                  .sort(
                    (a, b) =>
                      new Date(a.published_at ?? a.scraped_at ?? 0).getTime() -
                      new Date(b.published_at ?? b.scraped_at ?? 0).getTime(),
                  )
                  .map((a, i) => (
                    <div key={String(a.id)} className="relative flex gap-4 pb-4 pl-6">
                      {/* timeline rail */}
                      <span className="absolute left-[7px] top-1.5 h-full w-px bg-edge last:hidden" style={{ display: i === event.articles!.length - 1 ? "none" : undefined }} />
                      <span className="absolute left-[3px] top-1.5 h-2 w-2 rounded-full border border-amber bg-base" />
                      <div className="min-w-0 flex-1">
                        <p className="font-mono text-[11px] text-ink-faint">
                          {formatTimestamp(a.published_at ?? a.scraped_at)}
                          {a.source_name && (
                            <span className="ml-2 text-amber/70">{a.source_name}</span>
                          )}
                        </p>
                        <a
                          href={a.url ?? "#"}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-0.5 block truncate text-sm text-ink transition-colors hover:text-amber"
                          title={a.title}
                        >
                          {a.title}
                        </a>
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
