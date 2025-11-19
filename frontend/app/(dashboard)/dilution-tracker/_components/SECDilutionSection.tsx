"use client";

import { useState, useEffect } from "react";
import { 
  AlertCircle, 
  ExternalLink, 
  RefreshCw, 
  FileText, 
  TrendingDown, 
  Calendar, 
  DollarSign, 
  Percent,
  Zap,
  Waves,
  Archive,
  CheckCircle2,
  Info,
  BadgeDollarSign,
  BarChart3
} from "lucide-react";
import { 
  getSECDilutionProfile, 
  refreshSECDilutionProfile,
  type SECDilutionProfileResponse,
  type Warrant,
  type ATMOffering,
  type ShelfRegistration,
  type CompletedOffering 
} from "@/lib/dilution-api";

interface SECDilutionSectionProps {
  ticker: string;
}

export function SECDilutionSection({ ticker }: SECDilutionSectionProps) {
  const [data, setData] = useState<SECDilutionProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
  }, [ticker]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const profile = await getSECDilutionProfile(ticker);
      setData(profile);
      
      if (!profile) {
        setError("No SEC dilution data available for this ticker");
      }
    } catch (err) {
      setError("Failed to load SEC dilution data");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const success = await refreshSECDilutionProfile(ticker);
      if (success) {
        await fetchData();
      }
    } catch (err) {
      console.error("Failed to refresh:", err);
    } finally {
      setRefreshing(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-8">
        <div className="flex items-center justify-center">
          <RefreshCw className="h-6 w-6 text-slate-400 animate-spin" />
          <span className="ml-3 text-slate-600">Loading SEC dilution data...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-6">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
          <div>
            <h4 className="font-semibold text-slate-900 mb-1">SEC Data Unavailable</h4>
            <p className="text-sm text-slate-600">
              {error || "Unable to extract dilution data from recent SEC filings. This may indicate no active warrants, ATM, or shelf registrations."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const { profile, dilution_analysis, cached, cache_age_seconds } = data;

  // Check if there's any data
  const hasData = 
    profile.warrants.length > 0 || 
    profile.atm_offerings.length > 0 || 
    profile.shelf_registrations.length > 0 || 
    profile.completed_offerings.length > 0;

  if (!hasData) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-xl p-6">
        <div className="flex items-start gap-3">
          <FileText className="h-5 w-5 text-green-600 mt-0.5 shrink-0" />
          <div>
            <h4 className="font-semibold text-slate-900 mb-1">Clean Dilution Profile</h4>
            <p className="text-sm text-slate-600">
              No active warrants, ATM offerings, or shelf registrations found in recent SEC filings.
            </p>
            <p className="text-xs text-slate-500 mt-2">
              Last checked: {new Date(profile.metadata.last_scraped_at).toLocaleString()}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Stats - Professional Layout */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Total Dilution Card */}
        <div className="md:col-span-2 bg-white border border-slate-200 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <TrendingDown className="h-5 w-5 text-blue-600" />
              <h3 className="text-sm font-semibold text-slate-600">Total Potential Dilution</h3>
            </div>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-50 rounded-lg transition-colors disabled:opacity-50"
              title="Refresh from SEC EDGAR"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
          </div>
          
          <div>
            <div className="flex items-baseline gap-2 mb-2">
              <span className="text-5xl font-bold text-blue-600">
                {Number(dilution_analysis.total_potential_dilution_pct).toFixed(1)}%
              </span>
            </div>
            <p className="text-sm text-slate-600">
              {(Number(dilution_analysis.total_potential_new_shares) / 1_000_000).toFixed(1)}M potential new shares
            </p>
            <p className="text-xs text-slate-500 mt-3">
              Based on current price: ${profile.current_price ? Number(profile.current_price).toFixed(2) : 'N/A'}
            </p>
          </div>
        </div>

        {/* Breakdown Cards Compactas */}
        <div className="bg-white border border-slate-200 rounded-lg p-3">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Warrants</p>
          <p className="text-xl font-bold text-slate-900">
            {(Number(dilution_analysis.warrant_shares) / 1_000_000).toFixed(1)}M
          </p>
          <p className="text-xs text-slate-500">shares</p>
        </div>

        <div className="bg-white border border-slate-200 rounded-lg p-3">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">ATM + Shelf</p>
          <p className="text-xl font-bold text-slate-900">
            {((Number(dilution_analysis.atm_potential_shares) + Number(dilution_analysis.shelf_potential_shares)) / 1_000_000).toFixed(1)}M
          </p>
          <p className="text-xs text-slate-500">shares</p>
        </div>
      </div>

      {/* Cards Grid - Máximo 2 columnas */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Warrants */}
        {profile.warrants.length > 0 && (
          <WarrantsCard warrants={profile.warrants} />
        )}

        {/* ATM Offerings */}
        {profile.atm_offerings.length > 0 && (
          <ATMCard offerings={profile.atm_offerings} />
        )}

        {/* Shelf Registrations */}
        {profile.shelf_registrations.length > 0 && (
          <ShelfCard registrations={profile.shelf_registrations} />
        )}
      </div>

      {/* Completed Offerings Table - Full Width */}
      {profile.completed_offerings.length > 0 && (
        <div className="lg:col-span-2">
          <CompletedOfferingsCard offerings={profile.completed_offerings} />
        </div>
      )}

      {/* Metadata Footer */}
      <div className="flex items-center justify-between text-xs text-slate-500 pt-4 border-t border-slate-200">
        <div className="flex items-center gap-4">
          <span>
            Last scraped: {new Date(profile.metadata.last_scraped_at).toLocaleString()}
          </span>
          {profile.metadata.source_filings.length > 0 && (
            <span>
              {profile.metadata.source_filings.length} filings analyzed
            </span>
          )}
        </div>
        {cached && cache_age_seconds !== undefined && (
          <span className="text-slate-400">
            Cached ({cache_age_seconds < 3600 ? `${Math.floor(cache_age_seconds / 60)}m` : `${Math.floor(cache_age_seconds / 3600)}h`} old)
          </span>
        )}
      </div>
    </div>
  );
}

