'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import { cn } from "@/lib/utils";
import { TickerSearch } from "@/components/common/TickerSearch";
import { useWindowState } from "@/contexts/FloatingWindowContext";
import { useUserPreferencesStore, selectFont, selectColors } from "@/stores/useUserPreferencesStore";
import { HoldersTable } from "@/app/(dashboard)/dilution-tracker/_components/HoldersTable";
import { FilingsTable } from "@/app/(dashboard)/dilution-tracker/_components/FilingsTable";
import { CashRunwayChart } from "@/app/(dashboard)/dilution-tracker/_components/CashRunwayChart";
import { DilutionHistoryChart } from "@/app/(dashboard)/dilution-tracker/_components/DilutionHistoryChart";
import { FinancialsTable } from "@/app/(dashboard)/dilution-tracker/_components/FinancialsTable";
import { InstrumentContextSection } from "@/app/(dashboard)/dilution-tracker/_components/InstrumentContextSection";
import { AmbiguousQueueSection } from "@/app/(dashboard)/dilution-tracker/_components/AmbiguousQueueSection";
import {
  getCashPosition,
  getRiskRatings,
  getSharesHistory,
  getTickerAnalysis,
  validateTicker,
  type CashRunwayData,
  type DilutionRiskRatings,
  type TickerAnalysis,
} from "@/lib/dilution-api";
import {
  getInstrumentContext,
  type InstrumentContextResponse,
} from "@/lib/dilution-v2-api";

// ─── types ────────────────────────────────────────────────────────────────────
type TabType = "dilution" | "review" | "holders" | "filings" | "financials";
const DILUTION_ADMIN_EMAIL = "peertopeerhack@gmail.com";

interface DilutionWindowState {
  ticker?: string;
  tab?: TabType;
  [key: string]: unknown;
}

interface DilutionTrackerContentProps {
  initialTicker?: string;
}

// ─── font map ─────────────────────────────────────────────────────────────────
const FONT_CLASS_MAP: Record<string, string> = {
  "oxygen-mono":    "font-oxygen-mono",
  "ibm-plex-mono":  "font-ibm-plex-mono",
  "jetbrains-mono": "font-jetbrains-mono",
  "fira-code":      "font-fira-code",
};

// ─── risk colour ──────────────────────────────────────────────────────────────
function riskColor(level?: string): string {
  if (level === "High")   return "text-red-500 dark:text-red-400";
  if (level === "Medium") return "text-amber-500 dark:text-amber-400";
  if (level === "Low")    return "text-green-500 dark:text-green-400";
  return "text-muted-foreground";
}
function riskLabel(level?: string): string {
  if (!level || level === "Unknown") return "N/A";
  return level;
}

