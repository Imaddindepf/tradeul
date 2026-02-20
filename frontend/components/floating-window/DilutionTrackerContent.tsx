'use client';

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from 'react-i18next';
import { useSearchParams } from "next/navigation";
import { TickerSearch } from '@/components/common/TickerSearch';
import { HoldersTable } from "@/app/(dashboard)/dilution-tracker/_components/HoldersTable";
import { FilingsTable } from "@/app/(dashboard)/dilution-tracker/_components/FilingsTable";
import { CashRunwayChart } from "@/app/(dashboard)/dilution-tracker/_components/CashRunwayChart";
import { DilutionHistoryChart } from "@/app/(dashboard)/dilution-tracker/_components/DilutionHistoryChart";
import { FinancialsTable } from "@/app/(dashboard)/dilution-tracker/_components/FinancialsTable";
import { SECDilutionSection } from "@/app/(dashboard)/dilution-tracker/_components/SECDilutionSection";
import { AITerminalWindow } from "@/components/floating-window/AITerminalWindow";
import { useFloatingWindow, useWindowState } from "@/contexts/FloatingWindowContext";
import { useDilutionJobNotifications } from "@/hooks/useDilutionJobNotifications";

interface DilutionWindowState {
  ticker?: string;
  tab?: TabType;
  [key: string]: unknown;
}
import {
  getTickerAnalysis,
  validateTicker,
  getCashPosition,
  checkSECCache,
  getSharesHistory,
  type TickerAnalysis,
  type CashRunwayData,
  type SECDilutionProfileResponse,
  type SECCacheCheckResult,
  type SharesHistoryData
} from "@/lib/dilution-api";

type TabType = "overview" | "dilution" | "holders" | "filings" | "financials";

interface DilutionTrackerContentProps {
  initialTicker?: string;
}

interface DilutionTrackerContentProps {
  initialTicker?: string;
}

