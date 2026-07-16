/**
 * AI Alerts — typed client for the LLM-compiled alert specs API
 * (ai-agent-v4 /api/alerts*). Drafts are created from the chat; this
 * client manages their lifecycle: arm, pause, re-dry-run, fires, archive.
 */
import { authFetchStandalone } from '@/hooks/useAuthFetch';

const AGENT_BASE = process.env.NEXT_PUBLIC_AI_AGENT_V4_API_URL || 'https://agent.tradeul.com/v4';

export type GetTokenFn = (opts?: { skipCache?: boolean }) => Promise<string | null>;

// ── Types (mirror of services/ai-agent-v4/alerts/spec.py) ─────────

export type AlertStatus = 'draft' | 'armed' | 'paused' | 'archived';
export type AlertTier = 'event_match' | 'sequence' | 'membership' | 'agentic';

export interface AlertUniverse {
  symbols_include: string[];
  symbols_exclude: string[];
  min_price: number | null;
  max_price: number | null;
  min_rvol: number | null;
  min_volume: number | null;
  min_market_cap: number | null;
  max_market_cap: number | null;
  sector: string | null;
  session: 'regular' | 'premarket' | 'afterhours' | 'all';
}

export interface AlertSequenceStep {
  event_types: string[];
  after: 'session_open' | 'opening_low' | 'prev_step';
  within_minutes: number | null;
}

export interface AlertDayCondition {
  metric: string;
  op: 'gt' | 'gte' | 'lt' | 'lte' | 'eq';
  value: number;
}

export interface AlertPriceLevel {
  direction: 'above' | 'below';
  value: number;
}

export interface AlertLifecycle {
  cooldown_seconds: number;
  max_fires_per_day: number;
  pending_seconds?: number;
}

export interface AlertSpec {
  id: string;
  user_id: string;
  name: string;
  status: AlertStatus;
  tier: AlertTier;
  source_query: string;
  paraphrase: string;
  created_at: number;
  updated_at: number;
  universe: AlertUniverse;
  steps: AlertSequenceStep[];
  day_conditions: AlertDayCondition[];
  price_levels?: AlertPriceLevel[];
  lifecycle: AlertLifecycle;
  trigger_id: string | null;
  dry_run?: {
    total_fires: number;
    days_scanned: string[];
    unique_symbols: string[];
  } | null;
}

export interface DryRunMatch {
  symbol: string;
  open?: number;
  close?: number;
  close_vs_open_pct?: number;
  market_cap?: number;
  opening_drop_pct?: number;
  [k: string]: unknown; // stepN_event / stepN_time / stepN_price / stepN_vwap
}

export interface DryRunDay {
  date: string;
  count: number;
  matches: DryRunMatch[];
  error?: string;
}

/** One minute-bar (ET wall-clock epoch seconds) for the evidence chart. */
export interface EvidenceBar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
}

export interface EvidenceFire {
  t: number;
  price?: number | null;
  label?: string;
}

/** Real candles of a dry-run day with the exact fire moments marked. */
export interface ChartEvidence {
  symbol: string;
  date: string;
  bars: EvidenceBar[];
  fires: EvidenceFire[];
  levels: AlertPriceLevel[];
}

export interface DryRunResult {
  days_scanned: string[];
  total_fires: number;
  unique_symbols: string[];
  per_day: DryRunDay[];
  chart_evidence?: ChartEvidence[];
  errors: string[];
  elapsed_ms: number;
}

export interface AlertFire {
  symbol: string;
  event_type: string | null;
  price: number | null;
  evidence: Record<string, unknown> | null;
  fired_at: number;
}

export interface SimilarAlertSummary {
  spec_id: string;
  name: string;
  status: AlertStatus;
  tier: AlertTier;
  paraphrase: string;
  symbols: string[];
  event_types: string[];
  membership?: { category?: string; on?: string; rank_lte?: number } | null;
}

/** Payload of the `alert_draft` structured output emitted by the chat WS. */
export interface AlertDraftPayload {
  spec_id: string;
  name: string;
  status: AlertStatus;
  tier: AlertTier;
  paraphrase: string;
  armable_now: boolean;
  persisted: boolean;
  duplicate?: boolean;
  similar?: {
    recommendation: 'create' | 'reuse' | 'review';
    exact: SimilarAlertSummary[];
    near: SimilarAlertSummary[];
  };
  universe: Partial<AlertUniverse>;
  steps: AlertSequenceStep[];
  day_conditions: AlertDayCondition[];
  membership?: { category: string; on: 'enter' | 'exit'; rank_lte?: number | null } | null;
  price_levels?: AlertPriceLevel[];
  lifecycle: Partial<AlertLifecycle>;
  dry_run: {
    total_fires: number;
    days_scanned: string[];
    unique_symbols: string[];
    per_day: DryRunDay[];
    chart_evidence?: ChartEvidence[];
    errors: string[];
    note?: string;
  };
}