// ─── component ────────────────────────────────────────────────────────────────
export function DilutionTrackerContent({ initialTicker }: DilutionTrackerContentProps = {}) {
  const { t } = useTranslation();
  const { user, isLoaded: isUserLoaded } = useUser();
  const searchParams = useSearchParams();
  const { state: windowState, updateState: updateWindowState } = useWindowState<DilutionWindowState>();

  // preferences
  const font   = useUserPreferencesStore(selectFont);
  const colors = useUserPreferencesStore(selectColors);
  const fontClass = FONT_CLASS_MAP[font] || "font-jetbrains-mono";
  const upColor   = colors?.tickUp   || "#22c55e";
  const downColor = colors?.tickDown || "#ef4444";

  // ticker state
  const savedTicker = windowState.ticker || initialTicker || "";
  const [inputValue, setInputValue]     = useState(savedTicker);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(savedTicker || null);
  const [activeTab, setActiveTab]       = useState<TabType>(windowState.tab || "dilution");
  const autoLoadedRef = useRef(false);

  // data state
  const [loading, setLoading]               = useState(false);
  const [error, setError]                   = useState<string | null>(null);
  const [tickerData, setTickerData]         = useState<TickerAnalysis | null>(null);
  const [cashRunwayData, setCashRunwayData] = useState<CashRunwayData | null>(null);
  const [sharesHistory, setSharesHistory]   = useState<any>(null);
  const [instrumentContext, setInstrumentContext] = useState<InstrumentContextResponse | null>(null);
  const [riskRatings, setRiskRatings]       = useState<DilutionRiskRatings | null>(null);
  const [contextError, setContextError]     = useState<string | null>(null);

  const isDilutionAdmin = (user?.primaryEmailAddress?.emailAddress || "").toLowerCase() === DILUTION_ADMIN_EMAIL;
  const allowedTabs: TabType[] = isDilutionAdmin
    ? ["dilution", "review", "holders", "filings", "financials"]
    : ["dilution", "holders", "filings", "financials"];

  const normalizeTab = useCallback((tab: TabType | null | undefined): TabType => {
    if (!tab) return "dilution";
    return allowedTabs.includes(tab) ? tab : "dilution";
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDilutionAdmin]);

  const appendError = useCallback((msg: string) => {
    setError(prev => prev ? `${prev} · ${msg}` : msg);
  }, []);

  // persist state
  useEffect(() => {
    const safeTab = normalizeTab(activeTab);
    if (safeTab !== activeTab) { setActiveTab(safeTab); return; }
    updateWindowState({ ticker: selectedTicker || "", tab: safeTab });
  }, [selectedTicker, activeTab, updateWindowState, normalizeTab]);

  // fetch
  const fetchTickerData = useCallback(async (tickerInput: string) => {
    const ticker = tickerInput.toUpperCase().trim();
    const validResult = await validateTicker(ticker);
    // 'not_found' = ticker explicitly absent from dilution DB → block
    // 'error'     = backend temporarily unavailable → proceed optimistically
    if (validResult === 'not_found') { setError(t("dilution.invalidTicker")); return; }

    setLoading(true);
    setError(null);
    setContextError(null);
    setSelectedTicker(ticker);
    setTickerData(null);
    setCashRunwayData(null);
    setSharesHistory(null);
    setInstrumentContext(null);
    setRiskRatings(null);

    try {
      const [analysisData, contextData, sharesData, cashData, riskData] = await Promise.allSettled([
        getTickerAnalysis(ticker),
        getInstrumentContext(ticker),
        getSharesHistory(ticker),
        getCashPosition(ticker),
        getRiskRatings(ticker),
      ]);
      if (analysisData.status === "fulfilled") setTickerData(analysisData.value);
      else appendError("Analysis unavailable");

      if (contextData.status === "fulfilled") setInstrumentContext(contextData.value);
      else { setContextError("Instrument context unavailable."); appendError("Instrument context unavailable"); }

      if (sharesData.status === "fulfilled" && sharesData.value?.history) setSharesHistory(sharesData.value);
      if (cashData.status === "fulfilled") setCashRunwayData(cashData.value);
      else appendError("Cash runway unavailable");

      if (riskData.status === "fulfilled" && riskData.value) setRiskRatings(riskData.value);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("dilution.errorLoading"));
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, appendError]);

  // auto-load from URL / saved state
  useEffect(() => {
    if (!isUserLoaded) return;
    if (initialTicker && !selectedTicker) { fetchTickerData(initialTicker); return; }
    const tickerFromUrl = searchParams.get("ticker");
    const tabFromUrl = searchParams.get("tab") as TabType | null;
    if (tickerFromUrl && !selectedTicker) {
      const tk = tickerFromUrl.toUpperCase();
      setInputValue(tk); setSelectedTicker(tk); setActiveTab(normalizeTab(tabFromUrl));
      fetchTickerData(tk);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTicker, searchParams, selectedTicker, isUserLoaded]);

  useEffect(() => {
    if (!isUserLoaded) return;
    if (!isDilutionAdmin && activeTab === "review") setActiveTab("dilution");
  }, [isDilutionAdmin, activeTab, isUserLoaded]);

  useEffect(() => {
    if (!autoLoadedRef.current && windowState.ticker && !selectedTicker) {
      autoLoadedRef.current = true;
      setInputValue(windowState.ticker);
      setSelectedTicker(windowState.ticker);
      fetchTickerData(windowState.ticker);
    }
  }, [windowState.ticker, selectedTicker]);

  // sec data for chart
  const secData = useMemo(() => {
    if (!instrumentContext) return null;
    const currentPrice = Number(instrumentContext.ticker_info.last_price || 0);
    return {
      warrants: instrumentContext.instruments
        .filter(i => i.offering_type === "Warrant")
        .map(i => ({ outstanding: Number((i.details as any).remaining_warrants || 0) })),
      atm_offerings: instrumentContext.instruments
        .filter(i => i.offering_type === "ATM")
        .map(i => ({
          remaining_capacity: Number((i.details as any).remaining_atm_capacity || 0),
          potential_shares_at_current_price:
            currentPrice > 0
              ? Math.floor(Number((i.details as any).remaining_atm_capacity || 0) / currentPrice)
              : 0,
        })),
      equity_lines: instrumentContext.instruments
        .filter(i => i.offering_type === "Equity Line")
        .map(i => ({ potential_shares: Number((i.details as any).current_shares_equiv || 0) })),
      convertible_notes: instrumentContext.instruments
        .filter(i => i.offering_type === "Convertible Note")
        .map(i => ({ potential_shares: Number((i.details as any).remaining_shares_converted || 0) })),
      convertible_preferred: instrumentContext.instruments
        .filter(i => i.offering_type === "Convertible Preferred")
        .map(i => ({ potential_shares: Number((i.details as any).remaining_shares_converted || 0) })),
      s1_offerings: instrumentContext.instruments
        .filter(i => i.offering_type === "S-1 Offering")
        .map(i => ({ potential_shares: Number((i.details as any).final_shares_offered || 0) })),
      shares_outstanding: Number(instrumentContext.ticker_info.shares_outstanding || 0),
      current_price: currentPrice,
    };
  }, [instrumentContext]);

  const handleRefresh = useCallback(() => {
    if (selectedTicker) fetchTickerData(selectedTicker);
  }, [selectedTicker, fetchTickerData]);

  const effectiveRisk = riskRatings || ((tickerData?.risk_assessment as DilutionRiskRatings | undefined) ?? null);

  const displayCompanyName =
    tickerData?.summary?.company_name ||
    instrumentContext?.ticker_info?.company ||
    selectedTicker || "-";
  const displaySector   = tickerData?.summary?.sector || null;
  const displayExchange = tickerData?.summary?.exchange || null;
  const displayPrice    = instrumentContext?.ticker_info?.last_price || null;

  const tabs: { id: TabType; label: string }[] = allowedTabs.map(id => ({
    id,
    label: id === "dilution" ? "DILUTION" : id === "review" ? "REVIEW"
      : id === "holders" ? "HOLDERS" : id === "filings" ? "FILINGS" : "FINANCIALS",
  }));

  // ─── render ─────────────────────────────────────────────────────────────────
  return (
    <div className={cn("h-full flex flex-col bg-background text-foreground overflow-hidden", fontClass)}>

      {/* ── search bar ── */}
      <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-border flex-shrink-0">
        <TickerSearch
          value={inputValue}
          onChange={setInputValue}
          onSelect={tk => { setInputValue(tk.symbol); fetchTickerData(tk.symbol); }}
          placeholder="Ticker..."
          className="flex-1"
          autoFocus={false}
        />
        <button
          onClick={() => { if (inputValue.trim()) fetchTickerData(inputValue); }}
          disabled={loading}
          className="px-2.5 py-1 text-[10px] font-medium border border-border rounded text-muted-foreground hover:text-foreground hover:border-border transition-colors disabled:opacity-40"
        >
          {loading ? "..." : "GO"}
        </button>
      </div>

      {/* ── error banner ── */}
      {error && (
        <div className="px-2 py-1 text-[10px] text-red-500 border-b border-border flex-shrink-0">
          {error}
        </div>
      )}

      {selectedTicker ? (
        <>
          {/* ── company header ── */}
          <div className="flex items-baseline justify-between px-2 py-[5px] border-b border-border flex-shrink-0">
            <div className="flex items-baseline gap-1.5 min-w-0 overflow-hidden">
              <span className="text-[12px] font-semibold truncate">
                {loading ? "Loading…" : displayCompanyName}
              </span>
              {(displaySector || displayExchange) && (
                <span className="text-[10px] text-muted-foreground whitespace-nowrap truncate">
                  {[displaySector, displayExchange].filter(Boolean).join(" · ")}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0 ml-2">
              {displayPrice && (
                <span className="text-[11px] font-medium tabular-nums" style={{ color: upColor }}>
                  ${Number(displayPrice).toFixed(2)}
                </span>
              )}
              <span className="text-[9px] text-muted-foreground/60 border border-border rounded px-1.5 py-0.5 tracking-wider">
                {selectedTicker}
              </span>
            </div>
          </div>

          {/* ── risk strip (horizontal, 5 cells) ── */}
          {effectiveRisk && (
            <div className="flex border-b border-border flex-shrink-0">
              {([
                { key: "overall_risk",      label: "Overall Risk" },
                { key: "offering_ability",  label: "Offering" },
                { key: "overhead_supply",   label: "Overhead" },
                { key: "historical",        label: "Historical" },
                { key: "cash_need",         label: "Cash Need" },
              ] as const).map((item, idx) => {
                const val = effectiveRisk[item.key as keyof DilutionRiskRatings] as string | undefined;
                return (
                  <div
                    key={item.key}
                    className={cn(
                      "flex-1 flex flex-col gap-0.5 px-2 py-[6px]",
                      idx === 0 ? "flex-[1.3]" : "",
                      idx < 4 ? "border-r border-border" : "",
                    )}
                  >
                    <span className="text-[9px] text-muted-foreground/60 truncate">{item.label}</span>
                    <span className={cn("text-[11px] font-semibold leading-none", riskColor(val))}>
                      {riskLabel(val)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* ── tabs ── */}
          <div className="flex border-b border-border px-1 flex-shrink-0">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "px-2.5 py-[5px] text-[9px] font-medium tracking-wider border-b border-transparent",
                  "transition-colors -mb-px",
                  activeTab === tab.id
                    ? "text-foreground border-foreground/50"
                    : "text-muted-foreground/60 hover:text-muted-foreground",
                )}
              >
                {tab.label}
              </button>
            ))}
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="ml-auto px-2 py-[5px] text-[9px] text-muted-foreground/40 hover:text-muted-foreground/70 disabled:opacity-30 transition-colors"
            >
              {loading ? "…" : "↻"}
            </button>
          </div>

          {/* ── tab content ── */}
          <div className="flex-1 overflow-y-auto min-h-0">

            {/* DILUTION */}
            {activeTab === "dilution" && (
              <>
                {/* O/S history chart */}
                <div className="border-b border-border py-2">
                  <div className="px-2 pb-1 text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50">
                    Historical O/S &amp; Potential Dilution
                  </div>
                  <DilutionHistoryChart
                    data={sharesHistory || (tickerData?.dilution_history as any) || null}
                    secData={secData}
                    loading={loading}
                    fontClass={fontClass}
                    downColor={downColor}
                  />
                </div>

                {/* instruments table */}
                <div className="border-b border-border">
                  <div className="px-2 py-1 text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 border-b border-border">
                    Instruments
                  </div>
                  <InstrumentContextSection
                    context={instrumentContext}
                    loading={loading}
                    error={contextError}
                    fontClass={fontClass}
                  />
                </div>

                {/* completed offerings */}
                {instrumentContext && instrumentContext.completed_offerings.length > 0 && (
                  <div className="border-b border-border">
                    <div className="px-2 py-1 text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 border-b border-border">
                      Completed Offerings
                    </div>
                    <table className="w-full border-collapse">
                      <tbody>
                        {instrumentContext.completed_offerings.map(item => (
                          <tr key={item.id} className="border-b border-border hover:bg-muted/5 transition-colors">
                            <td className="px-2 py-[4px] text-[10px] font-medium w-[30%]">
                              {item.offering_type || "-"}
                            </td>
                            <td className="px-2 py-[4px] text-[10px] text-muted-foreground">
                              {item.offering_date ? new Date(item.offering_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" }) : "-"}
                              {item.shares ? ` · ${(item.shares / 1000).toFixed(0)}K sh` : ""}
                              {item.price ? ` @ $${Number(item.price).toFixed(2)}` : ""}
                              {item.bank ? ` · ${item.bank}` : ""}
                            </td>
                            <td className="px-2 py-[4px] text-[10px] font-medium tabular-nums text-right">
                              {item.amount != null
                                ? item.amount >= 1_000_000
                                  ? `$${(item.amount / 1_000_000).toFixed(2)}M`
                                  : item.amount >= 1_000
                                    ? `$${(item.amount / 1_000).toFixed(0)}K`
                                    : `$${item.amount.toLocaleString()}`
                                : "-"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* cash runway */}
                <div className="border-b border-border">
                  <div className="px-2 py-1 text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 border-b border-border">
                    Cash Runway
                  </div>
                  <div className="py-2">
                    <CashRunwayChart
                      data={cashRunwayData || (tickerData?.cash_runway as any) || null}
                      loading={loading}
                      fontClass={fontClass}
                      downColor={downColor}
                      upColor={upColor}
                    />
                  </div>
                </div>
              </>
            )}

            {/* HOLDERS */}
            {activeTab === "holders" && (
              <HoldersTable holders={tickerData?.holders || []} loading={loading} />
            )}

            {/* REVIEW (admin only) */}
            {activeTab === "review" && isDilutionAdmin && (
              <AmbiguousQueueSection ticker={selectedTicker} />
            )}

            {/* FILINGS */}
            {activeTab === "filings" && (
              <FilingsTable filings={tickerData?.filings || []} loading={loading} />
            )}

            {/* FINANCIALS */}
            {activeTab === "financials" && (
              <FinancialsTable financials={tickerData?.financials || []} loading={loading} />
            )}

          </div>

          {/* ── footer ── */}
          <div className="flex items-center justify-between px-2 py-[3px] border-t border-border text-[9px] text-muted-foreground/40 flex-shrink-0">
            <span>
              {selectedTicker}
              {instrumentContext && ` · ${instrumentContext.stats.total} instruments`}
            </span>
            <span>tradeul.com</span>
          </div>
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center text-[11px] text-muted-foreground/50">
          Enter a ticker to begin
        </div>
      )}
    </div>
  );
}
