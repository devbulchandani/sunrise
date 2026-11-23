import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useAuth } from "../services/auth";
import { ApiError, getEvent } from "../services/api";
import type { EventDetail } from "../types";
import type {
  PaperAccount,
  PaperOrder,
  PaperPortfolio,
  PortfolioPosition,
  TelegramLinkCode,
  TelegramLinkStatus,
  TradeProposal,
  TradingConfig,
  TradingQuote,
} from "../types/trading";
import {
  cancelPaperOrder,
  confirmProposal,
  createProposal,
  createTelegramLinkCode,
  getPaperAccount,
  getPaperOrders,
  getPaperPortfolio,
  getPaperPositions,
  getTelegramLink,
  getTradingConfig,
  getTradingQuote,
  rejectProposal,
  unlinkTelegram,
} from "../services/trading";
import {
  formatCurrency,
  formatTimestamp,
  signedCurrency,
} from "../lib/format";
import { useNow } from "../hooks/usePolling";
import { cn } from "../lib/cn";
import {
  ApiErrorBanner,
  Button,
  EmptyState,
  Metric,
  PageHeader,
  Panel,
  PanelHeader,
  Pill,
  SectionLabel,
  Skeleton,
  Spinner,
  StatBar,
} from "../components/ui";
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  Clock,
  External,
  Refresh,
  Send,
  Shield,
  SunriseMark,
  TrendingDown,
  TrendingUp,
  Wallet,
  X,
} from "../components/icons";

type Side = "BUY" | "SELL";
type OrderType = "MARKET" | "LIMIT";
type OrderFilter = "ALL" | "FILLED" | "OPEN" | "CANCELLED";

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "The request could not be completed.";
}

/**
 * Older API builds predate GET /trading/portfolio. Rebuild the same shape from
 * the account + positions endpoints so a dashboard deploy can roll out ahead of
 * the backend without blanking the desk.
 */
async function legacyPortfolio(): Promise<PaperPortfolio> {
  const [account, positions] = await Promise.all([
    getPaperAccount(),
    getPaperPositions(),
  ]);
  const invested = positions.reduce(
    (total, row) => total + row.average_price * row.quantity,
    0,
  );
  const rows: PortfolioPosition[] = positions.map((row) => {
    const cost = row.average_price * row.quantity;
    return {
      ...row,
      cost_basis: cost,
      unrealized_pnl_pct: cost > 0 ? (row.unrealized_pnl / cost) * 100 : 0,
      weight_pct:
        account.equity > 0 ? (row.market_value / account.equity) * 100 : 0,
    };
  });
  return {
    account,
    positions: rows,
    invested,
    cash_weight_pct:
      account.equity > 0 ? (account.cash / account.equity) * 100 : 0,
    total_return_pct:
      account.starting_cash > 0
        ? ((account.equity - account.starting_cash) / account.starting_cash) * 100
        : 0,
    position_count: rows.length,
    mode: account.mode,
  };
}

function statusTone(status: string) {
  const value = status.toUpperCase();
  if (value === "FILLED") return "bull" as const;
  if (value === "OPEN") return "amber" as const;
  if (value === "REJECTED") return "bear" as const;
  return "neutral" as const;
}

