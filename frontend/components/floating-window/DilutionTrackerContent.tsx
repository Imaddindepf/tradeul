'use client';

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { 
  Search, 
  TrendingUp, 
  BarChart3, 
  Clock, 
  Building2, 
  FileText, 
  DollarSign, 
  RefreshCw, 
  AlertTriangle 
} from "lucide-react";
import { HoldersTable } from "@/app/(dashboard)/dilution-tracker/_components/HoldersTable";
import { FilingsTable } from "@/app/(dashboard)/dilution-tracker/_components/FilingsTable";
import { CashRunwayChart } from "@/app/(dashboard)/dilution-tracker/_components/CashRunwayChart";
import { DilutionHistoryChart } from "@/app/(dashboard)/dilution-tracker/_components/DilutionHistoryChart";
import { FinancialsTable } from "@/app/(dashboard)/dilution-tracker/_components/FinancialsTable";
import { SECDilutionSection } from "@/app/(dashboard)/dilution-tracker/_components/SECDilutionSection";
import { getTickerAnalysis, validateTicker, type TickerAnalysis } from "@/lib/dilution-api";

type TabType = "overview" | "dilution" | "holders" | "filings" | "financials";

export function DilutionTrackerContent() {
  const searchParams = useSearchParams();
  
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>("dilution");
  const [loading, setLoading] = useState(false);
  const [tickerData, setTickerData] = useState<TickerAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [descriptionExpanded, setDescriptionExpanded] = useState(false);

  // Cargar ticker y tab desde URL al montar el componente
  useEffect(() => {
    const tickerFromUrl = searchParams.get('ticker');
    const tabFromUrl = searchParams.get('tab') as TabType;
    
    if (tickerFromUrl && !selectedTicker) {
      const ticker = tickerFromUrl.toUpperCase();
      setSearchQuery(ticker);
      setSelectedTicker(ticker);
      if (tabFromUrl && ["dilution", "holders", "filings", "financials"].includes(tabFromUrl)) {
        setActiveTab(tabFromUrl);
      }
      fetchTickerData(ticker);
    }
  }, [searchParams, selectedTicker]);

  const fetchTickerData = async (ticker: string) => {
    if (!validateTicker(ticker)) {
      setError("Ticker inválido");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await getTickerAnalysis(ticker);
      setTickerData(data);
      setSelectedTicker(ticker);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar datos");
      setTickerData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      fetchTickerData(searchQuery.trim().toUpperCase());
    }
  };

  const tabs: { id: TabType; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: "dilution", label: "Dilución", icon: TrendingUp },
    { id: "holders", label: "Holders", icon: Building2 },
    { id: "filings", label: "Filings", icon: FileText },
    { id: "financials", label: "Financieros", icon: DollarSign },
  ];

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Search Bar */}
      <div className="p-4 border-b border-slate-200 bg-slate-50">
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value.toUpperCase())}
              placeholder="Buscar ticker (ej: AAPL, TSLA)"
              className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            Buscar
          </button>
        </form>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mx-4 mt-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700">
          <AlertTriangle className="w-5 h-5" />
          <span>{error}</span>
        </div>
      )}

      {/* Content - flex-1 para ocupar espacio restante */}
      {selectedTicker && tickerData ? (
        <div className="flex-1 overflow-auto min-h-0">
          {/* Company Header */}
          <div className="bg-white border-b border-slate-200 p-4">
            {/* Company Name */}
            <h2 className="text-xl font-bold text-slate-900 mb-2">
              {loading ? "Loading..." : tickerData?.summary?.company_name || selectedTicker}
            </h2>

            {/* Info Lines */}
            <div className="space-y-1 text-sm">
              <div className="text-slate-600">
                <span className="font-medium">Sector:</span> {tickerData?.summary?.sector || "..."} 
                <span className="mx-2">•</span>
                <span className="font-medium">Industry:</span> {tickerData?.summary?.industry || "..."}
                {tickerData?.summary?.exchange && (
                  <>
                    <span className="mx-2">•</span>
                    <span className="font-medium">Exchange:</span> {tickerData.summary.exchange}
                  </>
                )}
              </div>

              <div className="text-slate-700 font-medium">
                <span className="text-slate-500">Mkt Cap & EV:</span> {tickerData?.summary?.market_cap ? `$${(tickerData.summary.market_cap / 1_000_000_000).toFixed(2)}B` : '--'}
                <span className="mx-3">•</span>
                <span className="text-slate-500">Float & OS:</span> {tickerData?.summary?.float_shares && tickerData?.summary?.shares_outstanding ? `${(tickerData.summary.float_shares / 1_000_000).toFixed(1)}M / ${(tickerData.summary.shares_outstanding / 1_000_000).toFixed(1)}M` : '--'}
                <span className="mx-3">•</span>
                <span className="text-slate-500">Inst Own:</span> {tickerData?.summary?.institutional_ownership ? `${tickerData.summary.institutional_ownership.toFixed(1)}%` : '--'}
              </div>
            </div>

            {/* Description */}
            {tickerData?.summary?.description && (
              <div className="mt-3 pt-3 border-t border-slate-200">
                <p className={`text-sm text-slate-600 leading-relaxed ${
                  !descriptionExpanded ? 'line-clamp-2' : ''
                }`}>
                  {tickerData.summary.description}
                </p>
                <button
                  onClick={() => setDescriptionExpanded(!descriptionExpanded)}
                  className="mt-1 text-xs text-blue-600 hover:text-blue-800 font-medium"
                >
                  {descriptionExpanded ? '(show less)' : '(show more)'}
                </button>
              </div>
            )}

            {/* Links */}
            <div className="flex gap-4 mt-3">
              <a href={`https://finviz.com/quote.ashx?t=${selectedTicker}`} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:text-blue-800 font-medium">
                Finviz →
              </a>
              <a href={`https://finance.yahoo.com/quote/${selectedTicker}`} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:text-blue-800 font-medium">
                Yahoo →
              </a>
              {tickerData?.summary?.homepage_url && (
                <a href={tickerData.summary.homepage_url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:text-blue-800 font-medium">
                  Website →
                </a>
              )}
            </div>
          </div>

          {/* Tabs */}
          <div className="border-b border-slate-200 bg-white sticky top-0 z-10">
            <div className="flex gap-1 px-4">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`
                      px-4 py-2 flex items-center gap-2 text-sm font-medium
                      border-b-2 transition-colors
                      ${
                        activeTab === tab.id
                          ? "border-blue-600 text-blue-600 bg-blue-50"
                          : "border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                      }
                    `}
                  >
                    <Icon className="w-4 h-4" />
                    {tab.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Tab Content */}
          <div className="p-4">
            {activeTab === "dilution" && (
              <div className="space-y-6">
                <SECDilutionSection ticker={selectedTicker} />
                <DilutionHistoryChart data={tickerData?.dilution_history || null} loading={loading} />
                <CashRunwayChart data={tickerData?.cash_runway || null} loading={loading} />
              </div>
            )}

            {activeTab === "holders" && (
              <HoldersTable holders={tickerData?.holders || []} loading={loading} />
            )}

            {activeTab === "filings" && (
              <FilingsTable filings={tickerData?.filings || []} loading={loading} />
            )}

            {activeTab === "financials" && (
              <FinancialsTable financials={tickerData?.financials || []} loading={loading} />
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-slate-500">
          <div className="text-center">
            <BarChart3 className="w-16 h-16 mx-auto mb-4 text-slate-300" />
            <p className="text-lg font-medium">Busca un ticker para comenzar</p>
            <p className="text-sm mt-2">Ingresa un símbolo de acción para ver su análisis de dilución</p>
          </div>
        </div>
      )}
    </div>
  );
}