export function DilutionTrackerContent({ initialTicker }: DilutionTrackerContentProps = {}) {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { openWindow, closeWindow } = useFloatingWindow();
  const { state: windowState, updateState: updateWindowState } = useWindowState<DilutionWindowState>();

  // Use persisted state
  const savedTicker = windowState.ticker || initialTicker || '';

  // Estados separados: input vs ticker seleccionado
  const [inputValue, setInputValue] = useState(savedTicker);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(savedTicker || null);
  const [activeTab, setActiveTab] = useState<TabType>(windowState.tab || "dilution");

  // Track if auto-load has been done
  const autoLoadedRef = useRef(false);

  // Persist state changes (including when ticker is cleared)
  useEffect(() => {
    // Always persist to ensure clearing ticker also clears persisted state
    updateWindowState({ ticker: selectedTicker || '', tab: activeTab });
  }, [selectedTicker, activeTab, updateWindowState]);

  const [loading, setLoading] = useState(false);
  const [tickerData, setTickerData] = useState<TickerAnalysis | null>(null);
  const [cashRunwayData, setCashRunwayData] = useState<CashRunwayData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [descriptionExpanded, setDescriptionExpanded] = useState(false);
  const [jobNotification, setJobNotification] = useState<{ ticker: string; message: string } | null>(null);
  const [pendingJobs, setPendingJobs] = useState<Set<string>>(new Set());

  // Estado para datos SEC (separado del tickerData general)
  const [secCacheData, setSecCacheData] = useState<SECDilutionProfileResponse | null>(null);
  const [secJobStatus, setSecJobStatus] = useState<'queued' | 'processing' | 'none' | 'unknown'>('none');

  // Historical shares desde SEC EDGAR
  const [sharesHistory, setSharesHistory] = useState<any>(null);

  // ID de la ventana de terminal AI (para poder cerrarla cuando lleguen datos)
  const [terminalWindowId, setTerminalWindowId] = useState<string | null>(null);

  // Función para abrir la terminal AI en una ventana flotante independiente
  const openAITerminal = useCallback((ticker: string, companyName?: string) => {
    const windowId = openWindow({
      title: `AI Analysis: ${ticker}`,
      content: (
        <AITerminalWindow
          ticker={ticker}
          companyName={companyName}
          onComplete={(success) => {
          }}
        />
      ),
      width: 600,
      height: 500,
      x: Math.max(50, window.innerWidth - 650),
      y: 100,
      minWidth: 400,
      minHeight: 300,
    });
    setTerminalWindowId(windowId);
    return windowId;
  }, [openWindow]);

  // Callback cuando un job de scraping completa
  const handleJobComplete = useCallback(async (ticker: string) => {

    // Remover de pending
    setPendingJobs(prev => {
      const next = new Set(prev);
      next.delete(ticker);
      return next;
    });

    // Si el ticker completado es el que estamos viendo
    if (ticker.toUpperCase() === selectedTicker?.toUpperCase()) {

      // Re-chequear caché (ahora debería tener datos)
      try {
        const cacheResult = await checkSECCache(ticker, false);

        if (cacheResult.status === 'cached' && cacheResult.data) {
          setSecCacheData(cacheResult.data);
          setSecJobStatus('none');
          // La terminal AI sigue corriendo independientemente - no la cerramos
        } else {
          setSecJobStatus('none');
        }
      } catch (err) {
        setSecJobStatus('none');
      }

    } else {
      // Si es otro ticker, mostrar notificación
      setJobNotification({
        ticker,
        message: `${ticker} analysis ready!`
      });
      setTimeout(() => setJobNotification(null), 5000);
    }
  }, [selectedTicker]);

  // Hook para notificaciones de jobs via WebSocket
  const {
    isConnected: wsConnected,
    enqueueJob,
    getJobStatus
  } = useDilutionJobNotifications({
    tickers: selectedTicker ? [selectedTicker] : [],
    onJobComplete: handleJobComplete,
    onJobFailed: (ticker, error) => {
      setPendingJobs(prev => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    },
    enabled: true,
  });

  // Cargar ticker y tab desde URL o prop initialTicker al montar el componente
  useEffect(() => {
    // Prioridad: initialTicker > URL param
    if (initialTicker && !selectedTicker) {
      fetchTickerData(initialTicker);
      return;
    }

    const tickerFromUrl = searchParams.get('ticker');
    const tabFromUrl = searchParams.get('tab') as TabType;

    if (tickerFromUrl && !selectedTicker) {
      const ticker = tickerFromUrl.toUpperCase();
      setInputValue(ticker);
      setSelectedTicker(ticker);
      if (tabFromUrl && ["dilution", "holders", "filings", "financials"].includes(tabFromUrl)) {
        setActiveTab(tabFromUrl);
      }
      fetchTickerData(ticker);
    }
  }, [searchParams, selectedTicker, initialTicker]);

  const fetchTickerData = async (ticker: string, options?: { skipEnqueue?: boolean }) => {
    if (!validateTicker(ticker)) {
      setError(t('dilution.invalidTicker'));
      return;
    }

    // Reset ALL state at the start of each search
    setLoading(true);
    setError(null);
    setCashRunwayData(null);
    setTickerData(null);
    setSecCacheData(null);
    setSharesHistory(null);
    setSecJobStatus('none');
    setSelectedTicker(ticker);

    // Cerrar terminal AI anterior si existe
    if (terminalWindowId) {
      closeWindow(terminalWindowId);
      setTerminalWindowId(null);
    }

    // 🆕 PASO 1: Chequear caché SEC (NO BLOQUEA)
    // Este es el cambio clave - primero chequeamos si hay datos cacheados

    try {
      const cacheResult = await checkSECCache(ticker, !options?.skipEnqueue);

      if (cacheResult.status === 'cached' && cacheResult.data) {
        // ✅ HAY DATOS EN CACHÉ - mostrar inmediatamente
        setSecCacheData(cacheResult.data);
        setSecJobStatus('none');
      } else {
        // ❌ NO HAY CACHÉ - abrir terminal AI en ventana flotante
        setSecCacheData(null);
        setSecJobStatus(cacheResult.job_status || 'none');

        // Abrir terminal AI en ventana flotante independiente
        if (!options?.skipEnqueue) {
          openAITerminal(ticker);
        }

        // Marcar como pending para WebSocket
        if (cacheResult.job_status === 'queued' || cacheResult.job_status === 'processing') {
          setPendingJobs(prev => new Set(prev).add(ticker));
        }
      }
    } catch (cacheErr) {
      // Fallback: abrir terminal AI
      if (!options?.skipEnqueue) {
        openAITerminal(ticker);
      }
    }

    // 🆕 PASO 2: Cargar datos generales (summary, holders, etc.)
    // Esto es independiente del caché SEC
    try {
      const data = await getTickerAnalysis(ticker);
      setTickerData(data);

      // Try to get cash runway if not present
      if (!data?.cash_runway) {
        try {
          const cashData = await getCashPosition(ticker);
          setCashRunwayData(cashData);
        } catch (cashErr) {
          console.warn('Could not fetch cash position:', cashErr);
        }
      }

      // Get historical shares from SEC EDGAR (gratuito)
      try {
        const sharesData = await getSharesHistory(ticker);
        if (sharesData && sharesData.history) {
          setSharesHistory(sharesData);
        }
      } catch (sharesErr) {
        console.warn('Could not fetch SEC shares history:', sharesErr);
      }

    } catch (err) {
      console.error('Dilution API error:', err);
      setError(err instanceof Error ? err.message : t('dilution.errorLoading'));
      setTickerData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim()) {
      fetchTickerData(inputValue.trim().toUpperCase());
    }
  };

  // Auto-load when windowState becomes available (after Zustand hydration)
  useEffect(() => {
    if (!autoLoadedRef.current && windowState.ticker && !selectedTicker) {
      autoLoadedRef.current = true;
      setInputValue(windowState.ticker);
      setSelectedTicker(windowState.ticker);
      fetchTickerData(windowState.ticker);
    }
  }, [windowState.ticker, selectedTicker]);

  const tabs: { id: TabType; label: string }[] = [
    { id: "dilution", label: "Dilution" },
    { id: "holders", label: "Holders" },
    { id: "filings", label: "Filings" },
    { id: "financials", label: "Financieros" },
  ];

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Job Completion Notification Toast - Minimalista */}
      {jobNotification && (
        <div
          className="mx-2 mt-1 px-3 py-2 border-b border-slate-200 flex items-center justify-between gap-2 cursor-pointer hover:bg-slate-50"
          onClick={() => {
            setInputValue(jobNotification.ticker);
            fetchTickerData(jobNotification.ticker);
            setJobNotification(null);
          }}
        >
          <span className="text-sm text-slate-700">{jobNotification.message}</span>
          <button
            className="text-xs text-slate-500 hover:text-slate-700 font-medium"
            onClick={(e) => {
              e.stopPropagation();
              setInputValue(jobNotification.ticker);
              fetchTickerData(jobNotification.ticker);
              setJobNotification(null);
            }}
          >
            View →
          </button>
        </div>
      )}

      {/* Search Bar - Minimalista */}
      <div className="px-3 py-2 border-b border-slate-200">
        <form onSubmit={handleSearch} className="flex items-center gap-2">
          <TickerSearch
            value={inputValue}
            onChange={setInputValue}
            onSelect={(ticker) => {
              setInputValue(ticker.symbol);
              fetchTickerData(ticker.symbol);
            }}
            placeholder="Enter ticker..."
            className="flex-1"
            autoFocus={false}
          />
          <button
            type="submit"
            disabled={loading}
            className="px-3 py-1 text-sm font-medium text-slate-600 hover:text-slate-900 disabled:opacity-50"
          >
            {loading ? '...' : 'Go'}
          </button>
        </form>
      </div>

      {/* Error Message */}
      {error && (
        <div className="px-3 py-2 text-sm text-red-600 border-b border-slate-200">
          {error}
        </div>
      )}

      {/* Content - flex-1 para ocupar espacio restante */}
      {selectedTicker ? (
        <div className="flex-1 overflow-auto min-h-0">
          {/* Company Header */}
          <div className="bg-white border-b border-slate-200 p-4">
            {/* Company Name */}
            <h2 className="text-xl font-bold text-slate-900 mb-2">
              {loading ? t('common.loading') : tickerData?.summary?.company_name || selectedTicker}
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
                <span className="text-slate-500">Float & OS:</span> {tickerData?.summary?.free_float && tickerData?.summary?.shares_outstanding ? `${(tickerData.summary.free_float / 1_000_000).toFixed(1)}M / ${(tickerData.summary.shares_outstanding / 1_000_000).toFixed(1)}M` : '--'}
                <span className="mx-3">•</span>
                <span className="text-slate-500">Inst Own:</span> {tickerData?.summary?.institutional_ownership ? `${tickerData.summary.institutional_ownership.toFixed(1)}%` : '--'}
              </div>
            </div>

            {/* Description */}
            {tickerData?.summary?.description && (
              <div className="mt-3 pt-3 border-t border-slate-200">
                <p className={`text-sm text-slate-600 leading-relaxed ${!descriptionExpanded ? 'line-clamp-2' : ''
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

          {/* Tabs - Minimalista */}
          <div className="border-b border-slate-200 bg-white sticky top-0 z-10">
            <div className="flex px-4">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`
                    px-4 py-2 text-sm font-medium border-b-2 transition-colors
                    ${activeTab === tab.id
                      ? "border-blue-600 text-blue-600"
                      : "border-transparent text-slate-500 hover:text-slate-700"
                    }
                  `}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Tab Content */}
          <div className="p-4">
            {activeTab === "dilution" && (
              <div className="space-y-6">
                {/* SEC Dilution Section - Siempre visible (maneja sus propios estados) */}
                {/* La terminal AI ahora se abre en ventana flotante independiente */}
                <SECDilutionSection
                  ticker={selectedTicker}
                  cachedData={secCacheData}
                  jobPending={pendingJobs.has(selectedTicker)}
                  jobStatus={secJobStatus}
                  onDataLoaded={() => {
                    // Cerrar ventana de terminal si existe cuando llegan datos
                    if (terminalWindowId) {
                      closeWindow(terminalWindowId);
                      setTerminalWindowId(null);
                    }
                  }}
                  onRefreshRequest={() => {
                    // Solicitar refresh forzando nuevo job
                    enqueueJob(selectedTicker, { forceRefresh: true });
                    setPendingJobs(prev => new Set(prev).add(selectedTicker));
                    setSecJobStatus('queued');
                    // Abrir terminal AI para el refresh
                    openAITerminal(selectedTicker, tickerData?.summary?.company_name);
                  }}
                />

                {/* Charts always visible below - Historical O/S from SEC EDGAR + Potential Dilution */}
                <DilutionHistoryChart
                  data={sharesHistory || (tickerData?.dilution_history as any) || null}
                  secData={secCacheData ? {
                    warrants: secCacheData.profile?.warrants?.map((w: any) => ({
                      outstanding: w.outstanding_warrants || w.outstanding || 0,
                      potential_new_shares: w.potential_new_shares || w.outstanding_warrants || 0
                    })) || [],
                    atm_offerings: secCacheData.profile?.atm_offerings?.map((a: any) => ({
                      remaining_capacity: a.remaining_capacity,
                      potential_shares_at_current_price: a.potential_shares_at_current_price
                    })) || [],
                    shares_outstanding: secCacheData.profile?.shares_outstanding,
                    current_price: secCacheData.profile?.current_price,
                    // Use dilution_analysis for pre-calculated totals
                    equity_lines: secCacheData.dilution_analysis?.equity_line_shares ?
                      [{ potential_shares: secCacheData.dilution_analysis.equity_line_shares }] : [],
                    convertible_notes: secCacheData.dilution_analysis?.convertible_shares ?
                      [{ potential_shares: secCacheData.dilution_analysis.convertible_shares }] : [],
                    convertible_preferred: [],
                    s1_offerings: [],
                  } as any : null}
                  loading={loading}
                />
                <CashRunwayChart data={cashRunwayData || (tickerData?.cash_runway as any) || null} loading={loading} />
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
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-slate-500">Enter a ticker to begin</p>
          </div>
        </div>
      )}
    </div>
  );
}