export default function Trading() {
  const { user, ready, configured, signIn } = useAuth();
  const [params] = useSearchParams();
  const location = useLocation();
  const eventId = params.get("event");
  const [config, setConfig] = useState<TradingConfig | null>(null);
  const [configError, setConfigError] = useState<Error | null>(null);
  const [portfolio, setPortfolio] = useState<PaperPortfolio | null>(null);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [linkedEvent, setLinkedEvent] = useState<EventDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataError, setDataError] = useState<Error | null>(null);

  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<Side>("BUY");
  const [orderType, setOrderType] = useState<OrderType>("MARKET");
  const [quantity, setQuantity] = useState("10");
  const [limitPrice, setLimitPrice] = useState("");
  const [rationale, setRationale] = useState("");
  const [quote, setQuote] = useState<TradingQuote | null>(null);
  const [proposal, setProposal] = useState<TradeProposal | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [busy, setBusy] = useState<"review" | "confirm" | null>(null);
  const [ticketError, setTicketError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [orderFilter, setOrderFilter] = useState<OrderFilter>("ALL");

  useEffect(() => {
    getTradingConfig()
      .then(setConfig)
      .catch((err: Error) => setConfigError(err));
  }, []);

  useEffect(() => {
    if (!config || symbol) return;
    const requested = params.get("symbol")?.toUpperCase();
    const valid = config.instruments.some((item) => item.symbol === requested);
    const preferred =
      config.instruments.find((item) => item.symbol === "RELIANCE") ??
      config.instruments[0];
    setSymbol(valid && requested ? requested : preferred?.symbol ?? "");
  }, [config, params, symbol]);

  useEffect(() => {
    if (!eventId) {
      setLinkedEvent(null);
      return;
    }
    let cancelled = false;
    getEvent(eventId)
      .then((event) => {
        if (!cancelled) setLinkedEvent(event);
      })
      .catch(() => {
        if (!cancelled) setLinkedEvent(null);
      });
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setDataError(null);
    try {
      let nextPortfolio: PaperPortfolio;
      try {
        nextPortfolio = await getPaperPortfolio();
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 404) throw err;
        nextPortfolio = await legacyPortfolio();
      }
      setOrders(await getPaperOrders());
      setPortfolio(nextPortfolio);
    } catch (err) {
      setDataError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, [user]);

  const account = portfolio?.account ?? null;
  const positions = portfolio?.positions ?? [];

  useEffect(() => {
    if (user) void load();
  }, [user, load]);

  useEffect(() => {
    if (loading) return;
    if (location.hash === "#telegram") {
      document.getElementById("telegram")?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [location.hash, loading]);

  useEffect(() => {
    if (!user || !symbol) return;
    let cancelled = false;
    setQuote(null);
    getTradingQuote(symbol)
      .then((next) => {
        if (!cancelled) setQuote(next);
      })
      .catch(() => {
        if (!cancelled) setQuote(null);
      });
    return () => {
      cancelled = true;
    };
  }, [user, symbol]);

  const instrument = useMemo(
    () => config?.instruments.find((item) => item.symbol === symbol) ?? null,
    [config, symbol],
  );
  const position = positions.find((item) => item.symbol === symbol);
  const positionQuantity = position?.quantity ?? 0;
  const quantityNumber = Number(quantity);
  const limitNumber = Number(limitPrice);
  const pricing = orderType === "LIMIT" && limitNumber > 0 ? limitNumber : quote?.price ?? 0;
  const estimatedNotional = pricing * (Number.isFinite(quantityNumber) ? quantityNumber : 0);
  const fee = config?.order_fee ?? 20;

  const filteredOrders = useMemo(
    () =>
      orderFilter === "ALL"
        ? orders
        : orders.filter((order) => order.status === orderFilter),
    [orders, orderFilter],
  );

  const pendingOrders = orders.filter((order) => order.status === "OPEN").length;

  const maxQuantity = () => {
    if (!quote) return;
    if (side === "SELL") {
      setQuantity(String(Math.max(positionQuantity, 0) || 1));
      return;
    }
    const affordable = Math.floor((account?.buying_power ?? 0) / quote.price);
    setQuantity(String(Math.max(Math.min(affordable, 1_000_000), 1)));
  };

  const resetTicket = () => {
    setSide("BUY");
    setOrderType("MARKET");
    setQuantity("10");
    setLimitPrice("");
    setRationale("");
    setTicketError(null);
  };

  const reviewOrder = async () => {
    if (!user || !symbol) return;
    if (!Number.isInteger(quantityNumber) || quantityNumber < 1) {
      setTicketError("Enter a whole number of shares greater than zero.");
      return;
    }
    if (orderType === "LIMIT" && (!Number.isFinite(limitNumber) || limitNumber <= 0)) {
      setTicketError("Enter a positive limit price.");
      return;
    }
    setBusy("review");
    setTicketError(null);
    try {
      const next = await createProposal({
        symbol,
        side,
        order_type: orderType,
        quantity: quantityNumber,
        limit_price: orderType === "LIMIT" ? limitNumber : null,
        event_id: eventId ? Number(eventId) : null,
        rationale: rationale.trim() || null,
      });
      setProposal(next);
      setReviewOpen(true);
    } catch (err) {
      setTicketError(messageOf(err));
    } finally {
      setBusy(null);
    }
  };

  const confirm = async () => {
    if (!proposal) return;
    setBusy("confirm");
    setTicketError(null);
    try {
      const result = await confirmProposal(proposal.id);
      const order = result.order;
      setNotice(
        `${order.side} ${order.filled_quantity || order.quantity} ${order.symbol} — ${
          order.status === "FILLED"
            ? `filled at ${formatCurrency(order.average_fill_price)}`
            : "resting open"
        }. ${formatCurrency(order.fee)} simulated fee booked.`,
      );
      setReviewOpen(false);
      setProposal(null);
      await load();
    } catch (err) {
      setTicketError(messageOf(err));
    } finally {
      setBusy(null);
    }
  };

  const discard = async () => {
    if (!proposal) return;
    setReviewOpen(false);
    void rejectProposal(proposal.id).catch(() => undefined);
    setProposal(null);
  };

  const cancel = async (order: PaperOrder) => {
    setTicketError(null);
    try {
      await cancelPaperOrder(order.id);
      setNotice(`Order #${order.id} cancelled.`);
      await load();
    } catch (err) {
      setTicketError(messageOf(err));
    }
  };

  const sell = (positionRow: PortfolioPosition) => {
    setSide("SELL");
    setSymbol(positionRow.symbol);
    setQuantity(String(positionRow.quantity));
    setOrderType("MARKET");
    document.getElementById("ticket")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (!configured) {
    return (
      <DeskShell>
        <Panel className="mx-auto max-w-xl p-8 text-center">
          <SunriseMark className="mx-auto mb-4 h-7 w-7 text-amber" />
          <h2 className="display text-2xl text-ink">Authentication is not configured.</h2>
          <p className="mt-2 text-sm leading-6 text-ink-dim">
            The paper desk needs Cognito sign-in. Configure the public Cognito
            client IDs and reload.
          </p>
        </Panel>
      </DeskShell>
    );
  }

  if (!ready) {
    return (
      <DeskShell>
        <div className="flex items-center justify-center gap-2 py-24 text-xs text-ink-faint">
          <Spinner /> Checking your session…
        </div>
      </DeskShell>
    );
  }

  if (!user) {
    return (
      <DeskShell>
        <div className="mx-auto max-w-2xl">
          <Panel className="overflow-hidden text-center">
            <div className="relative border-b border-edge/70 bg-dawn px-6 py-10">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-amber/25 bg-amber/[0.08] text-amber">
                <Shield className="h-6 w-6" />
              </div>
              <h2 className="display mt-5 text-3xl text-ink">Sign in to open the paper desk.</h2>
              <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-ink-dim">
                Your paper account, orders, and positions are tied to your verified
                Cognito identity. No brokerage account is connected and no real
                money moves.
              </p>
            </div>
            <div className="p-6">
              <div className="mb-6 grid grid-cols-3 gap-3 text-left">
                <MiniFact label="Mode" value="Paper" />
                <MiniFact label="Universe" value={`${config?.instruments.length ?? "—"} symbols`} />
                <MiniFact
                  label="Opening cash"
                  value={config ? formatCurrency(config.starting_cash) : "—"}
                />
              </div>
              <Button
                variant="primary"
                size="md"
                onClick={() => void signIn("/trading")}
                className="w-full"
              >
                Sign in with Cognito
                <ArrowUpRight className="h-4 w-4" />
              </Button>
              <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                Simulated quotes · manual confirmation · live trading disabled
              </p>
            </div>
          </Panel>
          {configError && <ApiErrorBanner error={configError} />}
        </div>
      </DeskShell>
    );
  }

  if (config && !config.paper_enabled) {
    return (
      <DeskShell>
        <Panel className="mx-auto max-w-xl p-8 text-center">
          <AlertTriangle className="mx-auto mb-4 h-7 w-7 text-amber" />
          <h2 className="display text-2xl text-ink">The paper desk is disabled.</h2>
          <p className="mt-2 text-sm leading-6 text-ink-dim">
            The environment has <code className="font-mono text-amber">PAPER_TRADING_ENABLED=false</code>.
            Live trading is also disabled. Ask the operator to enable paper mode.
          </p>
        </Panel>
      </DeskShell>
    );
  }

  return (
    <DeskShell>
      <PageHeader
        eyebrow="Paper desk · 04"
        title={
          <>
            Trade the signal,
            <br />
            <span className="italic text-amber">not the money.</span>
          </>
        }
        description="A simulated brokerage desk on top of Sunrise signals. Prices are simulated, orders are filled by our own ledger, and every trade needs your explicit confirmation."
        meta={
          <>
            <Pill tone="amber">Paper only</Pill>
            <Pill tone="bull">
              <Check className="h-3 w-3" /> Live trading disabled
            </Pill>
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
              Signed in as {String(user.profile.email || "you")}
            </span>
          </>
        }
        actions={
          <Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading}>
            {loading ? <Spinner className="h-3.5 w-3.5" /> : <Refresh className="h-3.5 w-3.5" />}
            Refresh
          </Button>
        }
      />

      <ApiErrorBanner error={dataError} onRetry={() => void load()} />
      {configError && <ApiErrorBanner error={configError} />}

      {notice && (
        <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-bull/25 bg-bull/[0.06] px-4 py-3">
          <Check className="h-4 w-4 text-bull" />
          <p className="text-xs text-bull">{notice}</p>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="ml-auto cursor-pointer text-xs text-bull/70 hover:text-bull"
          >
            Dismiss
          </button>
        </div>
      )}

      {linkedEvent && (
        <Panel className="mb-6 overflow-hidden border-amber/20">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4">
            <span className="label text-amber">Linked signal</span>
            <Link
              to={`/events/${linkedEvent.id}`}
              className="min-w-0 flex-1 truncate text-sm text-ink transition-colors hover:text-amber"
            >
              {linkedEvent.headline}
            </Link>
            <Pill
              tone={
                (linkedEvent.urgency ?? 0) >= 81
                  ? "bear"
                  : (linkedEvent.urgency ?? 0) >= 61
                    ? "amber"
                    : "neutral"
              }
            >
              {Math.round(linkedEvent.urgency ?? 0)} urgency
            </Pill>
            <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
              A signal can create a proposal; only your confirmation submits it.
            </span>
          </div>
        </Panel>
      )}

      {loading && !account ? (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          <Skeleton className="h-[520px] xl:col-span-8" />
          <Skeleton className="h-[420px] xl:col-span-4" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          <div className="space-y-6 xl:col-span-8">
            <OrderTicket
              config={config}
              account={account}
              quote={quote}
              instrument={instrument}
              symbol={symbol}
              onSymbol={setSymbol}
              side={side}
              onSide={setSide}
              orderType={orderType}
              onOrderType={setOrderType}
              quantity={quantity}
              onQuantity={setQuantity}
              limitPrice={limitPrice}
              onLimitPrice={setLimitPrice}
              rationale={rationale}
              onRationale={setRationale}
              positionQuantity={positionQuantity}
              estimatedNotional={estimatedNotional}
              fee={fee}
              onMax={maxQuantity}
              onReview={() => void reviewOrder()}
              onReset={resetTicket}
              busy={busy === "review"}
              error={ticketError}
            />

            <HoldingsPanel positions={positions} onSell={sell} />

            <OrdersPanel
              orders={filteredOrders}
              filter={orderFilter}
              onFilter={setOrderFilter}
              pending={pendingOrders}
              onCancel={(order) => void cancel(order)}
            />
          </div>

          <aside className="space-y-5 xl:col-span-4">
            <PortfolioPanel portfolio={portfolio} />
            <TelegramPanel />
            <LimitsPanel config={config} />
            <SafetyPanel config={config} />
          </aside>
        </div>
      )}

      {reviewOpen && proposal && (
        <ReviewModal
          proposal={proposal}
          busy={busy === "confirm"}
          error={ticketError}
          onConfirm={() => void confirm()}
          onDiscard={() => void discard()}
        />
      )}
    </DeskShell>
  );
}

function DeskShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-[1600px] px-5 pb-16 pt-6">
      {children}
    </div>
  );
}

function MiniFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-edge bg-surface-2/40 px-3 py-2.5">
      <p className="label mb-1">{label}</p>
      <p className="num text-sm text-ink">{value}</p>
    </div>
  );
}