// =====================================================
// EDUCATIONAL TOOLTIPS
// =====================================================

function EducationalTooltip({ type }: { type: 'warrant' | 'atm' | 'shelf' | 'completed' }) {
  const tooltips = {
    warrant: {
      title: "Warrants Outstanding",
      description: "Right to purchase shares at a fixed exercise price before expiration",
      impact: "🔴 Immediate dilution when exercised",
      filing: "Found in: 10-K, 10-Q, 424B5, S-1"
    },
    atm: {
      title: "At-The-Market Offering (424B5)",
      description: "Company can issue shares on the open market anytime up to $ amount",
      impact: "🟡 Low immediate impact - Used over time",
      filing: "Filed after shelf receives EFFECT"
    },
    shelf: {
      title: "Shelf Registration (S-3/S-1)",
      description: "Allows company to raise funds over next 3 years up to registered amount",
      impact: "🟢 No immediate impact until used",
      filing: "Requires EFFECT before use"
    },
    completed: {
      title: "Completed Offerings",
      description: "Historical offerings that have been priced and closed",
      impact: "✅ Already executed - Past dilution",
      filing: "Disclosed in 424B5, 8-K, 10-Q"
    }
  };

  const tooltip = tooltips[type];
  const [show, setShow] = useState(false);

  return (
    <div className="relative inline-block">
      <button
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        className="p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded transition-colors"
        type="button"
      >
        <Info className="h-3.5 w-3.5" />
      </button>
      
      {show && (
        <div className="absolute z-50 left-0 top-full mt-1 w-72 bg-slate-900 text-white text-xs rounded-lg shadow-xl p-3 pointer-events-none">
          <div className="font-semibold mb-1">{tooltip.title}</div>
          <div className="text-slate-300 mb-2">{tooltip.description}</div>
          <div className="text-slate-400 mb-1">{tooltip.impact}</div>
          <div className="text-slate-500 text-[10px]">{tooltip.filing}</div>
          {/* Arrow */}
          <div className="absolute -top-1 left-4 w-2 h-2 bg-slate-900 transform rotate-45" />
        </div>
      )}
    </div>
  );
}

