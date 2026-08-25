# Sunrise

**Wake up before the market does.**

Sunrise is an autonomous financial intelligence platform that continuously monitors publicly available financial news, extracts market-moving events with AI (urgency, sentiment, affected assets, sectors and broad markets), scores their urgency, and delivers filtered alerts to Telegram/email — all powered by a **self-healing scraping system** that detects when websites change under it, regenerates its extraction strategies with an LLM, validates the repair against real HTML, and resumes collection without human intervention.

```
PUBLIC WEB → SCRAPER → RAW ARTICLE → NORMALIZATION → DEDUPLICATION
                                                        ↓
                                            AI MARKET ANALYSIS → URGENCY SCORE
                                                        ↓
                                                  MARKET EVENT → REDIS PUB/SUB
                                                        ↓
                                          ┌───────────────┼───────────────┐
                                          ▼               ▼               ▼
                                      DASHBOARD       TELEGRAM         EMAIL
```

And when a scraper breaks:

```
SCRAPER → HEALTH CHECK → EXTRACTION FAILURE → FAILURE DIAGNOSIS
    → LLM HEALING AGENT → CANDIDATE STRATEGY (declarative JSON only)
    → VALIDATION PIPELINE → VERSIONED STRATEGY → RESUME COLLECTION
```

## What is self-healing?

Every source has a **versioned extraction strategy** stored in Postgres — pure data (CSS/XPath/JSON-LD/OpenGraph/semantic hints), never code:

```json
{
  "list_selector": {"method": "css", "selector": "ul.panel-body__list li"},
  "fields": {
    "title": {"method": "css", "selector": "a", "attribute": "text"},
    "url": {"method": "css", "selector": "a", "attribute": "href"},
    "published_at": {"method": "semantic"}
  }
}
```

1. **Detect** — every run records health metrics (article count, title/url/timestamp coverage, duplicate ratio, HTTP status). Anomaly detection flags `EMPTY_RESULT`, `STRUCTURE_CHANGE`, coverage collapse, or sudden volume drops.
2. **Classify** — network/rate-limit/server errors get exponential backoff retries. Only parsing/structure failures trigger healing.
3. **Capture** — the healing agent gets the old strategy, the last successful output shape, failure metrics, and the stored HTML snapshot of the current page.
4. **Generate** — the LLM produces a candidate strategy as structured JSON (validated by Pydantic; it can never execute code).
5. **Validate** — schema validation → static safety checks → dry-run extraction on the real snapshot → quality scoring (coverage + volume vs history − duplicates) → accept/reject. Rejected candidates are retried with feedback (max 3).
6. **Activate** — accepted candidates become strategy `vN+1`, the old version is deactivated, and the next scheduled run succeeds. Every attempt is recorded in `healing_events` with a full timeline rendered in the dashboard.

## Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI + Pydantic v2 |
| DB | PostgreSQL + SQLAlchemy 2 (async) |
| Queue/cache/pubsub | Redis + arq workers |
| Scheduler | APScheduler (per-source cron) |
| Scraping | httpx + selectolax/lxml + feedparser (no paid services) |
| LLM | OpenAI-compatible endpoints (OpenAI/OpenRouter/NVIDIA NIM) + Anthropic adapter |
| Frontend | React + Vite + TypeScript + Tailwind |
| Notifications | Telegram Bot API (multi-subscriber bot with per-user preferences) + SMTP email |

## Data sources

11 public sources seeded by default: Federal Reserve press releases (HTML), ECB press RSS, Bank of England RSS, Cointelegraph, CoinDesk, Yahoo Finance, Investing.com commodities, **TradingView Top Stories**, **Economic Times Markets (India)**, **LiveMint Markets (India)** — plus **MarketWatch via Bright Data** (see below). All public pages, robots.txt respected, rate-limited per host.

**TradingView** is fully client-rendered, but the article list ships server-side inside `<script type="application/prs.init-data+json">` tags — the `tradingview` source type walks those scripts and extracts the news items JSON directly (title, link, storyPath, published timestamp).

## Bright Data integration (Web Unlocker)

