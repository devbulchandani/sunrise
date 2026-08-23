import type {
  EventDetail,
  EventsResponse,
  MarketEvent,
  HealOutcome,
  HealingHistoryResponse,
  HealthCheck,
  RunOutcome,
  ScraperHealthResponse,
  ScraperRunsResponse,
  SourcesResponse,
  SystemStats,
} from "../types";

/**
 * All requests go through the Vite dev proxy ("/api" → http://localhost:8000)
 * so there are no CORS issues. Set VITE_API_BASE to override (e.g. when the
 * frontend is served from a different origin in production).
 */
const BASE = import.meta.env.VITE_API_BASE || "/api";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function adminHeaders(): Record<string, string> {
  const token = import.meta.env.VITE_ADMIN_TOKEN;
  return token ? { "X-Admin-Token": token } : {};
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...adminHeaders(),
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError("API unreachable", 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function getHealth(): Promise<HealthCheck> {
  return request<HealthCheck>("/health");
}

export interface EventFilters {
  min_urgency?: number;
  level?: string;
  category?: string;
  limit?: number;
}

export async function getEvents(
  filters: EventFilters = {},
): Promise<MarketEvent[]> {
  const qs = new URLSearchParams();
  if (filters.min_urgency != null) qs.set("min_urgency", String(filters.min_urgency));
  if (filters.level) qs.set("level", filters.level);
  if (filters.category) qs.set("category", filters.category);
  if (filters.limit != null) qs.set("limit", String(filters.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const data = await request<EventsResponse>(`/events${suffix}`);
  return data.events ?? [];
}

export function getEvent(id: string | number): Promise<EventDetail> {
  return request<EventDetail>(`/events/${id}`);
}

export function getSources(): Promise<SourcesResponse["sources"]> {
  return request<SourcesResponse>("/sources").then((d) => d.sources ?? []);
}

export function getScraperHealth(): Promise<
  ScraperHealthResponse["scrapers"]
> {
  return request<ScraperHealthResponse>("/scrapers/health").then(
    (d) => d.scrapers ?? [],
  );
}

export function getScraperRuns(
  id: string | number,
): Promise<ScraperRunsResponse["runs"]> {
  return request<ScraperRunsResponse>(`/scrapers/${id}/runs`).then(
    (d) => d.runs ?? [],
  );
}

export function getHealingHistory(
  id: string | number,
): Promise<HealingHistoryResponse["healing_events"]> {
  return request<HealingHistoryResponse>(`/scrapers/${id}/healing-history`).then(
    (d) => d.healing_events ?? [],
  );
}

export function runScraper(id: string | number): Promise<RunOutcome> {
  return request<RunOutcome>(`/scrapers/${id}/run`, { method: "POST" });
}

export function healScraper(id: string | number): Promise<HealOutcome> {
  return request<HealOutcome>(`/scrapers/${id}/heal`, { method: "POST" });
}

export function getStats(): Promise<SystemStats> {
  return request<SystemStats>("/stats");
}

export const SSE_STREAM_URL = `${BASE}/stream`;
