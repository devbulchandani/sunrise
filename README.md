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

10 public sources seeded by default: Federal Reserve press releases (HTML), ECB press RSS, Bank of England RSS, Cointelegraph, CoinDesk, BBC Business, Investing.com commodities, **TradingView Top Stories**, **Economic Times Markets (India)**, **LiveMint Markets (India)** — plus **MarketWatch via Bright Data** (registered only when `BRIGHTDATA_API_KEY` is set; see below). All public pages, robots.txt respected, rate-limited per host.

**TradingView** is fully client-rendered, but the article list ships server-side inside `<script type="application/prs.init-data+json">` tags — the `tradingview` source type walks those scripts and extracts the news items JSON directly (title, link, storyPath, published timestamp).

## Bright Data integration (Web Unlocker)

Sunrise's core collectors are owned infrastructure, but some financial sites run aggressive anti-bot protection that makes direct collection impractical — MarketWatch is a live example in this repo. For those targets Sunrise supports an auxiliary source type powered by **Bright Data's Web Unlocker** through the official `@brightdata/cli`:

```bash
npm i -g @brightdata/cli
bdata login                      # OAuth, once
# or: BRIGHTDATA_API_KEY=... in .env
```

Register a Bright Data-backed source (seeded automatically only when `BRIGHTDATA_API_KEY` is set):

```json
{"slug": "reuters_brightdata", "name": "MarketWatch via Bright Data",
 "url": "https://www.marketwatch.com/latest-news", "type": "brightdata", ...}
```

How it works:
1. On schedule, Sunrise invokes `bdata scrape https://www.marketwatch.com/latest-news --format markdown` (Web Unlocker handles proxies/retries/unblocking).
2. The returned markdown is parsed into headline entries by `brightdata_adapter.py`.
3. Those entries flow through the exact same pipeline as every other source: normalization → dedup → clustering → AI analysis → alerts.
4. Health metrics are tracked identically, so failures on this source are visible on the Scraper Health page too.

This keeps a clean separation: **owned self-healing collectors for the long tail, Bright Data for the walled gardens** — both feeding one intelligence pipeline. The Bright Data source is only seeded when `BRIGHTDATA_API_KEY` is set; without credentials it would otherwise fail on every run.

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
| `LLM_PROVIDER` | `openai` (OpenAI-compatible endpoint), `bedrock`, or `anthropic` |
| `LLM_MODEL` / `LLM_BASE_URL` | Model and endpoint for OpenAI-compatible providers. The example uses Gemini 3.1 Flash-Lite. Bedrock Mantle uses `openai.gpt-oss-20b` and `https://bedrock-mantle.us-east-1.api.aws/v1` |
| `LLM_API_KEY` | Provider key. For Bedrock Mantle, use the Bedrock bearer API key; it is sent as an `Authorization: Bearer` token |
| `LLM_BEDROCK_REGION` | Bedrock selected Region; defaults to `us-east-1` |
| `COGNITO_REGION` / `COGNITO_USER_POOL_ID` / `COGNITO_APP_CLIENT_ID` / `COGNITO_DOMAIN` | Cognito access-token verification and the userInfo fallback used to resolve the admin email |
| `TRADING_ENABLED` | Live broker execution is fail-closed (`false`); no live order routes exist |
| `PAPER_TRADING_ENABLED` | Enables the authenticated paper desk; live trading stays disabled |
| `PAPER_TRADING_FROZEN` | Emergency freeze for all paper proposals/orders |
| `PAPER_STARTING_CASH` / `PAPER_MAX_*` | Opening balance and deterministic per-order risk limits |
| `PAPER_TELEGRAM_ENABLED` | Enable/disable paper-trade buttons in Telegram (default on; still gated by the paper kill switches) |
| `PAPER_TELEGRAM_TICKET_NOTIONAL` / `PAPER_TELEGRAM_MAX_SYMBOLS` | Suggested Telegram ticket size (₹25,000 budget) and how many symbols get buttons |
| `PAPER_TELEGRAM_LINK_TTL_SECONDS` / `PAPER_TELEGRAM_INTENT_TTL_SECONDS` | Lifetime of a one-time `/link` code (600s) and of a Buy/Sell size prompt (300s) |
| `TELEGRAM_BOT_USERNAME` / `PUBLIC_DASHBOARD_URL` | Bot handle and dashboard links used in Telegram messages |
| `ARTICLE_RETENTION_DAYS` | Remove scraped articles older than this many days; defaults to 30 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram bot and owner destination; subscribers can also link their chat through the bot |
| `SMTP_*` / `EMAIL_FROM` | Email digests (optional) |
| `DEMO_MODE` | Enables demo break/heal commands |
| `ADMIN_TOKEN` | Ops-only token for `X-Admin-Token` on debug endpoints; never shipped to the browser |
| `ADMIN_EMAILS` | Comma-separated Cognito emails allowed to trigger runs/healing from the dashboard |

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