Sunrise's core collectors are owned infrastructure, but some financial sites run aggressive anti-bot protection that makes direct collection impractical — MarketWatch is a live example in this repo. For those targets Sunrise supports an auxiliary source type powered by **Bright Data's Web Unlocker** through the official `@brightdata/cli`:

```bash
npm i -g @brightdata/cli
bdata login                      # OAuth, once
# or: BRIGHTDATA_API_KEY=... in .env
```

Register a Bright Data-backed source (already seeded as `reuters_brightdata`):

```json
{"slug": "reuters_brightdata", "name": "MarketWatch via Bright Data",
 "url": "https://www.marketwatch.com/latest-news", "type": "brightdata", ...}
```

How it works:
1. On schedule, Sunrise invokes `bdata scrape https://www.marketwatch.com/latest-news --format markdown` (Web Unlocker handles proxies/retries/unblocking).
2. The returned markdown is parsed into headline entries by `brightdata_adapter.py`.
3. Those entries flow through the exact same pipeline as every other source: normalization → dedup → clustering → AI analysis → alerts.
4. Health metrics are tracked identically, so failures on this source are visible on the Scraper Health page too.

This keeps a clean separation: **owned self-healing collectors for the long tail, Bright Data for the walled gardens** — both feeding one intelligence pipeline.

## Quick start

### Prerequisites
- Python 3.12+, Node 20+, Docker

### 1. Infrastructure

```bash
docker compose up -d postgres redis
cp .env.example .env        # fill in your keys (see below)
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m app.seed          # create tables, register sources, demo user
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

### 3. Workers & scheduler (separate terminals)

```bash
cd backend
./.venv/bin/arq app.workers.settings.WorkerSettings   # queue worker
./.venv/bin/python -m app.scheduler.main              # cron scheduler
```

> Alternative: run everything through arq only (`worker` handles scraping/analysis/healing/notifications; scheduler enqueues jobs into Redis). Or run the whole stack in Docker: `docker compose up --build`.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
```

## Environment variables

See `.env.example`. Key ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres async DSN |
| `REDIS_URL` | Redis for queues/pubsub/cache |
| `LLM_PROVIDER` | `openai` (any compatible endpoint) or `anthropic` |
| `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` | LLM config; base URL enables OpenRouter/NIM gateways |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram alerts (optional; app works without) |
| `SMTP_*` / `EMAIL_FROM` | Email digests (optional) |
| `DEMO_MODE` | Enables demo break/heal commands |
| `ADMIN_TOKEN` | If set, required as `X-Admin-Token` on debug endpoints |

## Demo mode — watch Sunrise heal itself

Requires `DEMO_MODE=true`. The Fed source is the designated break target:

```bash
# 1. sabotage the active Fed strategy so extraction yields 0 articles
python -m app.demo.break_scraper fed

# 2. run the scraper twice (or wait for the schedule) -> FAILED, health DEGRADED,
#    then the healing agent triggers automatically; or force it:
python -m app.demo.trigger_healing fed
```

A real recorded run in this repo's history: strategy v1 (seed) failed → LLM generated an XPath candidate → validated at score 82 with 29 articles recovered → **strategy v2 activated** — visible on the Scraper Health dashboard timeline.

With `LLM_API_KEY` configured you'll see the full pipeline: candidate generation → validation score → `strategy v2 activated` → recovered article count. The Scraper Health page in the dashboard renders the same timeline live via SSE.

### Urgency model

Blended deterministic + AI score, normalized 0–100:

```
final = 0.55*AI_urgency + 0.15*source_credibility + 0.10*category_weight
      + 0.10*novelty + 0.10*breadth_of_assets   (+ small market_impact nudge)

0–20 LOW · 21–40 MODERATE · 41–60 RELEVANT · 61–80 HIGH · 81–100 CRITICAL
```

Telegram pushes at ≥61; user preferences can raise the floor or filter by asset/category.

## Agentic IPO research

Events categorized as `IPO` automatically trigger a multi-step research agent after standard analysis:

