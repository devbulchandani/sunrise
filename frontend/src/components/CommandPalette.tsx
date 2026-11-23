import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getEvents, getSources } from "../services/api";
import type { MarketEvent, Source } from "../types";
import { cn } from "../lib/cn";
import { ArrowUpRight, Command, Radar, Search, Server } from "./icons";
import { Kbd, Spinner } from "./ui";

type Result = {
  id: string;
  kind: "event" | "source";
  label: string;
  meta: string;
};

export function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [events, setEvents] = useState<MarketEvent[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    setError(null);
    setLoading(true);
    const timer = window.setTimeout(() => inputRef.current?.focus(), 30);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    Promise.all([getEvents({ limit: 80 }), getSources()])
      .then(([nextEvents, nextSources]) => {
        setEvents(nextEvents);
        setSources(nextSources);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
    return () => {
      window.clearTimeout(timer);
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  const results = useMemo<Result[]>(() => {
    const q = query.trim().toLowerCase();
    const eventMatches = events
      .filter(
        (event) =>
          !q ||
          event.headline?.toLowerCase().includes(q) ||
          (event.category ?? "").toLowerCase().includes(q) ||
          (event.affected_markets ?? []).some((market) => market.toLowerCase().includes(q)),
      )
      .slice(0, 7)
      .map((event) => ({
        id: `event-${event.id}`,
        kind: "event" as const,
        label: event.headline,
        meta: `${Math.round(event.urgency ?? 0)} urgency · ${(event.category || "other").replace(/_/g, " ")}`,
      }));

    const sourceMatches = sources
      .filter(
        (source) =>
          !q ||
          source.name?.toLowerCase().includes(q) ||
          source.slug?.toLowerCase().includes(q),
      )
      .slice(0, 4)
      .map((source) => ({
        id: `source-${source.id}`,
        kind: "source" as const,
        label: source.name ?? source.slug,
        meta: `${source.slug} · ${source.health_status ?? "unknown"}`,
      }));

    return [...eventMatches, ...sourceMatches];
  }, [events, sources, query]);

  useEffect(() => {
    setActive((current) => Math.min(current, Math.max(results.length - 1, 0)));
  }, [results.length]);

  if (!open) return null;

  const go = (result: Result | undefined) => {
    if (!result) return;
    if (result.kind === "event") {
      navigate(`/events/${result.id.replace("event-", "")}`);
    } else {
      navigate("/scrapers");
    }
    onClose();
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((current) => Math.min(current + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(results[active]);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[90] flex justify-center bg-black/70 px-4 pt-[10vh] backdrop-blur-md"
      onClick={onClose}
      onKeyDown={onKeyDown}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command menu"
        className="h-fit w-full max-w-2xl overflow-hidden rounded-2xl border border-edge bg-surface shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-edge px-4 py-3.5">
          <Search className="h-4 w-4 shrink-0 text-ink-faint" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            placeholder="Search events, categories, collectors…"
            className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint"
            aria-label="Search events and collectors"
          />
          <Kbd>esc</Kbd>
        </div>

        <div className="max-h-[52vh] overflow-y-auto p-2">
          {loading ? (
            <div className="flex items-center gap-2 px-3 py-8 text-xs text-ink-faint">
              <Spinner /> Loading the wire…
            </div>
          ) : error ? (
            <p className="px-3 py-8 text-xs text-bear">{error}</p>
          ) : results.length === 0 ? (
            <div className="px-3 py-10 text-center">
              <Radar className="mx-auto mb-3 h-5 w-5 text-ink-faint" />
              <p className="text-sm text-ink-dim">No signal matches “{query}”.</p>
              <p className="mt-1 text-xs text-ink-faint">
                Try a company, a category, or a collector name.
              </p>
            </div>
          ) : (
            <ul role="listbox" aria-label="Search results">
              {results.map((result, index) => (
                <li key={result.id} role="option" aria-selected={index === active}>
                  {(index === 0 || results[index - 1].kind !== result.kind) && (
                    <p className="label px-3 pb-1.5 pt-2">
                      {result.kind === "event" ? "Signals" : "Collectors"}
                    </p>
                  )}
                  <button
                    type="button"
                    onMouseEnter={() => setActive(index)}
                    onClick={() => go(result)}
                    className={cn(
                      "group flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                      index === active ? "bg-surface-2" : "hover:bg-surface-2/60",
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
                        result.kind === "event"
                          ? "border-amber/25 bg-amber/10 text-amber"
                          : "border-heal/25 bg-heal/10 text-heal",
                      )}
                    >
                      {result.kind === "event" ? (
                        <Radar className="h-4 w-4" />
                      ) : (
                        <Server className="h-4 w-4" />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-ink">{result.label}</span>
                      <span className="mt-0.5 block truncate font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">
                        {result.meta}
                      </span>
                    </span>
                    <ArrowUpRight
                      className={cn(
                        "h-4 w-4 shrink-0 text-ink-faint transition-all",
                        index === active && "text-amber",
                      )}
                    />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-edge px-4 py-2.5">
          <div className="flex items-center gap-3 text-[10px] text-ink-faint">
            <span className="flex items-center gap-1.5">
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> navigate
            </span>
            <span className="flex items-center gap-1.5">
              <Kbd>↵</Kbd> open
            </span>
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">
            Sunrise command
          </span>
        </div>
      </div>
    </div>
  );
}