## Paper trading desk

Sunrise includes a **Sunrise-owned paper trading simulator** for the India-only
universe. It does not connect to Upstox, Zerodha, or any other broker, and it
cannot place a real order.

**Flow**

1. Open **Paper desk** in the dashboard (`/trading`) and sign in with Cognito.
2. Pick an NSE symbol from the curated universe, choose Buy/Sell and
   Market/Limit, and set a quantity.
3. **Review order** creates a short-lived proposal with a simulated quote and a
   full risk-check report (buying power, position cap, gross exposure, daily
   order/loss caps, limit band, market hours, duplicate/quantity checks).
4. Only **Confirm paper order** submits it. Market orders fill immediately
   against the simulated quote; crossed limits fill, otherwise they rest open
   and are checked once a minute. Any open order can be cancelled.
5. Every proposal, confirmation, fill, rejection, and cancellation is written
   to `audit_events`; cash and positions are updated in the same transaction.

**Portfolio.** The desk shows one book: equity, cash, invested cost, realised and
unrealised P&L, total return since the opening balance, and every stock held with
its quantity, average cost, last simulated price, market value, weight in the
book, and P&L percentage. The same totals are available from
`GET /api/trading/portfolio`.

**Telegram trading.** A linked Telegram chat gets Buy and Sell buttons under
impact alerts for symbols in the paper universe. Tap Buy or Sell, reply with a
share quantity (e.g. `10`) or a rupee amount (e.g. `₹25000`), review the sized
proposal, then confirm. Sizes are the only thing typed; the symbol and side come
from the server-issued buttons. Linking is a one-time handshake:

