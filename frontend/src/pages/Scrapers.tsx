import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  getHealingHistory,
  getScraperArticles,
  getScraperHealth,
  healScraper,
  runScraper,
  type ScraperArticle,
} from "../services/api";
import { usePolling } from "../hooks/usePolling";
import { useEventStream } from "../hooks/useEventStream";
import type {
  HealingEvent,
  HealingTimelineStep,
  ScraperFailurePayload,
  ScraperHealedPayload,
  ScraperHealth,
} from "../types";
import { formatTimestamp, pct, relativeTime } from "../lib/format";
import { cn } from "../lib/cn";
import {
  ApiErrorBanner,
  Button,
  EmptyState,
  IconButton,
  Metric,
  Panel,
  PanelHeader,
  Pill,
  SectionLabel,
  Skeleton,
  StatBar,
  Spinner,
} from "../components/ui";
import { StatusDot } from "../components/StatusDot";
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  Clock,
  External,
  Refresh,
  Server,
  X,
  Zap,
} from "../components/icons";

const POLL_MS = 30_000;

type Filter = "ALL" | "HEALTHY" | "DEGRADED" | "HEALING";

export default function Scrapers() {
  const fetcher = () => getScraperHealth();
  const { data, error, loading, refresh } = usePolling(fetcher, POLL_MS);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [healedBanner, setHealedBanner] = useState<ScraperHealedPayload | null>(null);
  const [failureFlash, setFailureFlash] = useState<ScraperFailurePayload | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [history, setHistory] = useState<HealingEvent[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [selectedEventIdx, setSelectedEventIdx] = useState(0);
  const [articlesFor, setArticlesFor] = useState<ScraperHealth | null>(null);
  const [articles, setArticles] = useState<ScraperArticle[] | null>(null);
  const [articlesError, setArticlesError] = useState<string | null>(null);

  useEventStream({
    onHealed: (payload) => {
      setHealedBanner(payload);
      refresh();
    },
    onScraperFailure: (payload) => {
      setFailureFlash(payload);
      refresh();
    },
  });

  useEffect(() => {
    if (!healedBanner) return;
    const timer = window.setTimeout(() => setHealedBanner(null), 15_000);
    return () => window.clearTimeout(timer);
  }, [healedBanner]);

  useEffect(() => {
    if (!failureFlash) return;
    const timer = window.setTimeout(() => setFailureFlash(null), 10_000);
    return () => window.clearTimeout(timer);
  }, [failureFlash]);

  const scrapers = data ?? [];
  const filtered = useMemo(() => {
    if (filter === "ALL") return scrapers;
    if (filter === "HEALTHY") return scrapers.filter((s) => s.health_status === "HEALTHY");
    if (filter === "HEALING") return scrapers.filter((s) => s.health_status === "HEALING");
    return scrapers.filter((s) => s.health_status !== "HEALTHY" && s.health_status !== "HEALING");
  }, [scrapers, filter]);

  const healthy = scrapers.filter((s) => s.health_status === "HEALTHY").length;
  const needsAttention = scrapers.length - healthy;
  const avgSuccess = (() => {
    const values = scrapers
      .map((s) => s.success_rate_24h)
      .filter((value): value is number => value != null);
    if (!values.length) return null;
    return Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 100);
  })();
  const healingAttempts = scrapers.reduce(
    (sum, s) => sum + (s.healing_attempts_total ?? 0),
    0,
  );

  useEffect(() => {
    if (!selectedSourceId && scrapers.length > 0) {
      const withHealing = scrapers.find((s) => (s.healing_attempts_total ?? 0) > 0);
      setSelectedSourceId(String((withHealing ?? scrapers[0]).source_id));
    }
  }, [scrapers, selectedSourceId]);

  useEffect(() => {
    if (!selectedSourceId) return;
    let cancelled = false;
    setHistoryLoading(true);
    setHistoryError(null);
    getHealingHistory(selectedSourceId)
      .then((events) => {
        if (cancelled) return;
        setHistory(
          [...events].sort(
            (a, b) =>
              new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime(),
          ),
        );
        setSelectedEventIdx(0);
      })
      .catch((err: Error) => {
        if (!cancelled) setHistoryError(err.message);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedSourceId]);

  const selectedEvent = history[selectedEventIdx] ?? null;
  const selectedSource = scrapers.find((s) => String(s.source_id) === selectedSourceId);

  const openArticles = async (scraper: ScraperHealth) => {
    setArticlesFor(scraper);
    setArticles(null);
    setArticlesError(null);
    try {
      setArticles(await getScraperArticles(scraper.source_id));
    } catch (err) {
      setArticlesError(err instanceof Error ? err.message : "Could not load articles");
    }
  };

  return (
    <div className="mx-auto max-w-[1600px] px-5 pb-16 pt-6">
      <div className="mb-8 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="label-amber mb-3 flex items-center gap-2">
            <span className="h-px w-6 bg-amber/60" />
            Fleet · 02
          </p>
          <h1 className="display text-[clamp(2rem,4vw,3.4rem)] leading-[0.98] text-ink">
            Collector health
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-ink-dim">
            Every source has a versioned strategy. When a page changes, the fleet notices,
            attempts a repair, and proves it against real HTML before resuming.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Pill tone={needsAttention ? "amber" : "bull"}>
            {healthy}/{scrapers.length || 0} healthy
          </Pill>
          <Button size="sm" variant="secondary" onClick={refresh}>
            <Refresh className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      <ApiErrorBanner error={error} onRetry={refresh} />

      {healedBanner && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-heal/30 bg-heal/[0.06] px-4 py-3">
          <Check className="h-4 w-4 text-heal" />
          <p className="text-xs text-heal">
            Collector repaired
            {healedBanner.source_name ? ` — ${healedBanner.source_name}` : ""} · v
            {healedBanner.old_version ?? "?"} → v{healedBanner.new_version ?? "?"} · score{" "}
            {pct(healedBanner.score) ?? "?"}% · {healedBanner.articles_recovered ?? 0} articles
            recovered
          </p>
          <button
            type="button"
            onClick={() => setHealedBanner(null)}
            className="ml-auto cursor-pointer text-xs text-heal/70 hover:text-heal"
          >
            Dismiss
          </button>
        </div>
      )}
      {failureFlash && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-bear/30 bg-bear/[0.06] px-4 py-3">
          <AlertTriangle className="h-4 w-4 text-bear" />
          <p className="text-xs text-bear">
            Collector failure — {failureFlash.slug ?? failureFlash.source_id}
            {failureFlash.error_type ? ` (${failureFlash.error_type})` : ""}
            {failureFlash.error ? `: ${failureFlash.error}` : ""}
          </p>
          <button
            type="button"
            onClick={() => setFailureFlash(null)}
            className="ml-auto cursor-pointer text-xs text-bear/70 hover:text-bear"
          >
            Dismiss
          </button>
        </div>
      )}

      {loading && !data ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-56 lg:col-span-2" />
          <Skeleton className="h-56" />
        </div>
      ) : (
        <>
          <Panel className="mb-6 overflow-hidden">
            <div className="grid grid-cols-2 divide-x divide-edge/70 sm:grid-cols-4">
              <div className="p-5">
                <Metric label="Online" value={healthy} hint={`${scrapers.length} collectors`} accent="text-bull" />
              </div>
              <div className="p-5">
                <Metric
                  label="Needs attention"
                  value={needsAttention}
                  hint={needsAttention ? "Degraded or healing" : "All clear"}
                  accent={needsAttention ? "text-amber" : "text-ink"}
                />
              </div>
              <div className="p-5">
                <Metric
                  label="Success 24h"
                  value={avgSuccess != null ? `${avgSuccess}%` : "—"}
                  hint="Fleet average"
                  accent="text-ink"
                />
              </div>
              <div className="p-5">
                <Metric
                  label="Repairs"
                  value={healingAttempts}
                  hint="Healing events"
                  accent="text-heal"
                />
              </div>
            </div>
          </Panel>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
            <div className="xl:col-span-8">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <SectionLabel index="01">The fleet</SectionLabel>
                <div className="flex items-center gap-1 rounded-lg border border-edge bg-surface-2/40 p-1">
                  {(["ALL", "HEALTHY", "DEGRADED", "HEALING"] as Filter[]).map((value) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setFilter(value)}
                      className={cn(
                        "cursor-pointer rounded-md px-2.5 py-1 font-mono text-[9px] font-semibold uppercase tracking-[0.12em] transition-colors",
                        filter === value
                          ? "bg-surface-3 text-ink"
                          : "text-ink-faint hover:text-ink-dim",
                      )}
                    >
                      {value === "ALL" ? "All" : value.toLowerCase()}
                    </button>
                  ))}
                </div>
              </div>

              {filtered.length === 0 ? (
                <EmptyState
                  icon={<Server className="h-4 w-4" />}
                  title="No collectors in this view."
                  hint="Switch the filter or register a source in the backend."
                />
              ) : (
                <div className="stagger grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {filtered.map((scraper) => (
                    <SourceCard
                      key={String(scraper.source_id)}
                      scraper={scraper}
                      selected={String(scraper.source_id) === selectedSourceId}
                      onSelect={() => setSelectedSourceId(String(scraper.source_id))}
                      onOpenArticles={() => void openArticles(scraper)}
                      onActionDone={refresh}
                    />
                  ))}
                </div>
              )}
            </div>

            <aside className="xl:col-span-4">
              <div>
                <SectionLabel index="02">Healing timeline</SectionLabel>
                <Panel className="overflow-hidden">
                  <PanelHeader
                    eyebrow={selectedSource ? selectedSource.slug : "select a collector"}
                    title="Repair history"
                    action={
                      <select
                        value={selectedSourceId ?? ""}
                        onChange={(event) => setSelectedSourceId(event.target.value)}
                        aria-label="Select collector"
                        className="max-w-[150px] cursor-pointer rounded-md border border-edge bg-surface-2 px-2 py-1 font-mono text-[10px] text-ink-dim outline-none focus:border-amber/60"
                      >
                        {scrapers.map((scraper) => (
                          <option key={String(scraper.source_id)} value={String(scraper.source_id)}>
                            {scraper.name}
                          </option>
                        ))}
                      </select>
                    }
                  />

                  {historyLoading ? (
                    <div className="flex items-center gap-2 px-5 py-10 text-xs text-ink-faint">
                      <Spinner /> Loading repairs…
                    </div>
                  ) : historyError ? (
                    <p className="px-5 py-8 text-xs text-bear">{historyError}</p>
                  ) : history.length === 0 ? (
                    <div className="p-5">
                      <EmptyState
                        icon={<Zap className="h-4 w-4" />}
                        title="No repairs yet."
                        hint="This collector has not needed a new strategy. Run it or wait for the next schedule."
                      />
                    </div>
                  ) : (
                    <>
                      {history.length > 1 && (
                        <div className="border-b border-edge/70 px-5 py-3">
                          <select
                            value={selectedEventIdx}
                            onChange={(event) => setSelectedEventIdx(Number(event.target.value))}
                            aria-label="Select healing event"
                            className="w-full cursor-pointer rounded-md border border-edge bg-surface-2 px-2 py-1.5 font-mono text-[10px] text-ink-dim outline-none focus:border-amber/60"
                          >
                            {history.map((item, index) => (
                              <option key={String(item.id)} value={index}>
                                {formatTimestamp(item.created_at)} · {item.failure_type ?? item.status ?? "healing"}
                              </option>
                            ))}
                          </select>
                        </div>
                      )}
                      {selectedEvent ? (
                        <HealingDetail event={selectedEvent} />
                      ) : null}
                    </>
                  )}
                </Panel>

                <div className="mt-5">
                  <Panel className="overflow-hidden">
                    <PanelHeader eyebrow="Protocol" title="How a repair works" />
                    <ol className="divide-y divide-edge/60">
                      {[
                        ["01", "Detect", "Health metrics flag an empty result, a structure change, or a coverage collapse."],
                        ["02", "Generate", "The healing agent reads the stored HTML and proposes a declarative strategy — data, never code."],
                        ["03", "Validate", "The candidate runs against the real snapshot and is scored on coverage, volume, and duplicates."],
                        ["04", "Activate", "A passing candidate becomes vN+1; the next scheduled run proves recovery."],
                      ].map(([index, title, copy]) => (
                        <li key={index} className="flex gap-3 px-5 py-3.5">
                          <span className="num text-[10px] text-amber/70">{index}</span>
                          <div>
                            <p className="text-xs font-medium text-ink">{title}</p>
                            <p className="mt-1 text-[11px] leading-4 text-ink-faint">{copy}</p>
                          </div>
                        </li>
                      ))}
                    </ol>
                  </Panel>
                </div>
              </div>
            </aside>
          </div>
        </>
      )}

      <ArticleDrawer
        scraper={articlesFor}
        articles={articles}
        error={articlesError}
        onClose={() => {
          setArticlesFor(null);
          setArticles(null);
          setArticlesError(null);
        }}
      />
    </div>
  );
}