1. **Extract** — company name, ticker, exchange and IPO terms from the event's articles
2. **Research** — the agent issues `search()` (Bright Data SERP) and `fetch()` (Web Unlocker) tool calls, up to 3 rounds, to gather public information about the company
3. **Synthesize** — a structured due-diligence brief: company overview, business model, key financials, strengths, risks, valuation notes, use of proceeds, and "considerations"

The brief is stored on the event (`ipo_research`), rendered in the dashboard's **IPO Deep-Dive** section, and summarized in Telegram alerts. Every output is labeled AI interpretation with confidence and sources — the pipeline never recommends buying, and degrades honestly (marking claims `unverified`) when web tools are rate-limited.

## Deployment

| Component | Host | Notes |
|---|---|---|
| Dashboard | Cloudflare Pages | built with `VITE_API_BASE=<api-url>/api`, then `wrangler pages deploy dist` |
| Backend + worker + scheduler + Postgres + Redis | AWS EC2 `t4g.small` (free tier) | one instance via `docker-compose.aws.yml` |

Deploy the backend from scratch:

```bash
aws configure                                  # credentials with EC2 permissions
./deploy/aws-ec2.sh                            # keypair + SG + t4g.small + docker install (user-data)
scp .env ubuntu@<EC2_IP>:~/sunrise/.env        # secrets, never committed
scp docker-compose.aws.yml ubuntu@<EC2_IP>:~/sunrise/
ssh -i deploy/sunrise-deploy-key.pem ubuntu@<EC2_IP> \
  'cd ~/sunrise && sudo docker compose -f docker-compose.aws.yml up -d --build'
```

Seed runs automatically on backend start; the scheduler picks up all sources within 60s. Point the dashboard at the new API by rebuilding with `VITE_API_BASE=http://<EC2_IP>:8000/api`.

Backfill/re-run analysis manually if needed:

```bash
python -m app.maintenance    # cluster unclustered articles + analyze pending events
```

## How to add a source

Add an entry to `SEED_SOURCES` in `backend/app/seed.py` (or insert directly):

```json
{
  "slug": "imf", "name": "IMF News",
  "url": "https://www.imf.org/en/News/RSS?Language=ENG&category=news",
  "type": "rss",            // or "html" with an extraction strategy
  "schedule": "*/15 * * * *",
  "category": "GEOPOLITICS", "credibility": 0.9,
  "strategy": {"fields": {}}
}
```

The scheduler picks up new sources within 60 seconds. For HTML sources provide a `list_selector` + field selectors; if they break, the healing agent will rewrite them.

## API overview

```
GET  /api/health                     GET  /api/events (?min_urgency=&level=&category=)
GET  /api/events/{id}                GET  /api/sources
GET  /api/scrapers/health            GET  /api/scrapers/{id}/runs
GET  /api/scrapers/{id}/healing-history
GET  /api/scrapers/{id}/articles    (recent articles per collector)
POST /api/scrapers/{id}/run          POST /api/scrapers/{id}/heal
GET  /api/stats                      GET  /api/stream   (SSE live updates)
GET  /api/preferences                PUT  /api/preferences
```

## Telegram setup

1. Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN`.
2. Message your bot once, then get your chat ID from `https://api.telegram.org/bot<TOKEN>/getUpdates` → put it in `TELEGRAM_CHAT_ID`.
3. Events at urgency ≥ 61 (HIGH/CRITICAL) are pushed immediately with asset impacts and clearly labeled AI interpretation. Lower-urgency events don't spam.

### Multi-subscriber bot

Sunrise ships with a built-in Telegram subscriber bot — **anyone can receive alerts**, not just you.

