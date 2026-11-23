import { request } from "./api";
import type {
  AuditEntry,
  ConfirmResult,
  PaperAccount,
  PaperOrder,
  PaperPosition,
  TradeProposal,
  TradingConfig,
  TradingQuote,
} from "../types/trading";

export function getTradingConfig(): Promise<TradingConfig> {
  return request<TradingConfig>("/trading/config");
}

export function getPaperAccount(): Promise<PaperAccount> {
  return request<PaperAccount>("/trading/account");
}

export function getPaperPositions(): Promise<PaperPosition[]> {
  return request<PaperPosition[]>("/trading/positions");
}

export function getPaperOrders(): Promise<PaperOrder[]> {
  return request<PaperOrder[]>("/trading/orders");
}

export function getPaperAudit(): Promise<AuditEntry[]> {
  return request<AuditEntry[]>("/trading/audit");
}

export function getTradingQuote(symbol: string): Promise<TradingQuote> {
  return request<TradingQuote>(`/trading/quote/${encodeURIComponent(symbol)}`);
}

export interface ProposalInput {
  symbol: string;
  side: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT";
  quantity: number;
  limit_price?: number | null;
  event_id?: number | null;
  rationale?: string | null;
}

export function createProposal(body: ProposalInput): Promise<TradeProposal> {
  return request<TradeProposal>("/trading/proposals", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function confirmProposal(id: number): Promise<ConfirmResult> {
  return request<ConfirmResult>(`/trading/proposals/${id}/confirm`, { method: "POST" });
}

export function rejectProposal(id: number): Promise<TradeProposal> {
  return request<TradeProposal>(`/trading/proposals/${id}/reject`, { method: "POST" });
}

export function cancelPaperOrder(id: number): Promise<PaperOrder> {
  return request<PaperOrder>(`/trading/orders/${id}/cancel`, { method: "POST" });
}
