'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, AlertTriangle, TrendingUp, Clock, CheckCircle, XCircle, HelpCircle, Rocket, FileText, ExternalLink, Loader2 } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

interface IPO {
  ticker: string;
  issuer_name: string;
  ipo_status: 'pending' | 'new' | 'history' | 'rumor' | 'withdrawn' | 'direct_listing_process' | 'postponed';
  listing_date?: string;
  announced_date?: string;
  last_updated: string;
  currency_code?: string;
  final_issue_price?: number;
  lowest_offer_price?: number;
  highest_offer_price?: number;
  total_offer_size?: number;
  max_shares_offered?: number;
  min_shares_offered?: number;
  shares_outstanding?: number;
  primary_exchange?: string;
  security_type?: string;
  security_description?: string;
  lot_size?: number;
  us_code?: string;
  isin?: string;
}

interface IPOResponse {
  status: string;
  count: number;
  results: IPO[];
  cached: boolean;
  cache_ttl_hours?: number;
  total_available?: number;
}

type StatusFilter = 'all' | 'pending' | 'new' | 'history' | 'rumor' | 'withdrawn' | 'direct_listing_process';

// ============================================================================
// Helpers
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: typeof Clock }> = {
  pending: { label: 'PENDING', color: 'text-amber-700', bg: 'bg-amber-50', icon: Clock },
  new: { label: 'NEW', color: 'text-emerald-700', bg: 'bg-emerald-50', icon: Rocket },
  history: { label: 'LISTED', color: 'text-blue-700', bg: 'bg-blue-50', icon: CheckCircle },
  rumor: { label: 'RUMOR', color: 'text-purple-700', bg: 'bg-purple-50', icon: HelpCircle },
  withdrawn: { label: 'WITHDRAWN', color: 'text-red-700', bg: 'bg-red-50', icon: XCircle },
  direct_listing_process: { label: 'DLP', color: 'text-cyan-700', bg: 'bg-cyan-50', icon: TrendingUp },
  postponed: { label: 'POSTPONED', color: 'text-slate-700', bg: 'bg-slate-100', icon: Clock },
};

const EXCHANGE_MAP: Record<string, string> = {
  XNAS: 'NASDAQ',
  XNYS: 'NYSE',
  XASE: 'AMEX',
  ARCX: 'ARCA',
  BATS: 'BATS',
};

function formatPrice(price: number | undefined): string {
  if (price === undefined || price === null) return '—';
  return `$${price.toFixed(2)}`;
}

function formatSize(size: number | undefined): string {
  if (size === undefined || size === null) return '—';
  if (size >= 1_000_000_000) return `$${(size / 1_000_000_000).toFixed(1)}B`;
  if (size >= 1_000_000) return `$${(size / 1_000_000).toFixed(1)}M`;
  if (size >= 1_000) return `$${(size / 1_000).toFixed(0)}K`;
  return `$${size}`;
}

function formatShares(shares: number | undefined): string {
  if (shares === undefined || shares === null) return '—';
  if (shares >= 1_000_000) return `${(shares / 1_000_000).toFixed(1)}M`;
  if (shares >= 1_000) return `${(shares / 1_000).toFixed(0)}K`;
  return shares.toString();
}

function formatDate(dateStr: string | undefined): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
  } catch {
    return dateStr;
  }
}

// ============================================================================
// Component
// ============================================================================

