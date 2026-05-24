const DILUTION_SERVICE_URL = process.env.NEXT_PUBLIC_DILUTION_API_URL || "http://localhost:8009";
const DILUTION_REVIEW_SERVICE_URL =
  process.env.NEXT_PUBLIC_DILUTION_REVIEW_API_URL ||
  process.env.NEXT_PUBLIC_API_GATEWAY_URL ||
  "http://localhost:8000";

export interface InstrumentContextDetail {
  [key: string]: string | number | boolean | null;
}

export interface InstrumentContextInstrument {
  id: string;
  ticker: string;
  offering_type: string;
  security_name: string;
  card_color: string;
  reg_status: string;
  edgar_url?: string | null;
  file_number?: string | null;
  last_update_date?: string | null;
  details: InstrumentContextDetail;
}

export interface InstrumentContextTickerInfo {
  ticker: string;
  company?: string | null;
  float_shares?: number | null;
  shares_outstanding?: number | null;
  last_price?: number | null;
  num_offerings?: number | null;
}

export interface InstrumentContextStats {
  total: number;
  registered: number;
  pending_effect: number;
  by_type: Record<string, number>;
}

export interface InstrumentContextCompletedOffering {
  id: number;
  ticker: string;
  offering_date?: string | null;
  offering_type?: string | null;
  method?: string | null;
  shares?: number | null;
  price?: number | null;
  warrants?: number | null;
  amount?: number | null;
  bank?: string | null;
}

export interface InstrumentContextResponse {
  ticker_info: InstrumentContextTickerInfo;
  instruments: InstrumentContextInstrument[];
  completed_offerings: InstrumentContextCompletedOffering[];
  stats: InstrumentContextStats;
}

export interface AmbiguousFilingItem {
  message_id: string;
  ticker?: string | null;
  accession_number?: string | null;
  form_type?: string | null;
  filed_at?: string | null;
  confidence?: string | null;
  review_reason?: string | null;
  payload: Record<string, unknown>;
}

export interface AmbiguousFilingListResponse {
  total: number;
  items: AmbiguousFilingItem[];
}

export interface ReviewedFilingItem {
  message_id: string;
  accession_number?: string | null;
  decision?: string | null;
  notes?: string | null;
  source_message_id?: string | null;
  reviewed_at?: string | null;
  payload: Record<string, unknown>;
}

export interface ReviewedFilingListResponse {
  total: number;
  items: ReviewedFilingItem[];
}

export interface ReviewMetricsResponse {
  generated_at: string;
  ambiguous_queue_depth: number;
  filings_stream_depth: number;
  reviewed_stream_depth: number;
  reviewed_last_24h: number;
  decisions_last_24h: Record<string, number>;
}

export interface ApplyActionChange {
  action: string;
  instrument_id?: string | null;
  result: string;
  details: Record<string, unknown>;
}

export interface ApplyAmbiguousActionsResponse {
  dry_run: boolean;
  ticker: string;
  accession_number: string;
  applied: boolean;
  changes: ApplyActionChange[];
  warnings: string[];
}

export async function getInstrumentContext(ticker: string): Promise<InstrumentContextResponse> {
  const response = await fetch(`${DILUTION_SERVICE_URL}/api/instrument-context/${ticker}`, {
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch instrument context for ${ticker}`);
  }
  return response.json();
}

function _reviewHeaders(token: string | null): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

export async function listAmbiguousFilings(
  params?: { limit?: number; ticker?: string },
  token: string | null = null,
): Promise<AmbiguousFilingListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.ticker) searchParams.set("ticker", params.ticker);
  const qs = searchParams.toString();
  const response = await fetch(
    `${DILUTION_REVIEW_SERVICE_URL}/api/v1/dilution-v2/review/ambiguous${qs ? `?${qs}` : ""}`,
    {
      signal: AbortSignal.timeout(15000),
      headers: _reviewHeaders(token),
    },
  );
  if (!response.ok) {
    throw new Error("Failed to load ambiguous filings");
  }
  return response.json();
}

export async function listReviewedFilings(
  params?: { limit?: number; ticker?: string; decision?: string },
  token: string | null = null,
): Promise<ReviewedFilingListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.ticker) searchParams.set("ticker", params.ticker);
  if (params?.decision) searchParams.set("decision", params.decision);
  const qs = searchParams.toString();
  const response = await fetch(
    `${DILUTION_REVIEW_SERVICE_URL}/api/v1/dilution-v2/review/reviewed${qs ? `?${qs}` : ""}`,
    {
      signal: AbortSignal.timeout(15000),
      headers: _reviewHeaders(token),
    },
  );
  if (!response.ok) {
    throw new Error("Failed to load reviewed filings");
  }
  return response.json();
}

export async function getReviewMetrics(token: string | null = null): Promise<ReviewMetricsResponse> {
  const response = await fetch(`${DILUTION_REVIEW_SERVICE_URL}/api/v1/dilution-v2/review/metrics`, {
    headers: _reviewHeaders(token),
  });
  if (!response.ok) {
    throw new Error("Failed to load review metrics");
  }
  return response.json();
}

export async function requeueAmbiguousFiling(
  accessionNumber: string,
  reason = "manual_requeue",
  token: string | null = null,
): Promise<void> {
  const response = await fetch(`${DILUTION_REVIEW_SERVICE_URL}/api/v1/dilution-v2/review/ambiguous/requeue`, {
    method: "POST",
    headers: _reviewHeaders(token),
    body: JSON.stringify({ accession_number: accessionNumber, reason }),
  });
  if (!response.ok) {
    throw new Error("Failed to requeue ambiguous filing");
  }
}

export async function resolveAmbiguousFiling(
  accessionNumber: string,
  resolution: "ignore" | "accepted_manual_apply",
  notes?: string,
  token: string | null = null,
): Promise<void> {
  const response = await fetch(`${DILUTION_REVIEW_SERVICE_URL}/api/v1/dilution-v2/review/ambiguous/resolve`, {
    method: "POST",
    headers: _reviewHeaders(token),
    body: JSON.stringify({ accession_number: accessionNumber, resolution, notes }),
  });
  if (!response.ok) {
    throw new Error("Failed to resolve ambiguous filing");
  }
}

export async function applyAmbiguousActions(
  payload: { dry_run: boolean; batch: Record<string, unknown> },
  token: string | null = null,
): Promise<ApplyAmbiguousActionsResponse> {
  const response = await fetch(`${DILUTION_REVIEW_SERVICE_URL}/api/v1/dilution-v2/review/ambiguous/apply`, {
    method: "POST",
    headers: _reviewHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const maybeText = await response.text().catch(() => "");
    throw new Error(maybeText || "Failed to apply ambiguous actions");
  }
  return response.json();
}
