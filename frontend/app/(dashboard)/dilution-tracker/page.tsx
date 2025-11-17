"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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
import { HoldersTable } from "./_components/HoldersTable";
import { FilingsTable } from "./_components/FilingsTable";
import { CashRunwayChart } from "./_components/CashRunwayChart";
import { DilutionHistoryChart } from "./_components/DilutionHistoryChart";
import { FinancialsTable } from "./_components/FinancialsTable";
import { SECDilutionSection } from "./_components/SECDilutionSection";
import { getTickerAnalysis, validateTicker, type TickerAnalysis } from "@/lib/dilution-api";

type TabType = "overview" | "dilution" | "holders" | "filings" | "financials";

export default function DilutionTrackerPage() {
  const router = useRouter();
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
    
    if (tickerFromUrl) {
      const ticker = tickerFromUrl.toUpperCase();
      // Solo actualizar si el ticker es diferente al actual
      if (ticker !== selectedTicker) {
        setSearchQuery(ticker);
        setSelectedTicker(ticker);
        if (tabFromUrl && ["dilution", "holders", "filings", "financials"].includes(tabFromUrl)) {
          setActiveTab(tabFromUrl);
        }
        fetchTickerData(ticker);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    const trimmedQuery = searchQuery.trim();
    if (!trimmedQuery) {
      setError("Por favor ingresa un ticker");
      return;
    }
    
    const ticker = trimmedQuery.toUpperCase();
    
    // Si es el mismo ticker, no hacer nada
    if (ticker === selectedTicker) {
      return;
    }
    
    setError(null);
    setLoading(true);
    
    try {
      // Validar ticker primero
      const isValid = await validateTicker(ticker);
      
      if (!isValid) {
        setError(`Ticker ${ticker} no encontrado en el universo. Solo tickers del universo de Polygon están disponibles.`);
        setLoading(false);
        setSelectedTicker(null);
        setTickerData(null);
        return;
      }
      
      setSelectedTicker(ticker);
      setActiveTab("dilution");
      
      // Actualizar URL sin recargar la página
      router.push(`/dilution-tracker?ticker=${ticker}&tab=dilution`, { scroll: false });
      
      await fetchTickerData(ticker);
    } catch (err) {
      console.error("Error en handleSearch:", err);
      setError(`Error al buscar ${ticker}. Por favor intenta de nuevo.`);
      setLoading(false);
    }
  };

  const fetchTickerData = async (ticker: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getTickerAnalysis(ticker);
      if (!data) {
        setError(`No data available for ${ticker}`);
      }
      setTickerData(data);
    } catch (error) {
      console.error("Error fetching ticker data:", error);
      setError(`Error loading data for ${ticker}`);
      setTickerData(null);
    } finally {
      setLoading(false);
    }
  };

  const tabs = [
    { id: "dilution", label: "Dilution", icon: TrendingUp },
    { id: "holders", label: "Holders", icon: Building2 },
    { id: "filings", label: "Filings", icon: FileText },
    { id: "financials", label: "Financials", icon: DollarSign },
  ];

  return (
    <main className="min-h-screen bg-white">
      {/* Header con búsqueda - igual que escáner */}
      <header className="border-b border-slate-200 bg-white sticky top-0 z-50 shadow-sm">
        <div className="w-full px-6 py-4">
          <div className="flex items-center justify-between gap-6">
            <div className="flex-shrink-0">
              <h1 className="text-2xl font-bold text-slate-900">Dilution Tracker</h1>
              <p className="text-sm text-slate-600 mt-0.5">
                Análisis de dilución y cash runway
              </p>
            </div>
            
            {/* Search Bar en Header */}
            <form onSubmit={handleSearch} className="flex-1 max-w-md">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleSearch(e as any);
                    }
                  }}
                  placeholder="Buscar ticker (ej: AAPL, TSLA)..."
                  className="w-full pl-10 pr-4 py-2 text-sm border border-slate-200 rounded-lg 
                           focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none
                           bg-white text-slate-900 placeholder:text-slate-400 transition-all"
                  disabled={loading}
                />
                {loading && (
                  <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
                    <RefreshCw className="h-4 w-4 text-blue-600 animate-spin" />
                  </div>
                )}
              </div>
            </form>

            {selectedTicker && (
              <div className="flex items-center gap-3 flex-shrink-0">
                <div className="px-3 py-1.5 bg-blue-100 text-blue-700 text-sm font-medium rounded-lg">
                  {selectedTicker}
                </div>
                <button
                  onClick={() => fetchTickerData(selectedTicker)}
                  disabled={loading}
                  className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-slate-700
                           bg-slate-50 hover:bg-slate-100 border border-slate-200
                           rounded-lg transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="w-full px-6 py-6">
        {/* Error Message */}
        {error && (
          <div className="max-w-5xl mx-auto mb-6">
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-red-600 mt-0.5 shrink-0" />
                <div>
                  <h4 className="font-semibold text-slate-900 mb-1">Error</h4>
                  <p className="text-sm text-slate-600">{error}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {!selectedTicker ? (
          // Landing view
          <div className="max-w-5xl mx-auto">
            <div className="text-center py-16 space-y-6">
              <div className="flex justify-center">
                <div className="p-6 bg-blue-50 rounded-2xl">
                  <BarChart3 className="h-16 w-16 text-blue-600" />
                </div>
              </div>
              <div className="space-y-3">
                <h2 className="text-3xl font-bold text-slate-900">
                  Start Analyzing
                </h2>
                <p className="text-lg text-slate-600 max-w-2xl mx-auto">
                  Enter a ticker symbol in the search bar above to view comprehensive dilution analysis, cash runway projections, and institutional ownership data
                </p>
              </div>

              {/* Features Grid */}
              <div className="grid md:grid-cols-3 gap-6 mt-12 pt-12">
                <div className="bg-white rounded-xl p-6 border border-slate-200">
                  <div className="h-10 w-10 bg-blue-50 rounded-lg flex items-center justify-center mb-3">
                    <BarChart3 className="h-5 w-5 text-blue-600" />
                  </div>
                  <h3 className="text-base font-semibold text-slate-900 mb-2">
                    Dilution Analysis
                  </h3>
                  <p className="text-sm text-slate-600 leading-relaxed">
                    Track historical share dilution and outstanding shares progression
                  </p>
                </div>

                <div className="bg-white rounded-xl p-6 border border-slate-200">
                  <div className="h-10 w-10 bg-green-50 rounded-lg flex items-center justify-center mb-3">
                    <Clock className="h-5 w-5 text-green-600" />
                  </div>
                  <h3 className="text-base font-semibold text-slate-900 mb-2">
                    Cash Runway
                  </h3>
                  <p className="text-sm text-slate-600 leading-relaxed">
                    Calculate burn rate and estimate cash runway
                  </p>
                </div>

                <div className="bg-white rounded-xl p-6 border border-slate-200">
                  <div className="h-10 w-10 bg-purple-50 rounded-lg flex items-center justify-center mb-3">
                    <TrendingUp className="h-5 w-5 text-purple-600" />
                  </div>
                  <h3 className="text-base font-semibold text-slate-900 mb-2">
                    Institutional Holdings
                  </h3>
                  <p className="text-sm text-slate-600 leading-relaxed">
                    Monitor 13F filings and ownership patterns
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          // Analysis view
          <div className="space-y-6">
            {/* Company Header - Compacto y Profesional */}
            <div className="bg-white border-b border-slate-200 p-4">
              {/* Company Name */}
              <h2 className="text-xl font-bold text-slate-900 mb-2">
                {loading ? "Loading..." : tickerData?.summary?.company_name || selectedTicker}
              </h2>

              {/* Info Lines - Compacto */}
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
            <div className="bg-white border border-slate-200">
              {/* Tabs Navigation */}
              <div className="flex border-b border-slate-200 overflow-x-auto bg-slate-50">
                {tabs.map((tab) => {
                  const Icon = tab.icon;
                  const isActive = activeTab === tab.id;
                  
                  return (
                    <button
                      key={tab.id}
                      onClick={() => {
                        const newTab = tab.id as TabType;
                        setActiveTab(newTab);
                        if (selectedTicker) {
                          router.push(`/dilution-tracker?ticker=${selectedTicker}&tab=${newTab}`, { scroll: false });
                        }
                      }}
                      className={`
                        flex items-center gap-2 px-6 py-4 text-sm font-medium whitespace-nowrap
                        border-b-2 transition-all duration-200
                        ${isActive 
                          ? 'border-blue-600 text-blue-600 bg-blue-50' 
                          : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                        }
                      `}
                    >
                      <Icon className="h-4 w-4" />
                      {tab.label}
                    </button>
                  );
                })}
              </div>

              {/* Tab Content */}
              <div className="p-4">
                {activeTab === "dilution" && <DilutionTab data={tickerData} loading={loading} ticker={selectedTicker} />}
                {activeTab === "holders" && <HoldersTab data={tickerData} loading={loading} />}
                {activeTab === "filings" && <FilingsTab data={tickerData} loading={loading} />}
                {activeTab === "financials" && <FinancialsTab data={tickerData} loading={loading} />}
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

// Tab Components

function DilutionTab({ data, loading, ticker }: { data: TickerAnalysis | null; loading: boolean; ticker: string }) {
  return (
    <div className="space-y-6">
      {/* Cash Runway */}
      <div>
        <CashRunwayChart data={data?.cash_runway || null} loading={loading} />
      </div>

      {/* Dilution History */}
      <div>
        <DilutionHistoryChart data={data?.dilution_history || null} loading={loading} />
      </div>

      {/* SEC Dilution Profile - Warrants, ATM, Shelf, Completed Offerings */}
      {!loading && (
        <>
          <div className="border-t border-slate-200 pt-6">
            <div className="mb-4">
              <h3 className="text-base font-semibold text-slate-900 mb-1">
                SEC Dilution Profile
              </h3>
              <p className="text-sm text-slate-600">
                Warrants, ATM offerings, shelf registrations, and completed offerings extracted from SEC EDGAR filings
              </p>
            </div>
            <SECDilutionSection ticker={ticker} />
          </div>
        </>
      )}
    </div>
  );
}

function HoldersTab({ data, loading }: { data: TickerAnalysis | null; loading: boolean }) {
  return (
    <div>
      <HoldersTable holders={data?.holders || []} loading={loading} />
    </div>
  );
}

function FilingsTab({ data, loading }: { data: TickerAnalysis | null; loading: boolean }) {
  return (
    <div>
      <FilingsTable filings={data?.filings || []} loading={loading} />
    </div>
  );
}

function FinancialsTab({ data, loading }: { data: TickerAnalysis | null; loading: boolean }) {
  return (
    <div>
      <FinancialsTable financials={data?.financials || []} loading={loading} />
    </div>
  );
}