function OrderTicket({
  config,
  account,
  quote,
  instrument,
  symbol,
  onSymbol,
  side,
  onSide,
  orderType,
  onOrderType,
  quantity,
  onQuantity,
  limitPrice,
  onLimitPrice,
  rationale,
  onRationale,
  positionQuantity,
  estimatedNotional,
  fee,
  onMax,
  onReview,
  onReset,
  busy,
  error,
}: {
  config: TradingConfig | null;
  account: PaperAccount | null;
  quote: TradingQuote | null;
  instrument: TradingConfig["instruments"][number] | null;
  symbol: string;
  onSymbol: (value: string) => void;
  side: Side;
  onSide: (value: Side) => void;
  orderType: OrderType;
  onOrderType: (value: OrderType) => void;
  quantity: string;
  onQuantity: (value: string) => void;
  limitPrice: string;
  onLimitPrice: (value: string) => void;
  rationale: string;
  onRationale: (value: string) => void;
  positionQuantity: number;
  estimatedNotional: number;
  fee: number;
  onMax: () => void;
  onReview: () => void;
  onReset: () => void;
  busy: boolean;
  error: string | null;
}) {
  return (
    <Panel id="ticket" className="overflow-hidden">
      <PanelHeader
        eyebrow="Order ticket"
        title="Review before you confirm"
        action={<Pill tone="neutral">Simulated fills</Pill>}
      />
      <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-5">
          <div>
            <label htmlFor="symbol" className="label mb-2 block">
              Instrument · NSE paper universe
            </label>
            <select
              id="symbol"
              value={symbol}
              onChange={(event) => onSymbol(event.target.value)}
              className="w-full cursor-pointer rounded-lg border border-edge bg-surface-2 px-3 py-2.5 text-sm text-ink outline-none focus:border-amber/60"
            >
              {(config?.instruments ?? []).map((item) => (
                <option key={item.symbol} value={item.symbol}>
                  {item.symbol} — {item.name}
                </option>
              ))}
            </select>
            <p className="mt-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
              {instrument ? `${instrument.exchange} · ${instrument.sector}` : "Select an instrument"}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="label mb-2 block">Side</span>
              <div className="grid grid-cols-2 gap-1 rounded-lg border border-edge bg-surface-2/40 p-1">
                <button
                  type="button"
                  aria-pressed={side === "BUY"}
                  onClick={() => onSide("BUY")}
                  className={cn(
                    "flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-md text-xs font-medium transition-colors",
                    side === "BUY"
                      ? "bg-bull/15 text-bull"
                      : "text-ink-faint hover:text-ink",
                  )}
                >
                  <TrendingUp className="h-3.5 w-3.5" /> Buy
                </button>
                <button
                  type="button"
                  aria-pressed={side === "SELL"}
                  onClick={() => onSide("SELL")}
                  className={cn(
                    "flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-md text-xs font-medium transition-colors",
                    side === "SELL"
                      ? "bg-bear/15 text-bear"
                      : "text-ink-faint hover:text-ink",
                  )}
                >
                  <TrendingDown className="h-3.5 w-3.5" /> Sell
                </button>
              </div>
            </div>
            <div>
              <span className="label mb-2 block">Order type</span>
              <div className="grid grid-cols-2 gap-1 rounded-lg border border-edge bg-surface-2/40 p-1">
                {(["MARKET", "LIMIT"] as OrderType[]).map((value) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={orderType === value}
                    onClick={() => onOrderType(value)}
                    className={cn(
                      "h-9 cursor-pointer rounded-md font-mono text-[10px] uppercase tracking-[0.1em] transition-colors",
                      orderType === value
                        ? "bg-surface-3 text-ink"
                        : "text-ink-faint hover:text-ink",
                    )}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="quantity" className="label mb-2 block">
                Quantity
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="quantity"
                  type="number"
                  min={1}
                  step={1}
                  value={quantity}
                  onChange={(event) => onQuantity(event.target.value)}
                  className="h-10 min-w-0 flex-1 rounded-lg border border-edge bg-surface-2 px-3 font-mono text-sm text-ink outline-none focus:border-amber/60"
                />
                <button
                  type="button"
                  onClick={onMax}
                  className="h-10 cursor-pointer rounded-lg border border-edge px-2.5 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim transition-colors hover:border-edge-bright hover:text-ink"
                  title={side === "SELL" ? "Sell the whole position" : "Use available buying power"}
                >
                  Max
                </button>
              </div>
              <p className="mt-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                {side === "SELL"
                  ? `You hold ${positionQuantity} ${symbol || "shares"}`
                  : `Buying power ${formatCurrency(account?.buying_power ?? 0)}`}
              </p>
            </div>
            <div>
              <label htmlFor="limit" className="label mb-2 block">
                Limit price {orderType === "MARKET" ? "(not used)" : ""}
              </label>
              <input
                id="limit"
                type="number"
                min={0}
                step="0.05"
                value={limitPrice}
                onChange={(event) => onLimitPrice(event.target.value)}
                disabled={orderType === "MARKET"}
                placeholder={quote ? quote.price.toFixed(2) : "0.00"}
                className="h-10 w-full rounded-lg border border-edge bg-surface-2 px-3 font-mono text-sm text-ink outline-none placeholder:text-ink-faint focus:border-amber/60 disabled:opacity-40"
              />
              <p className="mt-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                ±20% band · simulated quote
              </p>
            </div>
          </div>

          <div>
            <label htmlFor="rationale" className="label mb-2 block">
              Thesis (optional · stored in the audit trail)
            </label>
            <textarea
              id="rationale"
              value={rationale}
              onChange={(event) => onRationale(event.target.value)}
              rows={2}
              maxLength={1000}
              placeholder="Why this trade? Reference the signal if you came from one."
              className="w-full resize-none rounded-lg border border-edge bg-surface-2 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-amber/60"
            />
          </div>

          {error && (
            <p className="flex items-start gap-2 rounded-lg border border-bear/25 bg-bear/[0.06] px-3 py-2.5 text-xs leading-5 text-bear">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {error}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              onClick={onReview}
              disabled={busy || !quote}
              className="flex-1"
            >
              {busy ? <Spinner className="h-4 w-4" /> : <Shield className="h-4 w-4" />}
              Review order
            </Button>
            <Button variant="ghost" onClick={onReset} disabled={busy}>
              Reset
            </Button>
          </div>
          <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
            No order is sent until you confirm on the next screen.
          </p>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-edge bg-base/50 p-4">
            <div className="flex items-start justify-between">
              <div>
                <p className="label">Simulated quote</p>
                <p className="num mt-2 text-2xl font-semibold text-ink">
                  {quote ? formatCurrency(quote.price) : "—"}
                </p>
              </div>
              <Pill tone="info">Simulated</Pill>
            </div>
            <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
              {quote
                ? `${quote.symbol} · ${new Date(quote.as_of).toLocaleTimeString("en-IN", { hour12: false })} IST`
                : "Fetching a quote"}
            </p>
          </div>

          <div className="rounded-xl border border-edge bg-surface-2/30 p-4">
            <Line label="Estimated notional" value={formatCurrency(estimatedNotional)} />
            <Line label="Simulated fee" value={formatCurrency(fee)} />
            <Line label="Buying power" value={formatCurrency(account?.buying_power ?? 0)} />
            <Line
              label="After order"
              value={
                side === "BUY"
                  ? formatCurrency(Math.max((account?.buying_power ?? 0) - estimatedNotional - fee, 0))
                  : formatCurrency((account?.buying_power ?? 0) + estimatedNotional - fee)
              }
            />
            <div className="mt-3 border-t border-edge/70 pt-3">
              <div className="flex items-center justify-between">
                <span className="label">Direction</span>
                <span className={cn("font-mono text-[10px] uppercase", side === "BUY" ? "text-bull" : "text-bear")}>
                  {side}
                </span>
              </div>
              <StatBar
                value={
                  estimatedNotional > 0
                    ? Math.min((estimatedNotional / Math.max(account?.equity ?? 1, 1)) * 100, 100)
                    : 0
                }
                tone={side === "BUY" ? "bull" : "bear"}
                height={3}
                className="mt-2"
              />
              <p className="mt-1.5 font-mono text-[9px] text-ink-faint">
                {estimatedNotional > 0
                  ? `${((estimatedNotional / Math.max(account?.equity ?? 1, 1)) * 100).toFixed(1)}% of equity`
                  : "Enter a quantity"}
              </p>
            </div>
          </div>

          <p className="text-[11px] leading-5 text-ink-faint">
            This desk uses simulated prices and a Sunrise-owned ledger. It never
            contacts a broker and cannot place a real order.
          </p>
        </div>
      </div>
    </Panel>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="label">{label}</span>
      <span className="num text-xs text-ink-dim">{value}</span>
    </div>
  );
}

function PortfolioPanel({ portfolio }: { portfolio: PaperPortfolio | null }) {
  const account = portfolio?.account;
  const positions = portfolio?.positions ?? [];
  const rawReturnPct = portfolio?.total_return_pct ?? 0;
  // A sub-basis-point move should not render as a red "-0.00%".
  const returnPct = Math.abs(rawReturnPct) < 0.005 ? 0 : rawReturnPct;
  const allocation = [
    {
      key: "cash",
      label: "Cash",
      pct: portfolio?.cash_weight_pct ?? 0,
      className: "bg-ink-faint/35",
    },
    ...positions.slice(0, 8).map((row, index) => ({
      key: row.symbol,
      label: row.symbol,
      pct: row.weight_pct,
      className: [
        "bg-amber",
        "bg-amber/80",
        "bg-amber/60",
        "bg-amber/45",
        "bg-amber/30",
        "bg-bull/70",
        "bg-bull/45",
        "bg-ink-dim/60",
      ][index] ?? "bg-ink-dim/40",
    })),
  ];
  return (
    <Panel className="overflow-hidden">
      <PanelHeader
        eyebrow="Portfolio"
        title="Paper book"
        action={
          <Pill tone={returnPct >= 0 ? "bull" : "bear"}>
            {returnPct >= 0 ? "+" : ""}
            {returnPct.toFixed(2)}%
          </Pill>
        }
      />
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="label mb-2">Equity</p>
            <p className="num text-3xl font-semibold text-ink">
              {formatCurrency(account?.equity ?? 0)}
            </p>
            <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
              Since {formatCurrency(account?.starting_cash ?? 0)} opening cash
            </p>
          </div>
          <Wallet className="mt-1 h-4 w-4 shrink-0 text-amber" />
        </div>

        <div className="mt-4">
          <div
            className="flex h-2 overflow-hidden rounded-full bg-surface-2"
            role="img"
            aria-label="Portfolio allocation"
          >
            {allocation.map((slice) =>
              slice.pct > 0 ? (
                <span
                  key={slice.key}
                  className={slice.className}
                  style={{ width: `${Math.max(slice.pct, 0.5)}%` }}
                  title={`${slice.label} ${slice.pct.toFixed(1)}%`}
                />
              ) : null,
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-faint">
            {allocation.slice(0, 5).map((slice) => (
              <span key={slice.key} className="inline-flex items-center gap-1">
                <span className={cn("h-1.5 w-1.5 rounded-sm", slice.className)} />
                {slice.label} {slice.pct.toFixed(1)}%
              </span>
            ))}
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4">
          <Metric label="Cash" value={formatCurrency(account?.cash ?? 0)} />
          <Metric label="Invested" value={formatCurrency(portfolio?.invested ?? 0)} />
          <Metric label="Holdings" value={formatCurrency(account?.positions_value ?? 0)} />
          <Metric label="Stocks held" value={account?.position_count ?? 0} />
          <Metric
            label="Unrealised"
            value={signedCurrency(account?.unrealized_pnl ?? 0)}
            accent={(account?.unrealized_pnl ?? 0) >= 0 ? "text-bull" : "text-bear"}
          />
          <Metric
            label="Realised"
            value={signedCurrency(account?.realized_pnl ?? 0)}
            accent={(account?.realized_pnl ?? 0) >= 0 ? "text-bull" : "text-bear"}
          />
        </div>
      </div>
    </Panel>
  );
}

function TelegramPanel() {
  const { user } = useAuth();
  const [status, setStatus] = useState<TelegramLinkStatus | null>(null);
  const [code, setCode] = useState<TelegramLinkCode | null>(null);
  const [busy, setBusy] = useState<"code" | "unlink" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [available, setAvailable] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    getTelegramLink()
      .then((next) => {
        if (!cancelled) setStatus(next);
      })
      .catch((err) => {
        if (cancelled) return;
        // A dashboard-first rollout can briefly run against an API without the
        // Telegram bridge; show a quiet note instead of an error banner.
        if (err instanceof ApiError && err.status === 404) setAvailable(false);
        else setError(messageOf(err));
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const generate = async () => {
    setBusy("code");
    setError(null);
    setCopied(false);
    try {
      const next = await createTelegramLinkCode();
      setCode(next);
      setStatus(next);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(null);
    }
  };

  const disconnect = async () => {
    setBusy("unlink");
    setError(null);
    try {
      const next = await unlinkTelegram();
      setStatus(next);
      setCode(null);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(null);
    }
  };

  const copy = async () => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(`/link ${code.code}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const botName = status?.bot_username || "sunrisescraperbot";
  const botUrl = status?.bot_url || `https://t.me/${botName}`;

  if (!available) {
    return (
      <Panel id="telegram" className="overflow-hidden">
        <PanelHeader
          eyebrow="Chat desk"
          title="Trade from Telegram"
          action={<Send className="h-4 w-4 text-ink-faint" />}
        />
        <p className="p-5 text-[11px] leading-5 text-ink-faint">
          The Telegram trading bridge is not available on this API build yet.
          Alerts keep flowing in the meantime.
        </p>
      </Panel>
    );
  }

  return (
    <Panel id="telegram" className="overflow-hidden">
      <PanelHeader
        eyebrow="Chat desk"
        title="Trade from Telegram"
        action={<Send className="h-4 w-4 text-amber" />}
      />
      <div className="space-y-4 p-5">
        {status?.linked ? (
          <Pill tone="bull">
            <Check className="h-3 w-3" /> Linked · {status.chat}
          </Pill>
        ) : (
          <Pill tone="neutral">Not linked</Pill>
        )}

        <p className="text-[11px] leading-5 text-ink-dim">
          Impact alerts in Telegram carry Buy and Sell buttons for stocks in the
          paper universe. Tap one, reply with a share quantity or ₹ amount, then
          confirm the review. Every fill is simulated.
        </p>

        {status && !status.trading_enabled && (
          <p className="rounded-lg border border-amber/25 bg-amber/[0.06] px-3 py-2 text-[10px] leading-5 text-amber">
            Telegram trading is paused by the operator. Linking still works and
            alerts keep flowing.
          </p>
        )}

        {error && (
          <p className="flex items-start gap-2 rounded-lg border border-bear/25 bg-bear/[0.06] px-3 py-2.5 text-[11px] leading-5 text-bear">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {error}
          </p>
        )}

        {status?.linked ? (
          <div className="flex flex-wrap gap-2">
            <a
              href={botUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-edge bg-surface-2/50 px-3 text-xs text-ink-dim transition-colors hover:border-edge-bright hover:text-ink"
            >
              Open @{botName}
              <External className="h-3 w-3" />
            </a>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void disconnect()}
              disabled={busy !== null}
            >
              {busy === "unlink" ? <Spinner className="h-3.5 w-3.5" /> : null}
              Disconnect
            </Button>
          </div>
        ) : (
          <>
            {code && (
              <div className="rounded-xl border border-amber/25 bg-amber/[0.06] p-3">
                <p className="label mb-2">Send this to @{botName}</p>
                <button
                  type="button"
                  onClick={() => void copy()}
                  className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg border border-amber/30 bg-base/60 px-3 py-2.5 text-left"
                  title="Copy /link code"
                >
                  <span className="select-all font-mono text-sm tracking-[0.18em] text-amber">
                    /link {code.code}
                  </span>
                  <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                    {copied ? "Copied" : "Copy"}
                  </span>
                </button>
                <p className="mt-2 text-[10px] leading-5 text-ink-faint">
                  Single-use · expires {new Date(code.expires_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })} IST
                </p>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                size="sm"
                onClick={() => void generate()}
                disabled={busy !== null}
              >
                {busy === "code" ? <Spinner className="h-3.5 w-3.5" /> : <Send className="h-3.5 w-3.5" />}
                {code ? "New link code" : "Generate link code"}
              </Button>
              <a
                href={botUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-edge px-3 text-xs text-ink-dim transition-colors hover:border-edge-bright hover:text-ink"
              >
                Open @{botName}
                <External className="h-3 w-3" />
              </a>
            </div>
            <p className="font-mono text-[9px] uppercase leading-4 tracking-[0.08em] text-ink-faint">
              The code binds this Telegram chat to your signed-in Sunrise account.
              One chat, one account. Sizes are typed in chat; symbols and sides
              only come from the alert buttons.
            </p>
          </>
        )}
      </div>
    </Panel>
  );
}

function LimitsPanel({ config }: { config: TradingConfig | null }) {
  return (
    <Panel className="overflow-hidden">
      <PanelHeader eyebrow="Risk" title="Per-order limits" action={<Shield className="h-4 w-4 text-ink-faint" />} />
      <div className="divide-y divide-edge/60">
        {[
          ["Max order notional", formatCurrency(config?.order_notional_limit ?? 0)],
          ["Max position value", formatCurrency(config?.position_notional_limit ?? 0)],
          ["Gross exposure cap", formatCurrency(config?.gross_exposure_limit ?? 0)],
          ["Daily orders", `${config?.daily_order_limit ?? "—"}`],
          ["Daily realised loss", formatCurrency(config?.daily_loss_limit ?? 0)],
          ["Proposal expiry", `${Math.round((config?.proposal_ttl_seconds ?? 0) / 60)} min`],
        ].map(([label, value]) => (
          <div key={label} className="flex items-center justify-between px-5 py-2.5">
            <span className="text-[11px] text-ink-faint">{label}</span>
            <span className="num text-[10px] text-ink-dim">{value}</span>
          </div>
        ))}
      </div>
      <div className="border-t border-edge/70 px-5 py-3 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
        {config?.market_hours_enforced ? "NSE market hours enforced" : "Market hours not enforced"}
      </div>
    </Panel>
  );
}

function SafetyPanel({ config }: { config: TradingConfig | null }) {
  return (
    <Panel className="overflow-hidden">
      <PanelHeader eyebrow="Guardrails" title="Read before trading" />
      <div className="space-y-3 p-5">
        <SafetyRow icon={<Shield className="h-3.5 w-3.5 text-amber" />} text="Every order needs an explicit confirmation. Nothing is auto-executed from an LLM signal." />
        <SafetyRow icon={<AlertTriangle className="h-3.5 w-3.5 text-amber" />} text="Prices are simulated and may drift. Fills are paper ledger entries, not market executions." />
        <SafetyRow icon={<Check className="h-3.5 w-3.5 text-bull" />} text="Live broker execution remains disabled. No broker credentials are stored or used." />
        <p className="border-t border-edge/70 pt-3 text-[10px] leading-5 text-ink-faint">
          {config?.disclaimer}
        </p>
      </div>
    </Panel>
  );
}

function SafetyRow({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex gap-2.5">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <p className="text-[11px] leading-5 text-ink-dim">{text}</p>
    </div>
  );
}

function HoldingsPanel({
  positions,
  onSell,
}: {
  positions: PortfolioPosition[];
  onSell: (position: PortfolioPosition) => void;
}) {
  const holdingsValue = positions.reduce((total, row) => total + row.market_value, 0);
  const holdingsPnl = positions.reduce((total, row) => total + row.unrealized_pnl, 0);
  return (
    <Panel className="overflow-hidden">
      <PanelHeader
        eyebrow="Holdings"
        title="Every stock you own"
        action={<Pill tone="neutral">{positions.length}</Pill>}
      />
      {positions.length === 0 ? (
        <div className="p-5">
          <EmptyState
            icon={<TrendingUp className="h-4 w-4" />}
            title="No holdings yet."
            hint="Review a paper order to open your first position. Cash stays in the account until you do."
          />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] border-collapse">
            <thead>
              <tr className="border-b border-edge/70">
                {["Instrument", "Qty", "Avg cost", "Last", "Value", "Weight", "Unrealised", ""].map((heading) => (
                  <th key={heading} className="px-4 py-3 text-left font-mono text-[9px] font-medium uppercase tracking-[0.12em] text-ink-faint">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => (
                <tr key={position.symbol} className="border-b border-edge/50 last:border-b-0">
                  <td className="px-4 py-3">
                    <p className="num text-xs text-ink">{position.symbol}</p>
                    <p className="truncate text-[10px] text-ink-faint">{position.name}</p>
                  </td>
                  <td className="num px-4 py-3 text-xs text-ink-dim">{position.quantity}</td>
                  <td className="num px-4 py-3 text-xs text-ink-dim">{formatCurrency(position.average_price)}</td>
                  <td className="num px-4 py-3 text-xs text-ink-dim">{formatCurrency(position.last_price)}</td>
                  <td className="num px-4 py-3 text-xs text-ink-dim">{formatCurrency(position.market_value)}</td>
                  <td className="px-4 py-3">
                    <span className="num text-xs text-ink-dim">{position.weight_pct.toFixed(1)}%</span>
                    <span className="mt-1 block h-1 w-14 overflow-hidden rounded-full bg-surface-2">
                      <span
                        className="block h-full bg-amber"
                        style={{ width: `${Math.min(position.weight_pct, 100)}%` }}
                      />
                    </span>
                  </td>
                  <td className={cn("num px-4 py-3 text-xs", position.unrealized_pnl >= 0 ? "text-bull" : "text-bear")}>
                    {signedCurrency(position.unrealized_pnl)}
                    <span className="mt-0.5 block font-mono text-[9px] text-ink-faint">
                      {position.unrealized_pnl_pct >= 0 ? "+" : ""}
                      {position.unrealized_pnl_pct.toFixed(2)}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button size="sm" variant="ghost" onClick={() => onSell(position)}>
                      Sell
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-edge/70 bg-surface-2/30">
                <td colSpan={4} className="px-4 py-3 text-[10px] uppercase tracking-[0.1em] text-ink-faint">
                  {positions.length} {positions.length === 1 ? "holding" : "holdings"} · simulated
                </td>
                <td className="num px-4 py-3 text-xs text-ink">{formatCurrency(holdingsValue)}</td>
                <td className="num px-4 py-3 text-xs text-ink-faint">100%</td>
                <td className={cn("num px-4 py-3 text-xs", holdingsPnl >= 0 ? "text-bull" : "text-bear")}>
                  {signedCurrency(holdingsPnl)}
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </Panel>
  );
}

function OrdersPanel({
  orders,
  filter,
  onFilter,
  pending,
  onCancel,
}: {
  orders: PaperOrder[];
  filter: OrderFilter;
  onFilter: (filter: OrderFilter) => void;
  pending: number;
  onCancel: (order: PaperOrder) => void;
}) {
  return (
    <Panel className="overflow-hidden">
      <PanelHeader
        eyebrow="Ledger"
        title="Orders"
        action={
          <div className="flex items-center gap-2">
            {pending > 0 && <Pill tone="amber">{pending} open</Pill>}
            <div className="flex items-center gap-1 rounded-lg border border-edge bg-surface-2/40 p-1">
              {(["ALL", "FILLED", "OPEN", "CANCELLED"] as OrderFilter[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => onFilter(value)}
                  className={cn(
                    "cursor-pointer rounded-md px-2 py-1 font-mono text-[9px] uppercase tracking-[0.1em] transition-colors",
                    filter === value ? "bg-surface-3 text-ink" : "text-ink-faint hover:text-ink",
                  )}
                >
                  {value === "ALL" ? "All" : value.toLowerCase()}
                </button>
              ))}
            </div>
          </div>
        }
      />
      {orders.length === 0 ? (
        <div className="p-5">
          <EmptyState
            icon={<Clock className="h-4 w-4" />}
            title="No orders in this view."
            hint="Submitted paper orders, fills, and cancellations appear here."
          />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse">
            <thead>
              <tr className="border-b border-edge/70">
                {["Time", "Instrument", "Side", "Type", "Qty", "Status", "Fill", "Value", ""].map((heading) => (
                  <th key={heading} className="px-5 py-3 text-left font-mono text-[9px] font-medium uppercase tracking-[0.12em] text-ink-faint">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id} className="border-b border-edge/50 last:border-b-0">
                  <td className="px-4 py-3 font-mono text-[10px] text-ink-faint">
                    {formatTimestamp(order.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <p className="num text-xs text-ink">{order.symbol}</p>
                    <p className="font-mono text-[9px] text-ink-faint">#{order.id}</p>
                  </td>
                  <td className={cn("px-4 py-3 font-mono text-[10px] uppercase", order.side === "BUY" ? "text-bull" : "text-bear")}>
                    {order.side}
                  </td>
                  <td className="px-4 py-3 font-mono text-[10px] text-ink-dim">
                    {order.order_type}
                    {order.limit_price != null ? ` ${formatCurrency(order.limit_price)}` : ""}
                  </td>
                  <td className="num px-4 py-3 text-xs text-ink-dim">{order.quantity}</td>
                  <td className="px-4 py-3">
                    <Pill tone={statusTone(order.status)}>{order.status}</Pill>
                  </td>
                  <td className="px-4 py-3 font-mono text-[10px] text-ink-dim">
                    {order.average_fill_price != null ? formatCurrency(order.average_fill_price) : "—"}
                  </td>
                  <td className="px-4 py-3 font-mono text-[10px] text-ink-dim">
                    {order.notional != null ? formatCurrency(order.notional) : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {order.status === "OPEN" ? (
                      <Button size="sm" variant="ghost" onClick={() => onCancel(order)}>
                        Cancel
                      </Button>
                    ) : (
                      <span className="text-ink-faint">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function ReviewModal({
  proposal,
  busy,
  error,
  onConfirm,
  onDiscard,
}: {
  proposal: TradeProposal;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onDiscard: () => void;
}) {
  const now = useNow(1_000);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onDiscard();
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onDiscard]);

  const expiresMs = new Date(proposal.expires_at).getTime() - now;
  const secondsLeft = Math.max(0, Math.floor(expiresMs / 1000));
  const expired = secondsLeft === 0 || proposal.expired;
  const approved = proposal.approved && !expired;
  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;

  return createPortal(
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4" role="presentation">
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={onDiscard} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Review paper order"
        className="relative flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-edge bg-surface shadow-2xl animate-rise"
      >
        <div className="flex items-start justify-between gap-4 border-b border-edge px-5 py-4">
          <div>
            <p className="label-amber mb-1">Manual confirmation</p>
            <h2 className="display text-2xl text-ink">Review paper order</h2>
          </div>
          <div className="flex items-center gap-2">
            <Pill tone={approved ? "bull" : "bear"}>{approved ? "Ready" : "Blocked"}</Pill>
            <button
              type="button"
              onClick={onDiscard}
              aria-label="Close review"
              className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border border-edge text-ink-faint transition-colors hover:border-edge-bright hover:text-ink"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          <div className="rounded-xl border border-edge bg-base/50 p-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="label mb-1">{proposal.side} · {proposal.order_type}</p>
                <p className="display text-3xl text-ink">{proposal.symbol}</p>
                <p className="mt-1 text-xs text-ink-faint">{proposal.name}</p>
              </div>
              <div className="text-right">
                <p className="num text-2xl font-semibold text-ink">
                  {formatCurrency(proposal.quote.price)}
                </p>
                <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                  simulated quote
                </p>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Mini label="Quantity" value={String(proposal.quantity)} />
              <Mini label="Notional" value={formatCurrency(proposal.estimated_notional)} />
              <Mini label="Fee" value={formatCurrency(proposal.estimated_fee)} />
              <Mini
                label="Expires"
                value={expired ? "Expired" : `${minutes}:${String(seconds).padStart(2, "0")}`}
              />
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="label">Risk checks</p>
              <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                {proposal.checks.filter((check) => check.ok).length}/{proposal.checks.length} passing
              </span>
            </div>
            <ul className="divide-y divide-edge/60 rounded-xl border border-edge">
              {proposal.checks.map((check) => (
                <li key={check.name} className="flex items-start gap-3 px-4 py-2.5">
                  <span className={cn("mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border", check.ok ? "border-bull/30 bg-bull/10 text-bull" : "border-bear/30 bg-bear/10 text-bear")}>
                    {check.ok ? <Check className="h-2.5 w-2.5" /> : <X className="h-2.5 w-2.5" />}
                  </span>
                  <div className="min-w-0">
                    <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
                      {check.name.replace(/_/g, " ")}
                    </p>
                    <p className="mt-0.5 text-[11px] leading-4 text-ink-faint">{check.detail}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {proposal.rationale && (
            <div className="rounded-xl border border-edge bg-surface-2/30 p-3">
              <p className="label mb-1">Your thesis</p>
              <p className="text-xs leading-5 text-ink-dim">{proposal.rationale}</p>
            </div>
          )}

        </div>

        <footer className="flex-none border-t border-edge bg-surface p-4">
          {error && (
            <p className="mb-3 flex items-start gap-2 rounded-lg border border-bear/25 bg-bear/[0.06] px-3 py-2.5 text-xs leading-5 text-bear">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {error}
            </p>
          )}
          <p className="mb-3 font-mono text-[9px] uppercase leading-4 tracking-[0.08em] text-amber/80">
            Paper simulator · no real order will be placed · confirm only if this is the exposure you intend
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={onConfirm} disabled={!approved || busy} className="flex-1">
              {busy ? <Spinner className="h-4 w-4" /> : <Check className="h-4 w-4" />}
              Confirm paper order
            </Button>
            <Button variant="ghost" onClick={onDiscard} disabled={busy}>
              Discard
            </Button>
          </div>
        </footer>
      </div>
    </div>,
    document.body,
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="label mb-1">{label}</p>
      <p className="num text-xs text-ink">{value}</p>
    </div>
  );
}
