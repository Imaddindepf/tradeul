'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, AlertTriangle, TrendingUp, Clock, CheckCircle, XCircle, HelpCircle, Rocket, FileText, ExternalLink, Loader2, ArrowLeft, Users, Building2, Scale, ClipboardList } from 'lucide-react';

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

  // View state: 'list' or 'detail' (inline, no modal)
  const [view, setView] = useState<'list' | 'detail'>('list');
  const [selectedIPO, setSelectedIPO] = useState<{ ticker: string; issuerName: string; ipoStatus: string } | null>(null);

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

      // Show inline detail view (no modal)
      setSelectedIPO({ ticker, issuerName, ipoStatus });
      setProspectusData(data);
      setView('detail');
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

  // Detail view (inline, no modal)
  if (view === 'detail' && selectedIPO) {
    const handleBack = () => {
      setView('list');
      setSelectedIPO(null);
      setProspectusData(null);
    };

    const structuredData = prospectusData?.structured_data;
    const filings = prospectusData?.filings || [];

    return (
      <div className="h-full flex flex-col bg-white">
        {/* Header */}
        <div className="flex items-center gap-2 px-2 py-1.5 border-b border-slate-200">
          <button onClick={handleBack} className="p-1 hover:bg-slate-100 rounded transition-colors">
            <ArrowLeft className="w-3.5 h-3.5 text-slate-600" />
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono font-semibold text-sm">{selectedIPO.ticker}</span>
              <span className="text-[9px] px-1 py-0.5 rounded bg-slate-100 text-slate-600">
                {STATUS_CONFIG[selectedIPO.ipoStatus]?.label || selectedIPO.ipoStatus}
              </span>
            </div>
            <p className="text-[10px] text-slate-500 truncate">{selectedIPO.issuerName}</p>
          </div>
          <a
            href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${encodeURIComponent(selectedIPO.issuerName)}&type=S-1&dateb=&owner=include&count=40`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 text-[10px] text-slate-600 hover:bg-slate-100 rounded transition-colors"
          >
            SEC EDGAR <ExternalLink className="w-2.5 h-2.5" />
          </a>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-2 space-y-3">
          {structuredData ? (
            <>
              {/* Filing Info */}
              <div className="flex items-center gap-3 text-[10px] text-slate-500">
                <span className="font-mono font-semibold text-slate-700">{structuredData.form_type}</span>
                <span>Filed: {formatDate(structuredData.filed_at)}</span>
                {structuredData.filing_url && (
                  <a href={structuredData.filing_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-blue-600 hover:underline">
                    View <ExternalLink className="w-2.5 h-2.5" />
                  </a>
                )}
              </div>

              {/* Offering Price */}
              {structuredData.public_offering_price && (
                <div className="border border-slate-200 rounded p-2">
                  <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-medium text-slate-700">
                    <TrendingUp className="w-3 h-3" /> Offering Price
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[10px]">
                    <div>
                      <span className="text-slate-500">Per Share</span>
                      <span className="ml-2 font-mono font-semibold">
                        {structuredData.public_offering_price.perShareText || formatPrice(structuredData.public_offering_price.perShare)}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500">Total</span>
                      <span className="ml-2 font-mono font-semibold">
                        {structuredData.public_offering_price.totalText || formatSize(structuredData.public_offering_price.total)}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Securities */}
              {structuredData.securities?.length > 0 && (
                <div className="border border-slate-200 rounded p-2">
                  <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-medium text-slate-700">
                    <ClipboardList className="w-3 h-3" /> Securities ({structuredData.securities.length})
                  </div>
                  <div className="space-y-0.5 text-[10px] text-slate-600">
                    {structuredData.securities.map((sec: any, i: number) => (
                      <div key={i}>{sec.name}</div>
                    ))}
                  </div>
                </div>
              )}

              {/* Underwriters */}
              {structuredData.underwriters?.length > 0 && (
                <div className="border border-slate-200 rounded p-2">
                  <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-medium text-slate-700">
                    <Building2 className="w-3 h-3" /> Underwriters ({structuredData.underwriters.length})
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {structuredData.underwriters.slice(0, 10).map((uw: any, i: number) => (
                      <span key={i} className={`px-1.5 py-0.5 rounded text-[9px] ${i === 0 ? 'bg-slate-200 font-medium' : 'bg-slate-100'} text-slate-700`}>
                        {uw.name}
                      </span>
                    ))}
                    {structuredData.underwriters.length > 10 && (
                      <span className="px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded text-[9px]">+{structuredData.underwriters.length - 10}</span>
                    )}
                  </div>
                </div>
              )}

              {/* Management */}
              {structuredData.management?.length > 0 && (
                <div className="border border-slate-200 rounded p-2">
                  <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-medium text-slate-700">
                    <Users className="w-3 h-3" /> Management ({structuredData.management.length})
                  </div>
                  <div className="space-y-1 text-[10px]">
                    {structuredData.management.slice(0, 6).map((m: any, i: number) => (
                      <div key={i} className="flex items-center gap-2">
                        <span className="font-medium text-slate-700">{m.name}</span>
                        {m.age && <span className="text-slate-400">({m.age})</span>}
                        <span className="text-slate-500 truncate">{m.position}</span>
                      </div>
                    ))}
                    {structuredData.management.length > 6 && <div className="text-slate-400">+{structuredData.management.length - 6} more</div>}
                  </div>
                </div>
              )}

              {/* Employees */}
              {structuredData.employees?.total && (
                <div className="border border-slate-200 rounded p-2 flex items-center justify-between">
                  <span className="text-[10px] text-slate-500">Employees</span>
                  <span className="font-mono font-semibold text-sm">{structuredData.employees.total.toLocaleString()}</span>
                </div>
              )}

              {/* Law Firms & Auditors */}
              <div className="grid grid-cols-2 gap-2">
                {structuredData.law_firms?.length > 0 && (
                  <div className="border border-slate-200 rounded p-2">
                    <div className="flex items-center gap-1.5 mb-1 text-[10px] font-medium text-slate-700">
                      <Scale className="w-3 h-3" /> Law Firms
                    </div>
                    <div className="space-y-0.5 text-[9px] text-slate-600">
                      {structuredData.law_firms.slice(0, 3).map((lf: any, i: number) => <div key={i} className="truncate">{lf.name}</div>)}
                    </div>
                  </div>
                )}
                {structuredData.auditors?.length > 0 && (
                  <div className="border border-slate-200 rounded p-2">
                    <div className="flex items-center gap-1.5 mb-1 text-[10px] font-medium text-slate-700">
                      <ClipboardList className="w-3 h-3" /> Auditors
                    </div>
                    <div className="space-y-0.5 text-[9px] text-slate-600">
                      {structuredData.auditors.map((a: any, i: number) => <div key={i} className="truncate">{a.name}</div>)}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="text-center py-6">
              {selectedIPO.ipoStatus === 'pending' || selectedIPO.ipoStatus === 'rumor' ? (
                <>
                  <Clock className="w-6 h-6 mx-auto mb-2 text-slate-400" />
                  <p className="text-[11px] font-medium text-slate-700 mb-1">S-1 Not Yet Filed</p>
                  <p className="text-[10px] text-slate-500 max-w-xs mx-auto">
                    {prospectusData?.message || "The S-1 Registration Statement has not yet been filed with the SEC."}
                  </p>
                </>
              ) : (
                <>
                  <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-slate-400" />
                  <p className="text-[11px] text-slate-500">{prospectusData?.message || "No SEC filings found."}</p>
                </>
              )}
            </div>
          )}

          {/* All Filings */}
          {filings.length > 0 && (
            <div className="border-t border-slate-200 pt-2">
              <div className="text-[10px] font-medium text-slate-700 mb-1.5">All Filings ({filings.length})</div>
              <div className="space-y-1">
                {filings.map((f: any, i: number) => (
                  <a key={i} href={f.filing_url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between px-2 py-1 bg-slate-50 rounded hover:bg-slate-100 transition-colors text-[10px]">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-slate-700">{f.form_type}</span>
                      <span className="text-slate-500">{formatDate(f.filed_at)}</span>
                    </div>
                    <ExternalLink className="w-2.5 h-2.5 text-slate-400" />
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-2 py-0.5 border-t border-slate-200 text-[8px] text-slate-400">SEC-API.io</div>
      </div>
    );
  }

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
        <span>Polygon.io</span>
        <span>{filteredIPOs.length} of {ipos.length}</span>
      </div>
    </div>
  );
}