// =====================================================
// WARRANTS CARD (Formato Vertical Detallado)
// =====================================================

function WarrantsCard({ warrants }: { warrants: Warrant[] }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      {warrants.map((warrant, idx) => {
        const issueDate = warrant.issue_date ? new Date(warrant.issue_date) : null;
        const title = issueDate 
          ? `${issueDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })} Warrants`
          : 'Warrants';
        
        return (
          <div key={idx} className={idx > 0 ? 'border-t border-slate-200' : ''}>
            {/* Header Compacto con Ícono Educativo */}
            <div className="bg-purple-50 px-4 py-2 border-l-2 border-purple-500 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-purple-600" />
                <h3 className="text-sm font-bold text-slate-900">{title}</h3>
              </div>
              <EducationalTooltip type="warrant" />
            </div>

            {/* Grid Compacto 2 Columnas */}
            <div className="p-4">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <div>
                  <span className="text-slate-500">Outstanding:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {warrant.outstanding ? Number(warrant.outstanding).toLocaleString() : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Exercise Price:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {warrant.exercise_price ? `$${Number(warrant.exercise_price).toFixed(2)}` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Total Issued:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {warrant.potential_new_shares ? Number(warrant.potential_new_shares).toLocaleString() : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Issue Date:</span>
                  <span className="ml-2 text-slate-900">
                    {warrant.issue_date ? new Date(warrant.issue_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Expiration:</span>
                  <span className="ml-2 text-slate-900">
                    {warrant.expiration_date ? new Date(warrant.expiration_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '—'}
                  </span>
                </div>
                {warrant.notes && (
                  <div className="col-span-2">
                    <span className="text-slate-500">Notes:</span>
                    <span className="ml-2 text-slate-700">{warrant.notes}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// =====================================================
// ATM OFFERINGS CARD (Formato Vertical Detallado)
// =====================================================

function ATMCard({ offerings }: { offerings: ATMOffering[] }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      {offerings.map((offering, idx) => {
        const filingDate = offering.filing_date ? new Date(offering.filing_date) : null;
        const title = filingDate
          ? `${filingDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })} ATM`
          : 'ATM Offering';

        return (
          <div key={idx} className={idx > 0 ? 'border-t border-slate-200' : ''}>
            {/* Header Compacto con Ícono Educativo */}
            <div className="bg-blue-50 px-4 py-2 border-l-2 border-blue-500 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Waves className="h-4 w-4 text-blue-600" />
                <h3 className="text-sm font-bold text-slate-900">{title}</h3>
              </div>
              <EducationalTooltip type="atm" />
            </div>

            {/* Grid Compacto */}
            <div className="p-4">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <div>
                  <span className="text-slate-500">Total Capacity:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {offering.total_capacity ? `$${(Number(offering.total_capacity) / 1_000_000).toFixed(1)}M` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Remaining:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {offering.remaining_capacity ? `$${(Number(offering.remaining_capacity) / 1_000_000).toFixed(1)}M` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Potential Shares:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {offering.potential_shares_at_current_price ? `${(Number(offering.potential_shares_at_current_price) / 1_000_000).toFixed(1)}M` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Filing Date:</span>
                  <span className="ml-2 text-slate-900">
                    {offering.filing_date ? new Date(offering.filing_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '—'}
                  </span>
                </div>
                {offering.placement_agent && (
                  <div className="col-span-2">
                    <span className="text-slate-500">Agent:</span>
                    <span className="ml-2 text-slate-900">{offering.placement_agent}</span>
                  </div>
                )}
                {offering.filing_url && (
                  <div className="col-span-2 mt-2">
                    <a
                      href={offering.filing_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
                    >
                      View Filing <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// =====================================================
// SHELF REGISTRATIONS CARD (Formato Vertical Detallado)
// =====================================================

function ShelfCard({ registrations }: { registrations: ShelfRegistration[] }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      {registrations.map((shelf, idx) => {
        const filingDate = shelf.filing_date ? new Date(shelf.filing_date) : null;
        const title = filingDate
          ? `${filingDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })} Shelf`
          : 'Shelf Registration';

        return (
          <div key={idx} className={idx > 0 ? 'border-t border-slate-200' : ''}>
            {/* Header Compacto con Ícono Educativo */}
            <div className="bg-orange-50 px-4 py-2 border-l-2 border-orange-500 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Archive className="h-4 w-4 text-orange-600" />
                <h3 className="text-sm font-bold text-slate-900">{title}</h3>
                {shelf.is_baby_shelf && (
                  <span className="text-xs px-1.5 py-0.5 bg-orange-200 text-orange-800 rounded font-medium">
                    Baby Shelf
                  </span>
                )}
              </div>
              <EducationalTooltip type="shelf" />
            </div>

            {/* Grid Compacto */}
            <div className="p-4">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <div>
                  <span className="text-slate-500">Registration:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {shelf.registration_statement || '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Total Capacity:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {shelf.total_capacity ? `$${(Number(shelf.total_capacity) / 1_000_000).toFixed(1)}M` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Remaining:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {shelf.remaining_capacity ? `$${(Number(shelf.remaining_capacity) / 1_000_000).toFixed(1)}M` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Filing Date:</span>
                  <span className="ml-2 text-slate-900">
                    {shelf.filing_date ? new Date(shelf.filing_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Expiration:</span>
                  <span className="ml-2 text-slate-900">
                    {shelf.expiration_date ? new Date(shelf.expiration_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '~3 years'}
                  </span>
                </div>
                {shelf.filing_url && (
                  <div className="col-span-2 mt-2">
                    <a
                      href={shelf.filing_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
                    >
                      View Filing <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// =====================================================
// COMPLETED OFFERINGS CARD
// =====================================================

function CompletedOfferingsCard({ offerings }: { offerings: CompletedOffering[] }) {
  // Sort by date (most recent first)
  const sortedOfferings = [...offerings].sort((a, b) => {
    if (!a.offering_date || !b.offering_date) return 0;
    return new Date(b.offering_date).getTime() - new Date(a.offering_date).getTime();
  });

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <h4 className="text-sm font-bold text-slate-900">Completed Offerings</h4>
          <span className="text-xs font-medium px-2 py-0.5 bg-green-100 text-green-700 rounded">
            {offerings.length}
          </span>
        </div>
        <EducationalTooltip type="completed" />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              <th className="text-left py-2 px-3 text-slate-600 font-semibold">Date</th>
              <th className="text-left py-2 px-3 text-slate-600 font-semibold">Type</th>
              <th className="text-right py-2 px-3 text-slate-600 font-semibold">Shares</th>
              <th className="text-right py-2 px-3 text-slate-600 font-semibold">Price</th>
              <th className="text-right py-2 px-3 text-slate-600 font-semibold">Amount Raised</th>
            </tr>
          </thead>
          <tbody>
            {sortedOfferings.map((offering, idx) => (
              <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="py-2 px-3 text-slate-700 whitespace-nowrap">
                  {offering.offering_date ? new Date(offering.offering_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : 'N/A'}
                </td>
                <td className="py-2 px-3 text-slate-700">
                  {offering.offering_type || 'N/A'}
                </td>
                <td className="py-2 px-3 text-right font-medium text-slate-900 tabular-nums">
                  {offering.shares_issued ? `${(Number(offering.shares_issued) / 1_000_000).toFixed(2)}M` : 'N/A'}
                </td>
                <td className="py-2 px-3 text-right text-slate-700 tabular-nums">
                  {offering.price_per_share ? `$${Number(offering.price_per_share).toFixed(2)}` : 'N/A'}
                </td>
                <td className="py-2 px-3 text-right font-semibold text-green-600 tabular-nums">
                  {offering.amount_raised ? `$${(Number(offering.amount_raised) / 1_000_000).toFixed(1)}M` : 'N/A'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

