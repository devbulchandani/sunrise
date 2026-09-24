# Sunrise trading execution: next phase plan

Status: in progress. Cognito identity foundation is provisioned; broker integration is not connected and no orders can be submitted.

## Current project state

Sunrise scrapes market news, clusters articles, analyzes events through an LLM, stores affected symbols and urgency, shows results in a React dashboard, and sends Telegram notifications. The LLM client supports OpenAI-compatible endpoints, Anthropic, and Bedrock Runtime. Telegram currently handles subscriptions and alert preferences; it has no trading commands. The dashboard has no user login. The Cloudflare Worker forwards requests to a public backend and adds wildcard CORS. API reads are public; only a few operational write routes use an optional admin-token dependency. Authentication and authorization are therefore the first prerequisites for trade controls.

## Research findings

- Scope is India-only for now. Upstox documents a sandbox API for order placement/modify/cancel with sandbox tokens, 24/7 testing, and no live funds. Zerodha's official FAQ says it has no Kite Connect sandbox. Upstox is therefore the first sandbox candidate, pending the user's broker choice and any terms/eligibility needed for a multi-user product.
- The Upstox sandbox is an integration-test environment; it does not by itself provide isolated paper accounts and market fills for Sunrise users. Keep each user's paper portfolio/order ledger isolated in Sunrise if the sandbox isn't designed for per-user accounts. Never share a sandbox token as if it were each user's own brokerage authorization.
- Current SEBI/exchange rules for Indian retail API/algo trading need product-specific review. SEBI's 2025 timeline extension states the February 2025 retail algorithmic-trading framework applies to stock brokers from April 1, 2026. NSE standards specify client static-IP mapping for API access and further requirements for retail algos. A multi-user hosted app that routes order APIs may need broker/exchange approvals or other controls. Manual confirmation does not automatically exempt API orders; confirm with the broker and qualified Indian securities counsel before any live account connection.
- FINRA warns about unregistered auto-trading services and AI performance claims. Whether Sunrise is a private tool or serves friends/public affects broker and legal requirements. Confirm jurisdiction and audience before live execution; seek qualified advice if the product gives recommendations or trades for other people.
- Store broker credentials in AWS Secrets Manager, restrict reads to the workload role, and audit access. Never put broker keys in the frontend, Cloudflare Worker, Telegram messages, source control, or logs.
- Bedrock remains the event-analysis provider. Model output is untrusted context; it must not directly construct or authorize broker orders.

## Recommended staged delivery

### Phase 0 — establish the security boundary

1. Add dashboard authentication and a server-side identity model before exposing account, position, or order endpoints. The current public API and wildcard CORS are not adequate for trading.
2. Make authorization explicit per user and account. For trading, replace open Telegram subscription as an authorization mechanism with owner-linked Telegram identity, allowlisted chat IDs, and step-up confirmation. Existing subscribers must never gain order permissions just by subscribing.
3. Add appropriate CSRF/origin protection, rate limits, audit events, secret redaction, backend ingress restrictions, and deployment-time checks that trading remains disabled by default.
4. Decide whether this stays a private tool for the owner's account or becomes available to others; confirm jurisdiction, broker eligibility, instrument classes, and who chooses orders.

**Exit criteria:** authenticated identities; deny-by-default trading permission; documented ownership mapping; no public path to account/order data; audited access; explicit `TRADING_ENABLED=false` kill switch.

**Progress:** Created Cognito user pool `us-east-1_V7pzjzvij` in the selected `us-east-1` Region with open email sign-up, email verification, strong password policy, deletion protection, and required TOTP MFA. Created no-secret public SPA OAuth client `6l372ppaohfv233ojmgkhqf2k6` with authorization code + PKCE, 15-minute access/ID tokens, one-day refresh token, refresh rotation and token revocation. Managed-login v2 domain `sunrise-trading-v7pzjzvij.auth.us-east-1.amazoncognito.com` is ACTIVE. Dashboard OIDC wiring and backend JWT verification are implemented locally. The existing market-data API remains public. No user account or broker token has been created.

### Phase 1 — paper broker adapter and order ledger

1. Implement an India-aware broker adapter for account/buying-power queries, asset lookup, quote retrieval, submit/cancel, and order/fill updates. Evaluate Upstox sandbox first, but verify whether it supports the desired multi-user isolation. If not, use a Sunrise-owned per-user paper ledger/simulator and keep Upstox sandbox for connector contract tests.
2. Persist order intents and immutable audit records: actor, channel, originating event, normalized request, risk checks, confirmation, broker IDs, status, fills, timestamps, and errors.
3. Make submissions idempotent with unique client order IDs. Use database uniqueness and an outbox/job flow so retries cannot duplicate an order. Reconcile open orders and positions with the broker after restarts.
4. Keep credentials server-side in Secrets Manager. Separate paper credentials/secrets from any future live credentials. For multi-user broker connections, prefer OAuth and encrypt per-user token material; do not collect brokerage passwords.