1. On `/trading`, open **Trade from Telegram** and generate a link code.
2. Send `/link CODE` to [@sunrisescraperbot](https://t.me/sunrisescraperbot) from
   a **private chat**. Codes are single-use and expire in 10 minutes.
3. The bot then shows `/portfolio`, trade buttons, and confirmations for that chat.
   `/unlink` disconnects it, and `/cancel` aborts a pending size prompt.

Group chats are refused, free text is never parsed into an order, and every
Telegram order still runs the same server-side risk policy and expiry as the
dashboard.

**API** (`/api/trading`, Cognito access token required except `/config` and
`/instruments`):

```
GET  /config                      GET  /instruments
GET  /quote/{symbol}              GET  /account
GET  /portfolio                   GET  /positions
GET  /orders                      GET  /audit
POST /proposals                   POST /proposals/{id}/confirm
POST /proposals/{id}/reject       POST /orders/{id}/cancel
GET  /telegram                    POST /telegram/link-code
DELETE /telegram                  POST /reconcile   (admin)
```

**Guardrails:** sandbox/simulated quotes only, explicit manual confirmation, no
LLM-generated order payloads, deterministic server-side limits, per-user
isolation by Cognito subject, durable audit events, and independent
`PAPER_TRADING_ENABLED` / `PAPER_TRADING_FROZEN` kill switches. Quotes are
generated from a seeded, slowly drifting base price and are labelled
`simulated` everywhere. Market-hours enforcement defaults to off so the desk
can be exercised outside NSE hours; turn it on with
`PAPER_ENFORCE_MARKET_HOURS=true`. Telegram trading adds a second gate,
`PAPER_TELEGRAM_ENABLED`, plus private-chat-only linking, single-use codes, and
proposal expiry.

**Not implemented:** live broker connectivity, Upstox sandbox credentials,
partial fills, and options/futures. The Telegram ticket is deliberately simple:
market orders only, with the size typed in chat and no limit price (use the
dashboard for limit orders). Live execution remains a separate release gate (see
the trading plan).

## Deployment

| Component | Host | Notes |
|---|---|---|
| Dashboard | Cloudflare Pages | `sunrise-dashboard.pages.dev`; built with `VITE_API_BASE=https://sunrise-api-proxy.devbulchandani876.workers.dev/api` |
| API proxy | Cloudflare Worker | `sunrise-api-proxy`; origin is `https://52.7.157.152.sslip.io` |
| TLS + backend + worker + scheduler + Postgres + Redis | AWS EC2 `t4g.small`, `us-east-1` | Instance `i-04187b97cb6a30803`; one instance via `docker-compose.aws.yml` |

The backend health endpoint is `https://sunrise-api-proxy.devbulchandani876.workers.dev/api/health`. Caddy terminates TLS on ports 80/443 with a Let's Encrypt certificate for the `sslip.io` hostname and proxies to the API over the private compose network; the API itself is bound to `127.0.0.1:8000`. The EC2 host has no SSH key pair and no port 22 ingress; connect through Systems Manager with `aws ssm start-session --target i-04187b97cb6a30803 --profile sunrise-new --region us-east-1`. Runtime secrets and settings are stored in AWS Secrets Manager (`sunrise/production/app-env`) and materialized into the instance's `.env` at deploy time. Never copy a local `.env` onto the host or commit secret values.

Admin actions (`Run now`, `Heal`) authenticate with the signed-in user's Cognito token against `ADMIN_EMAILS`, or with `X-Admin-Token` from a shell for CLI/ops. The dashboard never receives an admin secret. Production currently calls Bedrock Mantle through the OpenAI-compatible client using `LLM_MODEL=openai.gpt-oss-20b`, `LLM_BASE_URL=https://bedrock-mantle.us-east-1.api.aws/v1`, and a Bedrock bearer key in `LLM_API_KEY`. The alternative Bedrock Runtime Converse provider uses `LLM_PROVIDER=bedrock`, an enabled Bedrock model ID, and the EC2 instance role. For Telegram, set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; the scheduler starts the bot poller and dispatches qualifying alerts to subscribed chats.

> **Security note:** see [SECURITY.md](SECURITY.md). an early commit accidentally tracked an EC2 deploy key. The key pair no longer exists in AWS and the file has been purged from git history; SSH access is disabled entirely (SSM only). If you cloned this repository before that rewrite, re-clone rather than pulling. GitHub may continue to serve the old blob by commit SHA until support purges cached views; request a sensitive-data purge if that matters for your threat model.

The dashboard's Cognito public configuration is in `frontend/.env.production` (pool and client IDs are public identifiers, not secrets). Open registration requires email verification and TOTP MFA. Browser tokens are memory-only; the Cloudflare Worker CORS policy allows the Pages dashboard plus local development. The backend verifies Cognito access tokens for the paper desk; existing market-data routes remain public. The OIDC user (access/refresh tokens) is kept in tab-scoped `sessionStorage` so a refresh does not drop the session, and signing out clears it. Paper trading is enabled in production (`PAPER_TRADING_ENABLED=true`) with simulated quotes and `TRADING_ENABLED=false`; the live broker remains disconnected. **Live trading is disabled and no broker is connected.** See [the trading phase plan](docs/plans/trading-execution-phase.md) for the India-only paper/manual milestones and regulatory gates.

Inside the SSM session, update the checkout and restart the stack with:

```bash
cd /home/ubuntu/sunrise
git fetch origin && git reset --hard origin/main
docker compose -f docker-compose.aws.yml up -d --build
```

Seed runs automatically on backend start; the scheduler picks up all sources within 60s. Articles and their market events older than `ARTICLE_RETENTION_DAYS` / `EVENT_RETENTION_DAYS` (30 days by default) are purged daily, along with any orphaned events left by older runs. The Worker origin is configured in `deploy/cloudflare/worker.js`; after an origin change, deploy it with Wrangler. Rebuild Pages with the `VITE_API_BASE` value above when its API URL changes. `deploy/aws-ec2.sh` provisions a fresh instance without an SSH key (SSM-only access) and opens only 80/443; the live instance predates it.

The backend startup also ensures the unique notification index exists. This makes concurrent dispatcher attempts idempotent and allows the notification scheduler to record and deliver Telegram alerts.

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
GET  /api/auth/me                   (Cognito access token required)
GET  /api/events/{id}                GET  /api/sources
GET  /api/scrapers/health            GET  /api/scrapers/{id}/runs
GET  /api/scrapers/{id}/healing-history
GET  /api/scrapers/{id}/articles    (recent articles per collector)
POST /api/scrapers/{id}/run          POST /api/scrapers/{id}/heal
GET  /api/stats                      GET  /api/stream   (SSE live updates)
GET  /api/preferences                PUT  /api/preferences

GET  /api/trading/config             GET  /api/trading/instruments
GET  /api/trading/account            GET  /api/trading/positions
GET  /api/trading/orders             POST /api/trading/proposals
POST /api/trading/proposals/{id}/confirm
POST /api/trading/proposals/{id}/reject
POST /api/trading/orders/{id}/cancel
```

`POST /api/scrapers/{id}/run` and `/heal` enqueue work on the arq worker and
return immediately; the dashboard polls the run/healing history for results.
Admin routes accept `X-Admin-Token` (ops) or a Cognito access token whose email
is listed in `ADMIN_EMAILS`. The SSE stream emits `new`, `alerts`,
`scraper_failure`, and `healed` events.

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
| `/status` | Show current settings, including whether Telegram trading is linked |
| `/portfolio` | Your simulated paper holdings and P&L |
| `/link CODE` | Link this private chat to your signed-in Sunrise account |
| `/unlink` | Disconnect Telegram trading (alerts continue) |
| `/cancel` | Abort a pending Buy/Sell size prompt |
| `/help` | How alerts and paper trading work |
| `/stop` | Unsubscribe |

Every new subscriber receives a welcome message stating that alerts are AI interpretation with confidence levels — never financial advice.

**Paper-trade buttons.** Linked chats see Buy buttons for up to four affected
symbols in the paper universe (plus Sell when a position is held). A tap creates
a proposal; a Confirm tap submits it. Buttons are never shown in group chats, and
unlinked subscribers keep receiving notification-only alerts.

To run the poller standalone instead of inside the scheduler:

```bash
python -m app.services.notifications.bot_subscribers
```

## Running tests

```bash
cd backend && ./.venv/bin/python -m pytest tests -q    # 89 tests
```

Covers: extraction methods (CSS/XPath/JSON-LD/OG), malformed HTML, health anomaly detection, dedup fingerprints, candidate safety checks, accept/reject validation paths, urgency blending bounds, Telegram formatting (incl. no-prediction language), clustering similarity, and API round-trips on an isolated SQLite DB.

## Architecture notes

- **LLM never executes code** — healing strategies are declarative JSON validated by Pydantic schemas plus static safety checks before execution.
- **AI speculation is labeled** — every alert and event detail separates *what happened* (fact) from *why it may matter* (AI interpretation with confidence).
- **Graceful degradation** — no LLM key: articles still scrape/store; analysis stays PENDING and retries; healing keeps the scraper DEGRADED and retries later. No SMTP/Telegram: those channels no-op.
- **Politeness** — robots.txt checked, per-host rate limiting, timeouts, snapshot retention capped at 5 pages/source.

## Known limitations

- Paper trading uses simulated quotes, not a market-data feed; it is a ledger simulator, not a broker sandbox.
- Live broker connectivity, partial fills, and derivatives are not implemented. Telegram trading is paper-only and limited to market orders.
- Event clustering combines fuzzy title matching with token overlap inside a 48h window. It rejects template headlines ("X Share Price Live Updates") but is not full entity resolution.
- Network/anti-bot failures are retried with backoff and alerted on, but deliberately do not trigger strategy healing — a new selector cannot fix a blocked request.
- Playwright not wired in; JS-rendered listings aren't supported yet.
- Urgency scoring weights are sensible defaults, not calibrated against historical price moves.
- Schema upgrades are additive and idempotent (`app.db.upgrade`); destructive migrations would need Alembic.

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