export function IPOContent() {
  const { t } = useTranslation();
  const [ipos, setIpos] = useState<IPO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending');
  const [cached, setCached] = useState(false);
  const [loadingProspectus, setLoadingProspectus] = useState<string | null>(null);
  const [prospectusData, setProspectusData] = useState<any>(null);
  const [showProspectusModal, setShowProspectusModal] = useState(false);

  // Fetch IPO prospectus (S-1, 424B4) structured data from SEC-API.io
  const openProspectus = useCallback(async (ticker: string, ipoStatus: string, issuerName: string) => {
    setLoadingProspectus(ticker);
    try {
      const params = new URLSearchParams({
        ipo_status: ipoStatus,
        issuer_name: issuerName
      });
      const response = await fetch(`${API_URL}/api/v1/ipos/${ticker}/prospectus?${params}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();

      // Always show modal - it will display message for pending IPOs without filings
      setProspectusData({ ticker, issuerName, ipoStatus, ...data });
      setShowProspectusModal(true);
    } catch (err) {
      console.error('Error fetching prospectus:', err);
      // Fallback: open SEC EDGAR search by company name
      window.open(`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${encodeURIComponent(issuerName)}&type=S-1&dateb=&owner=include&count=40`, '_blank');
    } finally {
      setLoadingProspectus(null);
    }
  }, []);

  const fetchIPOs = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    setError(null);

    try {
      const url = `${API_URL}/api/v1/ipos?limit=500${forceRefresh ? '&force_refresh=true' : ''}`;
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data: IPOResponse = await response.json();
      setIpos(data.results || []);
      setCached(data.cached || false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading IPOs');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIPOs();
  }, [fetchIPOs]);

  // Filter IPOs by status
  const filteredIPOs = useMemo(() => {
    if (statusFilter === 'all') return ipos;
    return ipos.filter(ipo => ipo.ipo_status === statusFilter);
  }, [ipos, statusFilter]);

  // Count by status
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { all: ipos.length };
    ipos.forEach(ipo => {
      const status = ipo.ipo_status || 'unknown';
      counts[status] = (counts[status] || 0) + 1;
    });
    return counts;
  }, [ipos]);

  const STATUS_TABS: { id: StatusFilter; label: string }[] = [
    { id: 'pending', label: `Pending (${statusCounts.pending || 0})` },
    { id: 'new', label: `New (${statusCounts.new || 0})` },
    { id: 'direct_listing_process', label: `DLP (${statusCounts.direct_listing_process || 0})` },
    { id: 'rumor', label: `Rumor (${statusCounts.rumor || 0})` },
    { id: 'history', label: `Listed (${statusCounts.history || 0})` },
    { id: 'all', label: `All (${ipos.length})` },
  ];

  if (loading && ipos.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-white">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2" />
          <p className="text-slate-500 text-xs">Loading IPOs...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full bg-white">
        <div className="text-center">
          <AlertTriangle className="w-8 h-8 text-red-500 mx-auto mb-2" />
          <p className="text-red-600 text-sm">{error}</p>
          <button onClick={() => fetchIPOs()} className="mt-2 text-blue-600 text-xs hover:underline">
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1 bg-slate-50 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <Rocket className="w-4 h-4 text-blue-600" />
          <span className="text-xs font-semibold text-slate-700">IPOs</span>
          <span className="text-[10px] text-slate-400">({filteredIPOs.length})</span>
        </div>
        <div className="flex items-center gap-2">
          {cached && <span className="text-[9px] text-slate-400">Cached (24h)</span>}
          <button
            onClick={() => fetchIPOs(true)}
            disabled={loading}
            className="p-1 text-slate-400 hover:text-blue-600 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Status Tabs */}
      <div className="flex items-center gap-0.5 px-2 py-1 bg-slate-100 border-b border-slate-200 overflow-x-auto">
        {STATUS_TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setStatusFilter(tab.id)}
            className={`px-2 py-0.5 text-[9px] font-medium rounded whitespace-nowrap transition-colors ${statusFilter === tab.id
              ? 'bg-blue-600 text-white'
              : 'text-slate-600 hover:bg-slate-200'
              }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-[10px] border-collapse">
          <thead className="bg-slate-100 sticky top-0">
            <tr className="text-left text-slate-500 uppercase tracking-wide">
              <th className="px-1 py-0.5 font-medium w-12">{t('ipo.tableHeaders.ticker')}</th>
              <th className="px-1 py-0.5 font-medium w-10 text-center">{t('ipo.tableHeaders.status')}</th>
              <th className="px-1 py-0.5 font-medium">{t('ipo.tableHeaders.company')}</th>
              <th className="px-1 py-0.5 font-medium w-14 text-center">{t('ipo.tableHeaders.exchange')}</th>
              <th className="px-1 py-0.5 font-medium w-14 text-right">{t('ipo.tableHeaders.price')}</th>
              <th className="px-1 py-0.5 font-medium w-16 text-right">{t('ipo.tableHeaders.size')}</th>
              <th className="px-1 py-0.5 font-medium w-14 text-right">{t('ipo.tableHeaders.shares')}</th>
              <th className="px-1 py-0.5 font-medium w-16 text-center">{t('ipo.tableHeaders.date')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {filteredIPOs.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-2 py-4 text-center text-slate-400">
                  No IPOs found for this filter
                </td>
              </tr>
            ) : (
              filteredIPOs.map((ipo, idx) => {
                const statusCfg = STATUS_CONFIG[ipo.ipo_status] || STATUS_CONFIG.pending;
                const priceRange = ipo.lowest_offer_price && ipo.highest_offer_price && ipo.lowest_offer_price !== ipo.highest_offer_price
                  ? `$${ipo.lowest_offer_price}-${ipo.highest_offer_price}`
                  : ipo.final_issue_price
                    ? formatPrice(ipo.final_issue_price)
                    : ipo.lowest_offer_price
                      ? formatPrice(ipo.lowest_offer_price)
                      : '—';

                return (
                  <tr key={`${ipo.ticker}-${idx}`} className="hover:bg-blue-50/50 group">
                    <td className="px-1 py-0.5">
                      <button
                        onClick={() => openProspectus(ipo.ticker, ipo.ipo_status, ipo.issuer_name)}
                        disabled={loadingProspectus === ipo.ticker}
                        className="flex items-center gap-0.5 font-mono font-semibold text-blue-600 hover:text-blue-800 hover:underline cursor-pointer disabled:opacity-50"
                        title="View SEC Prospectus (S-1/424B4)"
                      >
                        {loadingProspectus === ipo.ticker ? (
                          <Loader2 className="w-2.5 h-2.5 animate-spin" />
                        ) : (
                          <FileText className="w-2.5 h-2.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                        )}
                        {ipo.ticker}
                        <ExternalLink className="w-2 h-2 opacity-0 group-hover:opacity-60 transition-opacity" />
                      </button>
                    </td>
                    <td className="px-1 py-0.5 text-center">
                      <span className={`px-1 py-0 rounded text-[8px] font-medium ${statusCfg.color} ${statusCfg.bg}`}>
                        {statusCfg.label}
                      </span>
                    </td>
                    <td className="px-1 py-0.5 text-slate-700 truncate max-w-[200px]" title={ipo.issuer_name}>
                      {ipo.issuer_name}
                    </td>
                    <td className="px-1 py-0.5 text-center text-slate-500 font-mono">
                      {EXCHANGE_MAP[ipo.primary_exchange || ''] || ipo.primary_exchange || '—'}
                    </td>
                    <td className="px-1 py-0.5 text-right font-mono text-slate-700">
                      {priceRange}
                    </td>
                    <td className="px-1 py-0.5 text-right font-mono text-slate-600">
                      {formatSize(ipo.total_offer_size)}
                    </td>
                    <td className="px-1 py-0.5 text-right font-mono text-slate-500">
                      {formatShares(ipo.max_shares_offered)}
                    </td>
                    <td className="px-1 py-0.5 text-center font-mono text-slate-500">
                      {formatDate(ipo.listing_date || ipo.announced_date)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="px-2 py-0.5 bg-slate-50 border-t border-slate-200 text-[8px] text-slate-400 flex justify-between">
        <span>Polygon.io • Updated daily</span>
        <span>{filteredIPOs.length} of {ipos.length} IPOs</span>
      </div>

      {/* Prospectus Modal */}
      {showProspectusModal && prospectusData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowProspectusModal(false)}>
          <div
            className="bg-white rounded-lg shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden m-4"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white">
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5" />
                <div>
                  <h3 className="font-bold text-lg">{prospectusData.ticker} Prospectus</h3>
                  <p className="text-blue-100 text-xs">{prospectusData.structured_data?.entity_name}</p>
                </div>
              </div>
              <button
                onClick={() => setShowProspectusModal(false)}
                className="p-1 hover:bg-white/20 rounded transition-colors"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="overflow-auto max-h-[calc(80vh-120px)] p-4 space-y-4">
              {prospectusData.structured_data ? (
                <>
                  {/* Form Info */}
                  <div className="flex items-center gap-4 text-sm">
                    <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded font-semibold">
                      {prospectusData.structured_data.form_type}
                    </span>
                    <span className="text-slate-500">
                      Filed: {formatDate(prospectusData.structured_data.filed_at)}
                    </span>
                    {prospectusData.structured_data.filing_url && (
                      <a
                        href={prospectusData.structured_data.filing_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-blue-600 hover:underline"
                      >
                        <ExternalLink className="w-3 h-3" />
                        View Filing
                      </a>
                    )}
                  </div>

                  {/* Pricing Info */}
                  {prospectusData.structured_data.public_offering_price && (
                    <div className="bg-emerald-50 rounded-lg p-3 border border-emerald-200">
                      <h4 className="font-semibold text-emerald-800 text-sm mb-2">💰 Offering Price</h4>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div>
                          <span className="text-slate-500">Per Share:</span>
                          <span className="ml-2 font-mono font-bold text-emerald-700">
                            {prospectusData.structured_data.public_offering_price.perShareText || formatPrice(prospectusData.structured_data.public_offering_price.perShare)}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500">Total:</span>
                          <span className="ml-2 font-mono font-bold text-emerald-700">
                            {prospectusData.structured_data.public_offering_price.totalText || formatSize(prospectusData.structured_data.public_offering_price.total)}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Securities */}
                  {prospectusData.structured_data.securities?.length > 0 && (
                    <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                      <h4 className="font-semibold text-slate-700 text-sm mb-2">📊 Securities Offered</h4>
                      <ul className="text-sm space-y-1">
                        {prospectusData.structured_data.securities.map((sec: any, i: number) => (
                          <li key={i} className="text-slate-600">{sec.name}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Underwriters */}
                  {prospectusData.structured_data.underwriters?.length > 0 && (
                    <div className="bg-amber-50 rounded-lg p-3 border border-amber-200">
                      <h4 className="font-semibold text-amber-800 text-sm mb-2">🏦 Underwriters ({prospectusData.structured_data.underwriters.length})</h4>
                      <div className="flex flex-wrap gap-1">
                        {prospectusData.structured_data.underwriters.slice(0, 8).map((uw: any, i: number) => (
                          <span key={i} className={`px-2 py-0.5 rounded text-xs ${i === 0 ? 'bg-amber-200 text-amber-800 font-semibold' : 'bg-amber-100 text-amber-700'}`}>
                            {uw.name}
                          </span>
                        ))}
                        {prospectusData.structured_data.underwriters.length > 8 && (
                          <span className="px-2 py-0.5 bg-amber-100 text-amber-600 rounded text-xs">
                            +{prospectusData.structured_data.underwriters.length - 8} more
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Management */}
                  {prospectusData.structured_data.management?.length > 0 && (
                    <div className="bg-purple-50 rounded-lg p-3 border border-purple-200">
                      <h4 className="font-semibold text-purple-800 text-sm mb-2">👥 Management Team</h4>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        {prospectusData.structured_data.management.slice(0, 6).map((m: any, i: number) => (
                          <div key={i} className="flex items-center gap-2">
                            <span className="font-medium text-purple-700">{m.name}</span>
                            {m.age && <span className="text-purple-400">({m.age})</span>}
                            <span className="text-purple-500 truncate">{m.position}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Employees */}
                  {prospectusData.structured_data.employees?.total && (
                    <div className="bg-cyan-50 rounded-lg p-3 border border-cyan-200">
                      <h4 className="font-semibold text-cyan-800 text-sm mb-1">👷 Employees</h4>
                      <span className="font-mono text-lg font-bold text-cyan-700">
                        {prospectusData.structured_data.employees.total.toLocaleString()}
                      </span>
                      {prospectusData.structured_data.employees.asOfDate && (
                        <span className="text-cyan-500 text-xs ml-2">
                          as of {formatDate(prospectusData.structured_data.employees.asOfDate)}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Law Firms & Auditors */}
                  <div className="grid grid-cols-2 gap-3">
                    {prospectusData.structured_data.law_firms?.length > 0 && (
                      <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                        <h4 className="font-semibold text-slate-700 text-xs mb-1">⚖️ Law Firms</h4>
                        <div className="space-y-0.5">
                          {prospectusData.structured_data.law_firms.slice(0, 3).map((lf: any, i: number) => (
                            <div key={i} className="text-[10px] text-slate-600">{lf.name}</div>
                          ))}
                        </div>
                      </div>
                    )}
                    {prospectusData.structured_data.auditors?.length > 0 && (
                      <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                        <h4 className="font-semibold text-slate-700 text-xs mb-1">📋 Auditors</h4>
                        <div className="space-y-0.5">
                          {prospectusData.structured_data.auditors.map((a: any, i: number) => (
                            <div key={i} className="text-[10px] text-slate-600">{a.name}</div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="text-center py-8">
                  {prospectusData.ipoStatus === 'pending' || prospectusData.ipoStatus === 'rumor' ? (
                    <>
                      <Clock className="w-10 h-10 mx-auto mb-3 text-amber-500" />
                      <h4 className="font-semibold text-slate-700 mb-2">S-1 Not Yet Filed</h4>
                      <p className="text-slate-500 text-sm max-w-md mx-auto">
                        {prospectusData.message || "The S-1 Registration Statement has not yet been filed with the SEC. This is normal for pending IPOs."}
                      </p>
                      <p className="text-slate-400 text-xs mt-2">
                        The S-1 is typically filed a few weeks before the expected listing date.
                      </p>
                      <a
                        href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${encodeURIComponent(prospectusData.issuerName || prospectusData.ticker)}&type=S-1&dateb=&owner=include&count=40`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
                      >
                        <ExternalLink className="w-4 h-4" />
                        Search SEC EDGAR
                      </a>
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="w-8 h-8 mx-auto mb-2 text-amber-500" />
                      <p className="text-slate-500">{prospectusData.message || "No SEC filings found for this ticker."}</p>
                      <a
                        href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${encodeURIComponent(prospectusData.issuerName || prospectusData.ticker)}&type=S-1&dateb=&owner=include&count=40`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 mt-3 text-blue-600 hover:underline text-sm"
                      >
                        <ExternalLink className="w-3 h-3" />
                        Search on SEC EDGAR
                      </a>
                    </>
                  )}
                </div>
              )}

              {/* All Filings List */}
              {prospectusData.filings?.length > 0 && (
                <div className="border-t border-slate-200 pt-3 mt-3">
                  <h4 className="font-semibold text-slate-700 text-sm mb-2">📁 All Filings ({prospectusData.filings.length})</h4>
                  <div className="space-y-1">
                    {prospectusData.filings.map((f: any, i: number) => (
                      <a
                        key={i}
                        href={f.filing_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-between px-2 py-1 bg-slate-50 rounded hover:bg-blue-50 transition-colors text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-semibold text-blue-600">{f.form_type}</span>
                          <span className="text-slate-500">{formatDate(f.filed_at)}</span>
                        </div>
                        <div className="flex items-center gap-2 text-slate-400">
                          {f.has_pricing && <span className="text-emerald-500">💰</span>}
                          {f.underwriters_count > 0 && <span>🏦{f.underwriters_count}</span>}
                          <ExternalLink className="w-3 h-3" />
                        </div>
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-4 py-2 bg-slate-50 border-t border-slate-200 flex justify-between items-center">
              <span className="text-[10px] text-slate-400">SEC-API.io • Cached 7 days</span>
              <button
                onClick={() => setShowProspectusModal(false)}
                className="px-3 py-1 bg-slate-200 hover:bg-slate-300 rounded text-sm transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