/* ---------------------------------------------------------------- source card */

function SourceCard({
  scraper,
  selected,
  onSelect,
  onOpenArticles,
  onActionDone,
}: {
  scraper: ScraperHealth;
  selected: boolean;
  onSelect: () => void;
  onOpenArticles: () => void;
  onActionDone: () => void;
}) {
  const [busy, setBusy] = useState<"run" | "heal" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const rate = pct(scraper.success_rate_24h);
  const rateTone = rate == null ? "ink" : rate >= 80 ? "bull" : rate >= 50 ? "amber" : "bear";

  const runNow = async (event: React.MouseEvent) => {
    event.stopPropagation();
    setBusy("run");
    setMessage(null);
    setFailed(false);
    try {
      const out = await runScraper(scraper.source_id);
      setMessage(out.triggered ? "Run queued — results land in the history." : "Run was not queued.");
      setFailed(!out.triggered);
      onActionDone();
      window.setTimeout(onActionDone, 5_000);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Run failed");
      setFailed(true);
    } finally {
      setBusy(null);
    }
  };

  const heal = async (event: React.MouseEvent) => {
    event.stopPropagation();
    setBusy("heal");
    setMessage(null);
    setFailed(false);
    try {
      const out = await healScraper(scraper.source_id);
      setMessage(
        out.triggered
          ? "Healing started — the timeline updates when the worker finishes."
          : "Healing did not start.",
      );
      setFailed(!out.triggered);
      onActionDone();
      window.setTimeout(onActionDone, 8_000);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Heal failed");
      setFailed(true);
    } finally {
      setBusy(null);
    }
  };

  return (
    <article
      className={cn(
        "panel panel-hover group cursor-pointer p-5",
        selected && "border-amber/35 shadow-glow-amber",
      )}
      onClick={onSelect}
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-edge bg-surface-2">
            <StatusDot status={scraper.health_status} label={false} size="lg" />
          </span>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-medium text-ink">{scraper.name}</h3>
            <p className="mt-0.5 truncate font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
              {scraper.slug} · v{scraper.strategy_version ?? "?"}
            </p>
          </div>
        </div>
        <Pill
          tone={
            scraper.health_status === "HEALTHY"
              ? "bull"
              : scraper.health_status === "HEALING"
                ? "heal"
                : "amber"
          }
        >
          {scraper.health_status ?? "unknown"}
        </Pill>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Stat label="Articles" value={scraper.last_articles_found ?? "—"} />
        <Stat label="Last run" value={relativeTime(scraper.last_run_at)} />
        <Stat label="Success 24h" value={rate != null ? `${rate}%` : "—"} tone={rateTone === "bull" ? "text-bull" : rateTone === "amber" ? "text-amber" : rateTone === "bear" ? "text-bear" : "text-ink-dim"} />
        <Stat label="Repairs" value={scraper.healing_attempts_total ?? 0} tone="text-heal" />
      </div>

      <div className="mt-4">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="label">Run health</span>
          <span className="num text-[10px] text-ink-faint">{rate ?? 0}%</span>
        </div>
        <StatBar
          value={rate ?? 0}
          tone={rateTone}
          height={3}
        />
      </div>

      {scraper.last_error_type && (
        <p className="mt-3 flex items-center gap-1.5 truncate rounded-md border border-bear/20 bg-bear/[0.06] px-2 py-1.5 font-mono text-[10px] text-bear">
          <AlertTriangle className="h-3 w-3 shrink-0" />
          {scraper.last_error_type}
        </p>
      )}

      {message && (
        <p className={cn("mt-3 text-[11px] leading-4", failed ? "text-bear" : "text-heal")}>
          {message}
        </p>
      )}

      <div className="mt-4 flex items-center gap-1.5 border-t border-edge/70 pt-4">
        <Button size="sm" variant="secondary" onClick={runNow} disabled={busy !== null}>
          {busy === "run" ? <Spinner className="h-3 w-3" /> : <Refresh className="h-3 w-3" />}
          Run
        </Button>
        <Button size="sm" variant="secondary" onClick={heal} disabled={busy !== null}>
          {busy === "heal" ? <Spinner className="h-3 w-3" /> : <Zap className="h-3 w-3" />}
          Heal
        </Button>
        <IconButton
          label={`View recent articles from ${scraper.name}`}
          onClick={(event) => {
            event.stopPropagation();
            onOpenArticles();
          }}
          className="ml-auto h-8 w-8"
        >
          <ArrowUpRight className="h-3.5 w-3.5" />
        </IconButton>
      </div>
    </article>
  );
}

