import { useEffect, useMemo, useState } from "react";
import {
  getHealingHistory,
  getScraperHealth,
  healScraper,
  runScraper,
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
import {
  ApiErrorBanner,
  Card,
  EmptyState,
  SectionLabel,
  Spinner,
} from "../components/ui";
import { StatusDot } from "../components/StatusDot";
import { formatTimestamp, pct, relativeTime } from "../lib/format";

const POLL_MS = 30_000;

/* ---------------- Scraper card ---------------- */

interface CardActionState {
  busy: "run" | "heal" | null;
  message: string | null;
  error: boolean;
}

function ScraperCard({
  scraper,
  onActionDone,
}: {
  scraper: ScraperHealth;
  onActionDone: () => void;
}) {
  const [action, setAction] = useState<CardActionState>({
    busy: null,
    message: null,
    error: false,
  });

  const runNow = async () => {
    setAction({ busy: "run", message: null, error: false });
    try {
      const out = await runScraper(scraper.source_id);
      setAction({
        busy: null,
        message:
          out.status === "ok" || !out.error
            ? `Run complete — ${out.new_articles ?? "?"} new / ${out.articles_found ?? "?"} found`
            : `Run failed — ${out.error}`,
        error: Boolean(out.error) || out.status === "error",
      });
      onActionDone();
    } catch (err) {
      setAction({
        busy: null,
        message: err instanceof Error ? err.message : "Run failed",
        error: true,
      });
    }
  };

  const heal = async () => {
    setAction({ busy: "heal", message: null, error: false });
    try {
      const out = await healScraper(scraper.source_id);
      setAction({
        busy: null,
        message: out.triggered
          ? `Healing ${out.status ?? "done"} — score ${
              pct(out.validation_score) ?? "?"
            }%, v${out.new_version ?? "?"}`
          : (out.error as string) || "Healing did not trigger",
        error: !out.triggered,
      });
      onActionDone();
    } catch (err) {
      setAction({
        busy: null,
        message: err instanceof Error ? err.message : "Heal failed",
        error: true,
      });
    }
  };

  const rate = pct(scraper.success_rate_24h);
  const rateColor =
    rate == null
      ? "text-ink-faint"
      : rate >= 80
        ? "text-bull"
        : rate >= 50
          ? "text-amber"
          : "text-bear";

  return (
    <div className="flex flex-col rounded-md border border-edge bg-surface p-4 animate-fade-in">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink">{scraper.name}</p>
          <p className="truncate font-mono text-[11px] text-ink-faint">
            {scraper.slug}
          </p>
        </div>
        <StatusDot status={scraper.health_status} />
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <Stat label="Version">
          <span className="font-mono text-amber">
            v{scraper.strategy_version ?? "?"}
          </span>
        </Stat>
        <Stat label="Last run">
          <span className="font-mono text-ink-dim">
            {relativeTime(scraper.last_run_at)}
          </span>
        </Stat>
        <Stat label="Articles found">
          <span className="font-mono text-ink-dim">
            {scraper.last_articles_found ?? "—"}
          </span>
        </Stat>
        <Stat label="Success 24h">
          <span className={`font-mono ${rateColor}`}>
            {rate != null ? `${rate}%` : "—"}
          </span>
        </Stat>
        <Stat label="Healing attempts">
          <span className="font-mono text-heal">
            {scraper.healing_attempts_total ?? 0}
          </span>
        </Stat>
        <Stat label="Last failure">
          <span className="font-mono text-ink-dim">
            {relativeTime(scraper.last_failure_at)}
          </span>
        </Stat>
      </dl>

      {scraper.last_error_type && (
        <p className="mt-2 truncate rounded border border-bear/30 bg-bear/10 px-2 py-1 font-mono text-[11px] text-bear">
          last error: {scraper.last_error_type}
        </p>
      )}

      {/* Debug actions */}
      <div className="mt-auto flex items-center gap-2 pt-4">
        <button
          onClick={runNow}
          disabled={action.busy !== null}
          className="inline-flex items-center gap-1.5 rounded border border-edge px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-wider text-ink-dim transition-colors hover:border-amber/60 hover:text-amber disabled:opacity-50"
        >
          {action.busy === "run" && <Spinner className="h-3 w-3" />}
          Run now
        </button>
        <button
          onClick={heal}
          disabled={action.busy !== null}
          className="inline-flex items-center gap-1.5 rounded border border-edge px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-wider text-ink-dim transition-colors hover:border-heal/60 hover:text-heal disabled:opacity-50"
        >
          {action.busy === "heal" && <Spinner className="h-3 w-3" />}
          Heal
        </button>
      </div>

      {action.message && (
        <p
          className={`mt-2 rounded px-2 py-1 font-mono text-[11px] ${
            action.error
              ? "border border-bear/40 bg-bear/10 text-bear"
              : "border border-bull/40 bg-bull/10 text-bull"
          }`}
        >
          {action.message}
        </p>
      )}
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="label-caps mb-0.5">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/* ---------------- Healing timeline ---------------- */

const STAGE_ICONS: Record<string, string> = {
  started: "▶",
  generating: "…",
  candidate_generated: "+",
  validated: "✓",
  activated: "★",
  recovered: "↺",
  rejected: "×",
};

function stageStyle(stage: string): string {
  const s = stage.toLowerCase();
  if (s.includes("reject") || s.includes("fail"))
    return "border-bear bg-bear/10 text-bear";
  if (s.includes("validat") || s.includes("activat") || s.includes("recover") ||
      s.includes("complete"))
    return "border-bull bg-bull/10 text-bull";
  return "border-amber/60 bg-amber/10 text-amber";
}

function HealingTimeline({ event }: { event: HealingEvent }) {
  const steps = event.timeline ?? [];
  return (
    <Card className="animate-fade-in">
      {/* Header: versions + scores */}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4 rounded border border-edge bg-base/60 px-4 py-3">
        <div className="flex items-center gap-3 font-mono text-sm">
          <span className="text-ink-faint">v{event.old_strategy_version ?? "?"}</span>
          <svg
            className="h-3 w-3 text-ink-faint"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
          <span className="font-semibold text-heal">
            v{event.new_strategy_version ?? "?"}
          </span>
        </div>
        <div className="flex items-center gap-5 font-mono text-xs">
          <span className="text-ink-dim">
            Validation score:{" "}
            <span
              className={`text-base font-bold ${
                (pct(event.validation_score) ?? 0) >= 70 ? "text-bull" : "text-bear"
              }`}
            >
              {pct(event.validation_score) ?? "—"}%
            </span>
          </span>
          {event.candidate_count != null && (
            <span className="text-ink-dim">
              Candidates: <span className="text-ink">{event.candidate_count}</span>
            </span>
          )}
          {event.articles_recovered != null && (
            <span className="text-ink-dim">
              Recovered: <span className="text-ink">{event.articles_recovered}</span>
            </span>
          )}
          {event.status && (
            <span
              className={`rounded border px-1.5 py-0.5 uppercase tracking-widest ${
                event.status === "success"
                  ? "border-bull/50 text-bull"
                  : "border-bear/50 text-bear"
              }`}
            >
              {event.status}
            </span>
          )}
        </div>
      </div>

      {(event.failure_reason || event.failure_type) && (
        <p className="mb-5 rounded border border-bear/30 bg-bear/10 px-3 py-2 font-mono text-xs text-bear">
          {event.failure_type}: {event.failure_reason}
        </p>
      )}

      {/* Vertical timeline */}
      <ol className="relative ml-2 space-y-0 border-l border-edge pl-6">
        {steps.map((step, i) => (
          <TimelineStep key={i} step={step} last={i === steps.length - 1} index={i} />
        ))}
        {steps.length === 0 && (
          <li className="py-2 font-mono text-xs text-ink-faint">
            No timeline steps recorded.
          </li>
        )}
      </ol>
    </Card>
  );
}

function TimelineStep({
  step,
  last,
  index,
}: {
  step: HealingTimelineStep;
  last: boolean;
  index: number;
}) {
  const style = stageStyle(step.stage);
  const icon = STAGE_ICONS[step.stage.toLowerCase()] ?? "·";
  return (
    <li
      className={`relative pb-5 animate-fade-in-up ${last ? "pb-1" : ""}`}
      style={{ animationDelay: `${Math.min(index * 90, 600)}ms` }}
    >
      {!last && <span className="absolute -left-6 top-8 h-full w-px bg-edge" />}
      <span
        className={`absolute -left-[31px] flex h-5 w-5 items-center justify-center rounded-full border font-mono text-[10px] ${style}`}
      >
        {icon}
      </span>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className={`font-mono text-xs font-bold uppercase tracking-widest ${style.split(" ").pop()}`}>
          {step.stage.replace(/_/g, " ")}
        </span>
        <span className="font-mono text-[10px] text-ink-faint">
          {formatTimestamp(step.at)}
        </span>
      </div>
      {step.detail && (
        <p className="mt-1 text-sm leading-relaxed text-ink-dim">{step.detail}</p>
      )}
    </li>
  );
}

/* ---------------- Page ---------------- */

export default function Scrapers() {
  const fetcher = () => getScraperHealth();
  const { data, error, loading, refresh } = usePolling(fetcher, POLL_MS);

  // Live SSE state
  const [healedBanner, setHealedBanner] = useState<ScraperHealedPayload | null>(
    null,
  );
  const [failureFlash, setFailureFlash] = useState<ScraperFailurePayload | null>(
    null,
  );

  useEventStream({
    onHealed: (p) => {
      setHealedBanner(p);
      refresh();
    },
    onScraperFailure: (p) => {
      setFailureFlash(p);
      refresh();
    },
  });

  useEffect(() => {
    if (!healedBanner) return;
    const t = setTimeout(() => setHealedBanner(null), 15_000);
    return () => clearTimeout(t);
  }, [healedBanner]);

  useEffect(() => {
    if (!failureFlash) return;
    const t = setTimeout(() => setFailureFlash(null), 10_000);
    return () => clearTimeout(t);
  }, [failureFlash]);

  // Healing history selection
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [history, setHistory] = useState<HealingEvent[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [selectedEventIdx, setSelectedEventIdx] = useState(0);

  const scrapers = data ?? [];

  // Auto-select first scraper once loaded; keep user's explicit choice otherwise.
  useEffect(() => {
    if (!selectedSourceId && scrapers.length > 0) {
      // Prefer a scraper with healing activity, else the first.
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
        const sorted = [...events].sort(
          (a, b) =>
            new Date(b.created_at ?? 0).getTime() -
            new Date(a.created_at ?? 0).getTime(),
        );
        setHistory(sorted);
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

  const selectedEvent = useMemo(
    () => history[selectedEventIdx] ?? null,
    [history, selectedEventIdx],
  );

  return (
    <div className="mx-auto max-w-[1600px] px-5 py-6">
      <div className="mb-6">
        <h1 className="font-mono text-xl font-bold tracking-[0.2em] text-ink">
          SCRAPER HEALTH
        </h1>
        <p className="mt-1 text-xs text-ink-faint">
          {scrapers.length} sources · self-healing pipeline status · polling every{" "}
          {POLL_MS / 1000}s
        </p>
      </div>

      {/* SSE banners */}
      {healedBanner && (
        <div className="mb-4 flex items-center gap-3 rounded-md border border-heal/50 bg-heal/10 px-4 py-3 animate-fade-in">
          <StatusDot status="HEALING" label={false} />
          <p className="font-mono text-sm font-semibold text-heal">
            SCRAPER HEALED
            {healedBanner.source_name ? ` — ${healedBanner.source_name}` : ""} · v
            {healedBanner.old_version ?? "?"} → v{healedBanner.new_version ?? "?"} ·
            score {pct(healedBanner.score) ?? "?"}% ·{" "}
            {healedBanner.articles_recovered ?? 0} articles recovered
          </p>
          <button
            onClick={() => setHealedBanner(null)}
            className="ml-auto font-mono text-xs text-heal/70 hover:text-heal"
          >
            dismiss ×
          </button>
        </div>
      )}
      {failureFlash && (
        <div className="mb-4 flex items-center gap-3 rounded-md border border-bear/50 bg-bear/10 px-4 py-3 animate-fade-in">
          <StatusDot status="FAILED" label={false} />
          <p className="font-mono text-sm text-bear">
            SCRAPER FAILURE — {failureFlash.slug ?? failureFlash.source_id}
            {failureFlash.error_type ? ` (${failureFlash.error_type})` : ""}
            {failureFlash.error ? `: ${failureFlash.error}` : ""}
          </p>
          <button
            onClick={() => setFailureFlash(null)}
            className="ml-auto font-mono text-xs text-bear/70 hover:text-bear"
          >
            dismiss ×
          </button>
        </div>
      )}

      <ApiErrorBanner error={error} onRetry={refresh} />

      {/* Source grid */}
      {loading && !data ? (
        <div className="flex items-center gap-2 py-16 text-sm text-ink-faint">
          <Spinner /> Loading scraper fleet…
        </div>
      ) : scrapers.length === 0 ? (
        <EmptyState
          title="No scrapers registered."
          hint="Register sources in the backend to see them here."
        />
      ) : (
        <>
          <SectionLabel>Fleet Status</SectionLabel>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {scrapers.map((s) => (
              <ScraperCard key={String(s.source_id)} scraper={s} onActionDone={refresh} />
            ))}
          </div>

          {/* Healing timeline */}
          <section className="mt-10">
            <SectionLabel>Healing Timeline</SectionLabel>

            <div className="mb-4 flex flex-wrap items-center gap-3">
              <select
                value={selectedSourceId ?? ""}
                onChange={(e) => setSelectedSourceId(e.target.value)}
                className="rounded border border-edge bg-surface px-3 py-1.5 font-mono text-xs text-ink outline-none focus:border-amber/60"
              >
                {scrapers.map((s) => (
                  <option key={String(s.source_id)} value={String(s.source_id)}>
                    {s.name}
                  </option>
                ))}
              </select>
              {history.length > 1 && (
                <select
                  value={selectedEventIdx}
                  onChange={(e) => setSelectedEventIdx(Number(e.target.value))}
                  className="rounded border border-edge bg-surface px-3 py-1.5 font-mono text-xs text-ink outline-none focus:border-amber/60"
                >
                  {history.map((h, i) => (
                    <option key={String(h.id)} value={i}>
                      {formatTimestamp(h.created_at)} ·{" "}
                      {h.failure_type ?? h.status ?? "healing"} · v
                      {h.old_strategy_version ?? "?"}→v
                      {h.new_strategy_version ?? "?"}
                    </option>
                  ))}
                </select>
              )}
              <span className="font-mono text-xs text-ink-faint">
                {history.length} healing event{history.length === 1 ? "" : "s"}
              </span>
            </div>

            {historyLoading ? (
              <div className="flex items-center gap-2 py-10 text-sm text-ink-faint">
                <Spinner /> Loading healing history…
              </div>
            ) : historyError ? (
              <ApiErrorBanner error={new Error(historyError)} onRetry={refresh} />
            ) : selectedEvent ? (
              <HealingTimeline event={selectedEvent} />
            ) : (
              <EmptyState
                title="No healing events for this source."
                hint="When the healing agent rewrites a failed strategy, its full timeline appears here."
              />
            )}
          </section>
        </>
      )}
    </div>
  );
}
