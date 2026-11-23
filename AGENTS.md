<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance for the new AWS experience

This user has signed up for the new AWS experience. This experience lets you sign into AWS using a social provider and requires the following additional context.

Where this guidance conflicts with the project's own instructions, the project's instructions take precedence.

## Context
### Terminology:
- Say "project" instead of "account" — a project contains an AWS account and settings for sharing with other collaborators
- Say "team member" instead of "IAM user" — users are invited by email, not created or federated in IAM
- Say "AWS Settings" when referring to management tasks at [settings.aws.com](https://settings.aws.com/) (project management, billing, team members, spend limits). Users view their actual AWS resources in the AWS Management Console.
- Say "selected Region" when referring to the user's Region — not "home Region"
- The user has a managed IAM experience. This includes a managed service control policies (SCP) and resource control policies (RCP) that govern the use of AWS. They will still need to use IAM to create policies to let services work with each other. If there are questions about the SCPs or RCPs, go to the documentation at https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html
### Constraints:
- All projects share a single AWS Region determined by the user's contact address. Resources cannot be created in other Regions
- When developing:
  - MUST create all Regional resources in the project's assigned Region
  - You CAN create AWS WAF and Cloudwatch Logs resources in us-east-1 when there are global resources (like a global WAF instance) that require a connection to dependencies in us-east-1. You should not use these for any other reason, because resources in the selected Region will provide lower cost (due to no cross-Region traffic), increased availability (due to no cross-Region traffic), and easier manageability (due to not needing to look in another Region).
When you need to do an inventory of resources, you need to look in both the selected Region and us-east-1 for Cloudwatch Logs or WAF resources.
  - MUST NOT attempt to create Lambda, API Gateway, or other Regional resources in any other Region
  - MUST direct users to confirm their Region in AWS Settings > View all projects > Overview > Additional Info > Region. If the user cannot confirm their Region, check in ~/.aws/config
  - MUST NOT use Lambda@Edge — excluded from both Lambda and CloudFront
  - MUST NOT use CloudFormation StackSets — no multi-account or multi-Region deployments
  - MUST NOT attempt cross-Region actions — no cross-Region replication for DynamoDB/S3/RDS, no multi-Region KMS keys
  - MUST NOT use Route 53 cross-Region routing — geolocation, latency-based, and failover routing policies are not available
  - CloudFront is a global service and its actions ARE allowed in `us-east-1`. A user can create a CloudFront distribution pointing to their project-region Lambda function URL or API Gateway. However, Lambda and API Gateway themselves MUST NOT be created in `us-east-1` — they must be in the project Region.
  - Reduced availability in `eu-north-1` specifically: Amazon Rekognition, Amazon Textract, Amazon Personalize, AWS App Runner are not available in that Region.
- IAM permissions for human access are managed by AWS. Don't assign roles to team members unless absolutely necessary
- The user may have a spend limit if they are on the paid plan. The limit pauses their project if it is exceeded. If resources suddenly become inaccessible, ask if they have a spend limit configured. Only project owners can modify a spend limit.
- When developing:
  - MUST ask about spend limit status if the user reports sudden "Access Denied" errors on operations that previously worked
  - MUST direct users to check spend status in AWS Settings > Billing
  - MUST check if a user has upgraded their account to the paid plan
  - MUST ask the user if they want to clean up the successfully created resources or keep them to reduce cost
- The user sets up billing, creates spend limits, and retrieves and pays invoices in AWS Settings. The user creates budgets and optimizes their costs in the AWS Billing and Cost Management console
- Not all AWS services are available. If a service isn't working, do the following:
  1. Run the command `aws freetier get-account-plan-state`
  2. If `accountPlanType` is `FREE`, check the [Free Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-free-tier) next,
  3. If `accountPlanType` is `PAID`, check the [Paid Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-paid-plan).
  4. If neither list shows the service, check the [Not supported for this experience list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#unsupported-services). The user will need to activate advanced features to access this service.
- Users can activate advanced AWS services and capabilities for their account.
- Before starting a task, check whether a relevant AWS skill is available. Load the skill with retrieve_skill and prefer its guidance over general knowledge.
### Help level

- help_level: LOW (the user selected this for the current AWS work).

You CAN update this rule file to save a user's help_level.

Constraints for each level:

**LOW:**
- MUST follow all constraints in this context file
- MUST execute the user's request without modification
- MUST NOT ask clarifying questions unless the action would create a security vulnerability
- MUST NOT suggest alternatives or improvements

**MEDIUM:**
- MUST execute the user's request
- MAY ask up to two clarifying questions per task if the request has an ambiguity or a potential issue
- MUST NOT repeat a question or suggestion the user has already dismissed
- MUST NOT explain trade-offs or alternatives unless the user asks

**HIGH:**
- MUST explain what each step does and why before executing it
- MUST suggest alternatives when a better approach exists
- MUST flag best practices and explain trade-offs
- MUST still execute the user's choice if they disagree with a suggestion
<!-- END AWS Agent Toolkit rules -->

---

# Sunrise — project guide for agents

> Last updated: **2026-11-23** (paper-trading release).
> Read this before changing code. The AWS block above still applies to AWS work;
> the project-specific instructions below take precedence where they conflict.

## 1. What this is

Sunrise is an autonomous financial-intelligence platform. It scrapes public
financial news, clusters articles into market events, scores urgency with an LLM,
sends Telegram/email alerts, and repairs broken scrapers with a validated
LLM-generated extraction strategy. It also now ships a **paper-trading desk**.

Production URLs:

- Dashboard: https://sunrise-dashboard.pages.dev
- Paper desk: https://sunrise-dashboard.pages.dev/trading
- API proxy (Cloudflare Worker): https://sunrise-api-proxy.devbulchandani876.workers.dev/api
- Origin (Caddy TLS): https://52.7.157.152.sslip.io
- Repo: https://github.com/devbulchandani/sunrise

## 2. Current state (important)

- Market pipeline is live on AWS EC2 `i-04187b97cb6a30803` (`t4g.small`, `us-east-1`) with Caddy TLS, Postgres, Redis, API, arq worker, and scheduler.
- **Paper trading is implemented, tested, and deployed.** It is a Sunrise-owned
  simulator: simulated quotes, per-user ledger, manual confirmation, risk checks,
  audit trail, a portfolio view (holdings, weights, cost basis, P&L), and a
  linked-Telegram ticket. It does **not** connect to Upstox/Zerodha/any broker.
- **Live trading is deliberately disabled.** `TRADING_ENABLED=false` and no live
  order routes exist. Do not enable live trading without an explicit user decision,
  broker integration, and legal/compliance review.
- Production paper config: `PAPER_TRADING_ENABLED=true`,
  `PAPER_TRADING_FROZEN=false`, 22 NSE symbols, ₹10,00,000 opening balance,
  ₹20 simulated fee, market-hours enforcement off.
- Backend test suite: **84 tests passing**. CI (`.github/workflows/ci.yml`) runs
  pytest + `tsc` + Vite build. Keep it green.
- The repo history was rewritten to purge an accidentally committed EC2 private
  key. The key pair no longer exists and the instance has no SSH key/port 22.
  GitHub may still serve the old blob by SHA until support purges cached views.

## 3. Stack and layout

```
backend/                 FastAPI + async SQLAlchemy 2 + Pydantic v2
  app/api/               public market routes + trading router
  app/core/              config, auth, logging, redis
  app/db/                session + additive schema upgrades
  app/llm/               provider-agnostic client + output schemas
  app/models/            all SQLAlchemy tables
  app/services/
    analysis/            clustering, analyzer, urgency, research, IPO
    deduplication/
    healing/             agent, validation, prompts, recovery
    notifications/       telegram, email, dispatcher, bot, ops alerts
    scraping/            fetcher, extractor, runner, health, lock, adapters
    trading/             accounts, broker, instruments, quotes, risk
  app/workers/           arq tasks
  app/scheduler/         APScheduler cron + paper open-order fills
  tests/                 pytest suite
frontend/                React 18 + Vite 5 + TypeScript + Tailwind 3
  src/components/        Header, ui, icons, charts, ticker, palette
  src/pages/             MarketPulse, EventDetail, Scrapers, System, Trading
  src/services/          api, auth, trading
deploy/                  Caddyfile, EC2 bootstrap, Cloudflare Worker
docs/plans/              trading phase plan
```

Key docs: `README.md`, `SECURITY.md`, `docs/plans/trading-execution-phase.md`.

## 4. Run locally

Prerequisites: Python 3.12+ (Docker uses 3.13), Node 20+, Docker.

```bash
make infra                 # postgres + redis
cp .env.example .env       # fill LLM/Telegram keys as needed
make install               # backend venv + npm install
make seed                  # create tables + sources + demo user
make backend               # uvicorn :8000
make worker                # arq worker
make scheduler             # cron + telegram poller + paper fills
make frontend              # vite :5173
make test                  # 84 tests
```

- Backend config uses pydantic-settings with `env_file=(".env", "../.env")`;
  later files take precedence. Shell env overrides both.
- Frontend dev proxies `/api` to `localhost:8000`; production uses
  `VITE_API_BASE` from `frontend/.env.production`.
- `make install` uses `pip install -r requirements.txt` (there is no package
  metadata; do not reintroduce `-e ".[dev]"`).

### Local paper-desk UI without real Cognito

`src/services/auth.tsx` has a **dev-only** bypass:

```bash
VITE_DEV_AUTH=true VITE_API_BASE=http://127.0.0.1:8001/api npm run dev
```

It is guarded by `import.meta.env.DEV`, so production builds contain no bypass.
For local backend QA, run the app with `require_paper_trader` overridden in a
throwaway script (or a valid Cognito token). Never add a production auth bypass.

## 5. Configuration and secrets

- `.env` files are gitignored. Never commit secrets, `.pem`, `.key`, or
  `.brightdata/`.
- Production runtime uses `/home/ubuntu/sunrise/.env` on EC2. The same settings
  are stored in AWS Secrets Manager (`sunrise/production/app-env`) but **are not
  auto-synced**; when changing production config, update the instance `.env`
  and the secret.
- `ADMIN_TOKEN` gates operational endpoints from CLI/curl; it is never shipped to
  the browser. `ADMIN_EMAILS` is the Cognito email allowlist for dashboard
  admin actions. With neither set (local dev), admin routes are open by design.
- Cognito is the only user auth: access tokens are verified (RS256, issuer,
  `token_use`, client ID) in `app/core/auth.py`. Public market-data reads remain
  public; account/order data is authenticated.
- CORS is restricted to the Pages dashboard and local hosts. Caddy terminates TLS;
  only 80/443 are public; the API binds to `127.0.0.1:8000`.
- The Cloudflare API token lives in root `.env` as `CLOUDFARE_API_TOKEN` (spelling
  is intentional). Do not print or commit it; rotate any token pasted into chat.

## 6. Data and schema rules

- `app/db/upgrade.py::ensure_schema()` is the migration path: `create_all` plus
  idempotent additive DDL. There is no Alembic. New tables appear automatically;
  new columns on existing Postgres tables need an explicit
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `upgrade.py`.
- `Article` has a unique `(source_id, url)` index and inserts use
  `ON CONFLICT DO NOTHING`; feeds can repeat URLs in one batch. Do not replace
  this with plain inserts.
- `market_events`/`articles` share a retention lifecycle; old events and orphaned
  events are purged. Do not reintroduce orphan event rows.
- SQLite tests return naive datetimes; use the `_aware()` helper pattern in
  trading code when comparing to `datetime.now(timezone.utc)`.
- Money uses `Decimal`/`Numeric(18,2|4)`, never floats, inside the ledger.
- Use `select(...).with_for_update()` on account/proposal rows for order mutations.

## 7. Paper-trading invariants — do not break

Files: `backend/app/services/trading/{accounts,broker,instruments,quotes,risk}.py`,
`backend/app/api/trading.py`, `backend/app/schemas/trading.py`,
`frontend/src/pages/Trading.tsx`, `backend/tests/test_trading.py`.

1. **No live broker.** No broker credentials, no live order endpoint, no network
   call to a broker. `TRADING_ENABLED` stays false.
2. **Simulated quotes only.** `quotes.py` generates deterministic simulated INR
   prices; every API/UI surface must label them `simulated`.
3. **Manual confirmation.** A proposal can be created from a signal, but no order
   is submitted until the authenticated user calls
   `POST /api/trading/proposals/{id}/confirm`. Never accept LLM/Telegram text as
   an order payload.
4. **Risk twice.** `evaluate_order()` runs at proposal time and again at confirm
   time with a fresh quote. Keep both passes.
5. **Idempotency.** `(account_id, client_order_id)` and `proposal_id` are unique;
   confirmation is idempotent. Do not remove the constraints or the existing-order
   return path.
6. **Audit.** Proposal/fill/rejection/cancel events go to `audit_events`; cash and
   position changes are transactional with the order.
7. **Kill switches.** `PAPER_TRADING_ENABLED` disables the desk.
   `PAPER_TRADING_FROZEN` currently blocks the whole paper API, including
   cancellation, and open-order fills. If you split read/cancel access from
   new-order access, keep cancellation available while frozen.
8. **Account isolation.** Accounts/positions/orders are keyed to the Cognito
   `sub` via `users.cognito_sub`; never query another user's account by ID alone.
9. **Fills.** Market orders fill immediately with simulated slippage; LIMIT
   orders fill only when crossed, otherwise rest OPEN and are filled by the
   scheduler. Cancellation is only valid for OPEN orders.
10. **Tests.** Extend `backend/tests/test_trading.py` for any change to risk,
    fills, idempotency, cancel, reconciliation, or auth behavior.
11. **Telegram bridge.** Trading callbacks are honoured only for a private chat
    already bound to a Cognito `sub` through a single-use, expiring link code
    (`PAPER_TELEGRAM_LINK_TTL_SECONDS`). Buttons carry a symbol from the fixed
    paper universe; free text is never an order. A button creates a proposal; a
    second tap confirms it through the same `broker.confirm_proposal` path
    (owner-scoped, risk twice, idempotent, expiring). Refuse group chats and keep
    `PAPER_TELEGRAM_ENABLED` as a second kill switch.

Trading API (all under `/api/trading`; auth required except `/config` and
`/instruments`): `config`, `instruments`, `quote/{symbol}`, `account`,
`portfolio`, `positions`, `orders`, `audit`, `proposals`,
`proposals/{id}/confirm`, `proposals/{id}/reject`, `orders/{id}/cancel`,
`telegram`, `telegram/link-code`, admin `reconcile`.

## 8. Frontend guide

- Design system: Instrument Serif display, Geist UI, JetBrains Mono data.
  Ink-navy surfaces, single amber accent, jade/rose semantic colors. Keep new UI
  inside `components/ui.tsx`, `icons.tsx`, `Sparkline.tsx`, `Ticker.tsx`.
- Tailwind is v3; tokens live in `tailwind.config.js` and `src/index.css`.
  Use `.panel`, `.label`, `.display`, `.num`, `.stagger`, focus rings, and reduced
  motion. Avoid new colors/fonts without a reason.
- Routes are lazy-loaded in `App.tsx`; keep heavy pages (charts/Trading) lazy.
- `services/api.ts::request()` adds the Cognito bearer token and maps API errors
  to `ApiError`. Reuse it; do not bypass auth.
- Admin/paper actions require sign-in; the dashboard header handles Cognito
  sign-in/sign-out. Clicking the account chip opens a menu (paper desk, Telegram
  trading, explicit Sign out) — it must never sign the user out directly. The
  OIDC user is persisted in tab-scoped `sessionStorage` so refresh keeps the
  session; `AuthCallback` exchanges the code exactly once under StrictMode.
- The article drawer and review modal use `createPortal` so they layer above the
  sticky header. Keep portal/dialog/Escape/scroll-lock behavior.
- Verify with `npx tsc --noEmit` and `npm run build` before committing. CI also
  runs both.

## 9. Deployment

### AWS

All commands below are run on the instance via SSM (no SSH):

```bash
export HOME=/root
git config --global --add safe.directory /home/ubuntu/sunrise
cd /home/ubuntu/sunrise
git fetch origin && git reset --hard origin/main
docker compose -f docker-compose.aws.yml up -d --build
```

- Use `git fetch && git reset --hard` (history was rewritten; `git pull` may fail).
- Caddy obtains/renews the Let's Encrypt cert for `52.7.157.152.sslip.io`.
- AWS CLI uses an SSO/root login session that expires. Run `aws login` first;
  `aws sts get-caller-identity` should work before using SSM.
- The instance has no SSH key pair or port 22 ingress. If the IP changes, update
  the Caddyfile hostname and the Worker `BACKEND` constant.
- Never print secret values from Secrets Manager.

### Cloudflare

- Worker source: `deploy/cloudflare/worker.js` (origin is the HTTPS Caddy host).
- Dashboard: `frontend/dist` deployed to Pages project `sunrise-dashboard`,
  branch `main`.
- Deploy commands use `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`; do not
  commit the token. This machine has had intermittent DNS failures resolving
  `api.cloudflare.com`; fix the resolver for the session (the earlier session
  used a temporary Node preload or `curl --resolve`) but never add that workaround
  to the repo.

## 10. Conventions

- Python: async SQLAlchemy, Pydantic v2, typed functions, structured loggers
  (`get_logger`), `Decimal` for money, no bare `except` unless deliberate.
- Tests: pytest, isolated SQLite where possible; run `pytest tests -q`.
- Commits: imperative, sentence case, one concern per commit (matches history).
- Never commit generated artifacts, `.env`, `dist/`, `.venv/`, `node_modules/`,
  or keys. `.gitignore` already covers them.
- Prefer additive changes to existing endpoints/models; do not break public
  market-data routes or the paper-desk auth boundary.
- For production changes, verify through the Worker with a real request and, when
  relevant, check the origin over TLS.

## 11. Known gaps / next steps

- **Live broker integration** (Upstox sandbox or another broker) is not built.
  It needs a separate explicit decision, broker terms/eligibility review, and
  legal/compliance review for India. Keep `TRADING_ENABLED=false` until then.
- Telegram paper trading is intentionally a **quick ticket**: market orders, one
  default size, no limit price or quantity picker (use the dashboard for those).
  Group chats and shared devices are unsupported; linking is private-chat only.
- Paper trading lacks **partial fills** and derivatives. The paper soak/Phase 3
  work in `docs/plans/trading-execution-phase.md` is still open.
- Frozen mode currently blocks cancellation as well as new orders; a
  read/cancel-only dependency would restore the plan's cancel-open-orders control.
- No Alembic; schema upgrades are additive. Destructive migrations need a plan.
- Urgency weights are defaults, not calibrated against market outcomes.
- Clustering is fuzzy title + token overlap; deeper entity resolution is future work.
- GitHub may still serve the old leaked-key blob; request a sensitive-data purge
  or keep the repo private until purged.

## 12. Quick start for a new session

1. `pwd` should be `/Users/devbulchandani/scraper-verse`.
2. `git status` must be clean; `git log -1`.
3. Read `README.md`, `SECURITY.md`, and the trading plan.
4. `cd backend && ./.venv/bin/python -m pytest tests -q` (84 pass).
5. `cd frontend && npx tsc --noEmit && npm run build`.
6. If deploying: confirm `aws login` works, then use SSM; deploy Pages with the
   Cloudflare token from `.env`.
7. Verify `https://sunrise-api-proxy.devbulchandani876.workers.dev/api/trading/config`
   reports `paper_enabled=true`, `live_enabled=false`, and that
   `/api/trading/account` returns 401 without a token.
8. Do not enable live trading.