function Stat({ label, value, tone = "text-ink-dim" }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div>
      <p className="label mb-1">{label}</p>
      <p className={cn("num text-xs", tone)}>{value}</p>
    </div>
  );
}

/* ---------------------------------------------------------------- healing detail */

function HealingDetail({ event }: { event: HealingEvent }) {
  const steps = event.timeline ?? [];
  const success = (event.status || "").toUpperCase() === "SUCCESS";
  return (
    <div>
      <div className="flex items-center justify-between border-b border-edge/70 px-5 py-4">
        <div className="flex items-center gap-2 font-mono text-xs">
          <span className="text-ink-faint">v{event.old_strategy_version ?? "?"}</span>
          <span className="text-ink-faint">→</span>
          <span className={success ? "font-semibold text-heal" : "font-semibold text-bear"}>
            v{event.new_strategy_version ?? "?"}
          </span>
        </div>
        <Pill tone={success ? "bull" : (event.status || "").toUpperCase() === "REJECTED" ? "bear" : "neutral"}>
          {event.status ?? "unknown"}
        </Pill>
      </div>
      <div className="grid grid-cols-3 divide-x divide-edge/70 border-b border-edge/70">
        <div className="px-4 py-3">
          <p className="label mb-1">Score</p>
          <p className={cn("num text-sm font-semibold", success ? "text-bull" : "text-bear")}>
            {pct(event.validation_score) ?? "—"}%
          </p>
        </div>
        <div className="px-4 py-3">
          <p className="label mb-1">Candidates</p>
          <p className="num text-sm text-ink-dim">{event.candidate_count ?? 0}</p>
        </div>
        <div className="px-4 py-3">
          <p className="label mb-1">Recovered</p>
          <p className="num text-sm text-ink-dim">{event.articles_recovered ?? "—"}</p>
        </div>
      </div>
      {event.failure_reason && (
        <p className="border-b border-edge/70 px-5 py-3 font-mono text-[10px] leading-4 text-bear">
          {event.failure_type ? `${event.failure_type}: ` : ""}
          {event.failure_reason}
        </p>
      )}
      <ol className="max-h-[420px] overflow-y-auto p-5">
        {steps.length === 0 ? (
          <p className="text-xs text-ink-faint">No timeline steps recorded.</p>
        ) : (
          steps.map((step, index) => (
            <TimelineStep key={`${step.at}-${index}`} step={step} last={index === steps.length - 1} />
          ))
        )}
      </ol>
    </div>
  );
}