**Live bot: [@sunrisescraperbot](https://t.me/sunrisescraperbot)** — send `/start` to subscribe.

- The scheduler process long-polls Telegram for updates (no webhook or public URL needed).
- Anyone who sends `/start` to your bot is registered as a subscriber with their own preferences and starts receiving events.
- Each alert fans out to every subscriber, filtered by *their* settings.
- Your own `TELEGRAM_CHAT_ID` keeps working as the owner channel (no duplicates if you also subscribe via the bot).

Subscriber commands:

| Command | Effect |
|---|---|
| `/start` | Subscribe (default: urgency ≥ 61) |
| `/urgency 80` | Only receive events at that threshold or higher |
| `/assets BTC,SPY` | Only events touching those symbols |
| `/categories crypto,macro` | Filter: `crypto`, `macro`, `stocks`, `geopolitics`, `commodities` |
| `/status` | Show current settings |
| `/stop` | Unsubscribe |

Every new subscriber receives a welcome message stating that alerts are AI interpretation with confidence levels — never financial advice.

To run the poller standalone instead of inside the scheduler:

```bash
python -m app.services.notifications.bot_subscribers
```

## Running tests

```bash
cd backend && ./.venv/bin/python -m pytest tests -q    # 40 tests
```

Covers: extraction methods (CSS/XPath/JSON-LD/OG), malformed HTML, health anomaly detection, dedup fingerprints, candidate safety checks, accept/reject validation paths, urgency blending bounds, Telegram formatting (incl. no-prediction language), clustering similarity, and API round-trips on an isolated SQLite DB.

## Architecture notes

- **LLM never executes code** — healing strategies are declarative JSON validated by Pydantic schemas plus static safety checks before execution.
- **AI speculation is labeled** — every alert and event detail separates *what happened* (fact) from *why it may matter* (AI interpretation with confidence).
- **Graceful degradation** — no LLM key: articles still scrape/store; analysis stays PENDING and retries; healing keeps the scraper DEGRADED and retries later. No SMTP/Telegram: those channels no-op.
- **Politeness** — robots.txt checked, per-host rate limiting, timeouts, snapshot retention capped at 5 pages/source.

## Known limitations

- Single-tenant demo user model (no auth beyond admin token gating).
- Event clustering is fuzzy-title based within a 48h window — sophisticated entity resolution is future work.
- Playwright not wired in; JS-rendered listings aren't supported yet.
- Urgency scoring weights are sensible defaults, not calibrated against historical price moves.

## Demo script (for judges)

Live deployment: dashboard at https://sunrise-dashboard.pages.dev reading from a backend that scrapes, analyzes and alerts continuously.

1. Open the dashboard — Market Pulse shows sources healthy, events flowing.
2. Open an event → see FACT vs AI INTERPRETATION separation, urgency gauge, affected assets and affected markets.
3. Critical/high events arrive on Telegram formatted with asset impacts; low-urgency ones never spam.
4. Scraper Health page → status per source, success rates, strategy versions, healing history timelines.
5. Self-healing demo: `python -m app.demo.break_scraper fed` → next run fails → dashboard shows FAILED/DEGRADED with metrics.
6. Healing agent runs automatically → timeline: analyzing → generating candidate → validating (score) → vN+1 activated → recovered.
7. Next run HEALTHY again. *"The website changed. The scraper broke. Sunrise noticed, repaired itself, validated the repair, and kept delivering market intelligence."*

## Project structure

```
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routes + SSE stream
│   │   ├── core/           # config, structured logging, redis channels
│   │   ├── db/             # async engine/session
│   │   ├── models/         # SQLAlchemy schema (12 tables)
│   │   ├── schemas/        # API response models
│   │   ├── llm/            # provider-agnostic client + Pydantic output schemas
│   │   ├── services/
│   │   │   ├── scraping/   # fetcher, strategy executor, health, runner, brightdata adapter
│   │   │   ├── healing/    # agent, validation pipeline, prompts
│   │   │   ├── analysis/   # clustering, analyzer, urgency blending
│   │   │   ├── notifications/  # telegram, email, preference dispatcher
│   │   │   └── deduplication/
│   │   ├── workers/        # arq tasks (scrape / analyze / heal / notify)
│   │   ├── scheduler/      # APScheduler cron loop
│   │   └── demo/           # break_scraper / trigger_healing commands
│   └── tests/              # pytest suite
├── frontend/               # React + Vite + Tailwind dashboard
├── deploy/                 # AWS EC2 launch scripts
├── docker-compose.yml      # local dev (postgres+redis) / full stack
├── docker-compose.aws.yml  # production backend-only stack
└── Makefile
```