// ── API calls ─────────────────────────────────────────────────────

async function call<T>(
  getToken: GetTokenFn,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await authFetchStandalone(`${AGENT_BASE}${path}`, getToken, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function listAlerts(getToken: GetTokenFn, includeArchived = false) {
  return call<{ alerts: AlertSpec[]; count: number }>(
    getToken, `/api/alerts?include_archived=${includeArchived}`,
  );
}

export function getAlert(getToken: GetTokenFn, specId: string) {
  return call<AlertSpec>(getToken, `/api/alerts/${specId}`);
}

export function armAlert(getToken: GetTokenFn, specId: string) {
  return call<{ spec_id: string; status: string; live: boolean; kind?: string; note: string }>(
    getToken, `/api/alerts/${specId}/arm`, { method: 'POST' },
  );
}

export function pauseAlert(getToken: GetTokenFn, specId: string) {
  return call<{ spec_id: string; status: string }>(
    getToken, `/api/alerts/${specId}/pause`, { method: 'POST' },
  );
}

export function rerunDryRun(getToken: GetTokenFn, specId: string, days = 5) {
  return call<DryRunResult>(
    getToken, `/api/alerts/${specId}/dry-run?days=${days}`, { method: 'POST' },
  );
}

export function listFires(getToken: GetTokenFn, specId: string, limit = 50) {
  return call<{ spec_id: string; fires: AlertFire[]; count: number }>(
    getToken, `/api/alerts/${specId}/fires?limit=${limit}`,
  );
}

export function archiveAlert(getToken: GetTokenFn, specId: string) {
  return call<{ spec_id: string; status: string }>(
    getToken, `/api/alerts/${specId}`, { method: 'DELETE' },
  );
}

// ── Display helpers ───────────────────────────────────────────────

export function formatUniverse(u: Partial<AlertUniverse> | undefined): string[] {
  if (!u) return [];
  const parts: string[] = [];
  if (u.symbols_include?.length) parts.push(u.symbols_include.join(', '));
  if (u.min_price != null && u.max_price != null) parts.push(`$${u.min_price}–$${u.max_price}`);
  else if (u.min_price != null) parts.push(`≥ $${u.min_price}`);
  else if (u.max_price != null) parts.push(`≤ $${u.max_price}`);
  if (u.min_rvol != null) parts.push(`RVOL ≥ ${u.min_rvol}`);
  if (u.min_volume != null) parts.push(`Vol ≥ ${fmtCompact(u.min_volume)}`);
  if (u.min_market_cap != null) parts.push(`MCap ≥ ${fmtCompact(u.min_market_cap)}`);
  if (u.max_market_cap != null) parts.push(`MCap ≤ ${fmtCompact(u.max_market_cap)}`);
  if (u.sector) parts.push(u.sector);
  if (u.session && u.session !== 'regular') parts.push(u.session);
  return parts;
}

export function fmtCompact(n: number): string {
  if (n >= 1e9) return `${+(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${+(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${+(n / 1e3).toFixed(0)}K`;
  return String(n);
}

export function formatPriceLevel(p: AlertPriceLevel): string {
  return p.direction === 'above' ? `↑ $${p.value}` : `↓ $${p.value}`;
}

export function fmtCooldown(seconds: number): string {
  if (seconds >= 3600) return `${+(seconds / 3600).toFixed(1)}h`;
  if (seconds >= 60) return `${Math.round(seconds / 60)}min`;
  return `${seconds}s`;
}

/** Extract per-step evidence columns from a dry-run match row. */
export function matchSteps(m: DryRunMatch): Array<{ event: string; time: string; price?: number }> {
  const out: Array<{ event: string; time: string; price?: number }> = [];
  for (let i = 1; i <= 5; i++) {
    const ev = m[`step${i}_event`];
    const t = m[`step${i}_time`];
    if (!ev || !t) break;
    out.push({
      event: String(ev),
      time: String(t),
      price: typeof m[`step${i}_price`] === 'number' ? (m[`step${i}_price`] as number) : undefined,
    });
  }
  return out;
}