function TimelineStep({ step, last }: { step: HealingTimelineStep; last: boolean }) {
  const stage = (step.stage || "").toLowerCase();
  const tone = stage.includes("error") || stage.includes("reject")
    ? "text-bear border-bear/40"
    : stage.includes("recovered") || stage.includes("activated") || stage.includes("success")
      ? "text-heal border-heal/40"
      : stage.includes("validated") || stage.includes("generated")
        ? "text-amber border-amber/40"
        : "text-ink-dim border-edge-bright";
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      {!last && <span className="absolute left-[5px] top-3 h-full w-px bg-edge" aria-hidden="true" />}
      <span className={cn("relative mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full border bg-base", tone)} />
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className={cn("font-mono text-[9px] font-semibold uppercase tracking-[0.12em]", tone.split(" ")[0])}>
            {(step.stage || "").replace(/_/g, " ").replace("healing ", "")}
          </span>
          <span className="font-mono text-[9px] text-ink-faint">{formatTimestamp(step.at)}</span>
        </div>
        {step.detail && <p className="mt-1 text-[11px] leading-4 text-ink-dim">{step.detail}</p>}
      </div>
    </li>
  );
}

/* ---------------------------------------------------------------- article drawer */

function ArticleDrawer({
  scraper,
  articles,
  error,
  onClose,
}: {
  scraper: ScraperHealth | null;
  articles: ScraperArticle[] | null;
  error: string | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!scraper) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [scraper, onClose]);

  if (!scraper) return null;

  const visibleArticles = (articles ?? []).filter((article) => {
    const title = (article.title ?? "").trim();
    return title.length > 0 && title.toLowerCase() !== "archive" && !/^\d{4}$/.test(title);
  });

  return createPortal(
    <div className="fixed inset-0 z-[70] flex justify-end" role="presentation">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Recent articles from ${scraper.name}`}
        className="relative flex h-full w-full max-w-lg flex-col border-l border-edge bg-surface shadow-2xl animate-rise"
      >
        <div className="flex items-start justify-between gap-4 border-b border-edge px-5 py-4">
          <div className="min-w-0">
            <p className="label mb-1">Collector</p>
            <h2 className="truncate text-sm font-medium text-ink">{scraper.name}</h2>
            <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
              {scraper.slug} · {scraper.last_articles_found ?? 0} found last run
            </p>
          </div>
          <IconButton label="Close articles" onClick={onClose}>
            <X className="h-4 w-4" />
          </IconButton>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          {error ? (
            <p className="px-3 py-8 text-xs text-bear">{error}</p>
          ) : articles === null ? (
            <div className="flex items-center gap-2 px-3 py-10 text-xs text-ink-faint">
              <Spinner /> Loading articles…
            </div>
          ) : visibleArticles.length === 0 ? (
            <EmptyState title="No articles recorded yet." hint="Run the collector to populate this list." />
          ) : (
            <ul className="divide-y divide-edge/60">
              {visibleArticles.map((article) => (
                <li key={String(article.id)}>
                  <a
                    href={article.url ?? "#"}
                    target="_blank"
                    rel="noreferrer"
                    className="group block rounded-lg px-3 py-3 transition-colors hover:bg-white/[0.03]"
                  >
                    <div className="flex items-start gap-3">
                      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-edge bg-surface-2 text-ink-faint">
                        <External className="h-3 w-3" />
                      </span>
                      <div className="min-w-0">
                        <p className="text-xs leading-5 text-ink-dim transition-colors group-hover:text-ink">
                          {article.title}
                        </p>
                        <p className="mt-1 flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                          <Clock className="h-2.5 w-2.5" />
                          {formatTimestamp(article.published_at ?? article.scraped_at)}
                        </p>
                      </div>
                    </div>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="border-t border-edge px-5 py-3 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
          {visibleArticles.length} recent articles
        </div>
      </aside>
    </div>,
    document.body,
  );
}
