# Security

## Reporting

Email **devbulchandani876@gmail.com** for security issues. Please do not open a
public issue for a vulnerability or leaked credential.

## Credential history

An EC2 deploy key was committed to this repository in early history. The
matching key pair has been deleted from AWS, the live instance has no key pair
and no SSH ingress (Systems Manager only), and the file was removed from git
history. GitHub may continue to serve the old blob by commit SHA until support
purges cached views — request a sensitive-data purge via
<https://support.github.com/contact/private-information>. Do not reuse that key.

## Paper trading

- The paper desk is a Sunrise-owned simulator: **no broker is contacted**, no
  broker credentials exist, and quotes are generated locally and labelled
  `simulated`.
- Live execution is fail-closed with `TRADING_ENABLED=false`; the paper desk has
  its own `PAPER_TRADING_ENABLED` and `PAPER_TRADING_FROZEN` kill switches.
- Every order requires an authenticated Cognito session and an explicit
  confirmation after a server-side risk report.
- Proposals, confirmations, fills, rejections, and cancellations are recorded in
  `audit_events`; accounts and positions are isolated by Cognito subject.
- Model output can pre-fill a proposal but can never construct, authorize, or
  submit an order payload.

## Runtime posture

- Secrets are stored in AWS Secrets Manager (`sunrise/production/app-env`) and
  materialized into the instance's `.env` at deploy time; they are never
  committed or baked into images.
- The dashboard never receives an admin secret. Operational actions use a
  Cognito session whose email is listed in `ADMIN_EMAILS`, or `X-Admin-Token`
  from an ops shell.
- Caddy terminates TLS on 80/443. The API binds to `127.0.0.1:8000`; only 80/443
  are reachable from the internet.
- `TRADING_ENABLED` is fail-closed and no broker is connected.
