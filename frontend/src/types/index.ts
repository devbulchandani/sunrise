// Shared API payload types for the Sunrise backend.

export type Sentiment = "BULLISH" | "BEARISH" | "NEUTRAL";

export type UrgencyTier = "CRITICAL" | "HIGH" | "MODERATE" | "RELEVANT";

export type HealthStatus = "HEALTHY" | "DEGRADED" | "FAILED" | "HEALING";

/** GET /api/events list item and GET /api/events/{id} shared fields */
export interface MarketEvent {
  id: number | string;
  headline: string;
  summary?: string | null;
  ai_summary?: string | null;
  category?: string | null;
  sentiment?: Sentiment | null;
  market_impact?: number | null;
  urgency?: number | null;
  confidence?: number | null;
  analysis_status?: string | null;
  first_detected_at?: string | null;
  last_updated_at?: string | null;
  article_count?: number | null;
  affected_markets?: string[] | null;
}

export interface IPIOResearch {
  company_name: string;
  ticker?: string;
  exchange?: string;
  sector?: string;
  company_overview: string;
  business_model?: string;
  key_financials?: string[];
  ipo_terms?: string[];
  strengths?: string[];
  risks?: string[];
  valuation_notes?: string;
  use_of_proceeds?: string;
  considerations?: string[];
  research_confidence?: number;
  sources_used?: string[];
  researched_at?: string;
}

export interface AffectedAsset {
  symbol: string;
  impact: number | string;
  confidence?: number | null;
}

export interface EventSourceRef {
  id: number | string;
  name?: string | null;
  url?: string | null;
  [key: string]: unknown;
}

export interface Article {
  id: number | string;
  title: string;
  url?: string | null;
  published_at?: string | null;
  scraped_at?: string | null;
  source_name?: string | null;
}

/** GET /api/events/{id} — detail payload */
export interface EventDetail extends MarketEvent {
  reason?: string | null;
  affected_markets?: string[] | null;
  ipo_research?: IPIOResearch | null;
  affected_assets?: AffectedAsset[] | null;
  sources?: EventSourceRef[] | null;
  articles?: Article[] | null;
}

export interface EventsResponse {
  events: MarketEvent[];
}

/** GET /api/sources */
export interface Source {
  id: number | string;
  slug: string;
  name: string;
  url: string;
  type?: string | null;
  schedule?: string | null;
  category?: string | null;
  credibility?: number | null;
  active?: boolean;
  health_status?: HealthStatus | string | null;
  current_strategy_version?: number | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
}

export interface SourcesResponse {
  sources: Source[];
}

/** GET /api/scrapers/health */
export interface ScraperHealth {
  source_id: number | string;
  slug: string;
  name: string;
  health_status: HealthStatus | string | null;
  strategy_version?: number | string | null;
  last_run_at?: string | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  last_error_type?: string | null;
  last_articles_found?: number | null;
  success_rate_24h?: number | null;
  healing_attempts_total?: number | null;
  active_healing_event_id?: number | string | null;
}

export interface ScraperHealthResponse {
  scrapers: ScraperHealth[];
}

/** GET /api/scrapers/{id}/runs */
export interface ScraperRun {
  id: number | string;
  started_at?: string | null;
  completed_at?: string | null;
  status?: string | null;
  http_status?: number | null;
  response_time_ms?: number | null;
  articles_found?: number | null;
  new_articles?: number | null;
  title_coverage?: number | null;
  url_coverage?: number | null;
  timestamp_coverage?: number | null;
  duplicate_ratio?: number | null;
  error_type?: string | null;
  error_message?: string | null;
}

export interface ScraperRunsResponse {
  runs: ScraperRun[];
}

/** GET /api/scrapers/{id}/healing-history */
export interface HealingTimelineStep {
  at?: string | null;
  stage: string;
  detail?: string | null;
}

export interface HealingEvent {
  id: number | string;
  source_id: number | string;
  old_strategy_version?: number | string | null;
  new_strategy_version?: number | string | null;
  failure_reason?: string | null;
  failure_type?: string | null;
  candidate_count?: number | null;
  candidate_scores?: unknown;
  validation_score?: number | null;
  status?: string | null;
  timeline?: HealingTimelineStep[] | null;
  articles_recovered?: number | null;
  error?: string | null;
  created_at?: string | null;
}

export interface HealingHistoryResponse {
  healing_events: HealingEvent[];
}

/** POST /api/scrapers/{id}/run */
export interface RunOutcome {
  status?: string;
  articles_found?: number | null;
  new_articles?: number | null;
  error?: string | null;
  run_id?: number | string | null;
  [key: string]: unknown;
}

/** POST /api/scrapers/{id}/heal */
export interface HealOutcome {
  triggered?: boolean;
  status?: string | null;
  validation_score?: number | null;
  new_version?: number | string | null;
  timeline?: HealingTimelineStep[] | null;
  error?: string | null;
  [key: string]: unknown;
}

/** GET /api/stats */
export interface SystemStats {
  jobs_processed?: number | null;
  jobs_pending?: number | null;
  jobs_failed?: number | null;
  articles_scraped?: number | null;
  events_detected?: number | null;
  alerts_sent?: number | null;
  scraper_failures?: number | null;
  scraper_healings?: number | null;
  llm_calls?: number | null;
}

/** GET /api/health */
export interface HealthCheck {
  status?: string;
  [key: string]: unknown;
}

/* ---- SSE stream payloads (GET /api/stream) ---- */

export type StreamEventType =
  | "new"
  | "alerts"
  | "scrapers"
  | "healed"
  | string;

export interface StreamEnvelope {
  event: StreamEventType;
  data: string; // raw JSON, parsed by the hook
}

/** "new" → new_event, "alerts" → critical_alert (same shape as a market event) */
export type NewEventPayload = MarketEvent;

/** "scrapers" → scraper_failure */
export interface ScraperFailurePayload {
  source_id: number | string;
  slug?: string;
  error?: string | null;
  error_type?: string | null;
  [key: string]: unknown;
}

/** "healed" → scraper_healed */
export interface ScraperHealedPayload {
  source: number | string;
  source_name?: string | null;
  old_version?: number | string | null;
  new_version?: number | string | null;
  score?: number | null;
  articles_recovered?: number | null;
  timeline?: HealingTimelineStep[] | null;
  [key: string]: unknown;
}
