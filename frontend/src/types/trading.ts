export interface TradingInstrument {
  symbol: string;
  name: string;
  exchange: string;
  sector: string;
  base_price: number;
}

export interface TradingQuote {
  symbol: string;
  name: string;
  price: number;
  currency: string;
  source: string;
  as_of: string;
}

export interface RiskCheck {
  name: string;
  ok: boolean;
  detail: string;
}

export interface TradeProposal {
  id: number;
  event_id: number | null;
  symbol: string;
  name: string;
  side: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT";
  quantity: number;
  limit_price: number | null;
  quote: TradingQuote;
  estimated_notional: number;
  estimated_fee: number;
  checks: RiskCheck[];
  approved: boolean;
  status: string;
  expires_at: string;
  expired: boolean;
  rationale: string | null;
  created_at: string | null;
}

export interface PaperOrder {
  id: number;
  client_order_id: string;
  symbol: string;
  side: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT";
  quantity: number;
  limit_price: number | null;
  status: string;
  filled_quantity: number;
  average_fill_price: number | null;
  quote_price: number | null;
  quote_source: string;
  notional: number | null;
  fee: number;
  realized_pnl: number;
  rejection_reason: string | null;
  created_at: string | null;
  filled_at: string | null;
  cancelled_at: string | null;
}

export interface PaperPosition {
  symbol: string;
  name: string;
  quantity: number;
  average_price: number;
  last_price: number;
  market_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  currency: string;
  quote_source: string;
}

export interface PortfolioPosition extends PaperPosition {
  cost_basis: number;
  unrealized_pnl_pct: number;
  weight_pct: number;
}

export interface PaperPortfolio {
  account: PaperAccount;
  positions: PortfolioPosition[];
  invested: number;
  cash_weight_pct: number;
  total_return_pct: number;
  position_count: number;
  mode: string;
}

export interface TelegramLinkStatus {
  linked: boolean;
  chat: string;
  bot_username: string;
  bot_url: string;
  trading_enabled: boolean;
}

export interface TelegramLinkCode extends TelegramLinkStatus {
  code: string;
  expires_at: string;
  instructions: string;
}

export interface PaperAccount {
  currency: string;
  starting_cash: number;
  cash: number;
  positions_value: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  buying_power: number;
  position_count: number;
  mode: string;
  quote_source: string;
}

export interface ConfirmResult {
  order: PaperOrder;
  account: PaperAccount;
  idempotent: boolean;
}

export interface TradingConfig {
  paper_enabled: boolean;
  frozen: boolean;
  live_enabled: boolean;
  currency: string;
  starting_cash: number;
  order_notional_limit: number;
  position_notional_limit: number;
  gross_exposure_limit: number;
  daily_order_limit: number;
  daily_loss_limit: number;
  order_fee: number;
  proposal_ttl_seconds: number;
  market_hours_enforced: boolean;
  instruments: TradingInstrument[];
  disclaimer: string;
}

export interface AuditEntry {
  id: number;
  action: string;
  entity_type: string;
  entity_id: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
}