**Exit criteria:** paper-environment verification covers idempotency, duplicate callbacks, cancel/replacement behavior, partial fills, rejections, restart reconciliation, and secret redaction. No live URL or live credentials in this phase.

### Phase 2 — explicit trade proposals from both channels

1. An event may create an optional proposal only: instrument, side, order type, quantity/notional, price guard, time in force, rationale/source, expiry. Validate against broker assets and fetch a fresh quote before confirmation.
2. The dashboard displays the proposal, account, side, quantity, estimated notional, price guard, expiry, risk summary, and paper/live mode. Require an authenticated user's explicit confirmation.
3. Telegram uses a short-lived, single-use callback or link bound to the verified owner and proposal. Enforce sender/chat allowlist, expiry, replay protection, and rate limits. Never accept free-form LLM or Telegram text as an order payload.
4. Both channels call the same server-side proposal/confirmation service and deterministic risk checks. Neither channel calls the broker directly.
5. Enforce limits before each submission: eligible instrument and market state, stale-quote rejection, per-order notional, max exposure, daily loss/order caps, buying power, duplicate-order checks, allowed order types, and global/per-account kill switch. Fail closed.

**Exit criteria:** end-to-end paper-only workflow through Telegram and dashboard with identical policies, explicit confirmation, complete audit trail, and a tested kill switch.

### Phase 3 — shadowing, paper soak, and readiness

1. Run signal-to-proposal in shadow mode without submitting orders; record outcomes and realistic slippage assumptions. Do not represent results as guaranteed or predictive.
2. Soak paper trading across market sessions; inspect reconciliation drift, outages, rate limits, duplicate signals, stale data, partial fills, rejected/canceled orders, and restart recovery.
3. Alert on broker disconnects, rejections, stale account state, risk-limit trips, unexpected positions, and reconciliation failures. Provide operator pause and cancel-open-orders controls.
4. Document risk disclosures, audit retention/access, incident handling, data licensing, and applicable legal/broker requirements for the user's jurisdiction and audience.

**Exit criteria:** written go/no-go review with measured reconciliation/error rates, user-approved limits, successful kill-switch drill, and no unresolved security or compliance blocker.

### Phase 4 — live trading, only after a separate explicit decision

Live execution is a separate release gate. Require separate live broker authorization/credentials, clear live-mode indicators, per-account limits, recent step-up authentication, and an operator kill switch. Begin with low limits and manual confirmation for every order. Unattended AI-directed trading is outside the paper milestone. Discretionary/automated execution or serving other users needs a separate broker, compliance, and legal review.

## Architecture sketch

```text
Dashboard login ─┐
                 ├─> authenticated proposal service ─> validation + risk policy ─> durable order intent/outbox
Verified Telegram┘                                                                  │
                                                                                     ├─> paper broker adapter
                                                                                     └─> audit/order ledger + reconciliation
Sunrise event analysis ─> proposal context only; cannot authorize or submit an order
```

Event analysis remains independent of trade state. A signal may create a draft proposal, but only a verified user's confirmation can advance it to an order intent.

## Decisions before implementation

User decisions so far: open signup; multi-user target; India only; paper trading with manual confirmation for the first release. Still choose the launch broker/instruments (e.g. Upstox and NSE equities), and decide if/when to pursue broker onboarding for multi-user live access. Regardless, live mode stays disabled pending legal/broker review and a separate explicit launch decision.

## Sources

- [Upstox Sandbox APIs](https://upstox.com/developer/api-documentation/sandbox/)
- [Upstox sandbox access and test mode](https://upstox.com/developer/api-documentation/build-using-sandbox/)
- [Zerodha Kite Connect sandbox FAQ](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/kite-connect-api-faqs)
- [SEBI September 2025 extension to retail algorithmic-trading implementation](https://www.sebi.gov.in/legal/circulars/sep-2025/extension-of-timeline-for-implementation-of-sebi-circular-dated-february-04-2025-on-safer-participation-of-retail-investors-in-algorithmic-trading-_96979.html)
- [NSE decision-support and algorithmic-trading requirements](https://www.nseindia.com/static/trade/platform-services-non-neat-decision-support-tools-algorithm-trading)
- [NSE retail API standards PDF](https://nsearchives.nseindia.com/content/circulars/INVG67858.pdf)
- [FINRA: risks of auto-trading services](https://www.finra.org/investors/insights/auto-trading)
- [SEC staff guidance on robo-advisers](https://www.sec.gov/investment/2017-02-robo-advisers)
- [AWS Secrets Manager access control](https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_overview.html)
