'use client';

/**
 * InstitutionalHoldingsContent - Form 13F Institutional Holdings
 * 
 * FULL DATA - No simplifications. Maximum detail level.
 * NO ICONS - Text only interface.
 * 
 * Views:
 * - By Ticker: All institutional holders of a stock with FULL details
 * - By Fund: Complete fund profile + ALL holdings with FULL details
 * - Search Funds: Find funds by name
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { TableVirtuoso } from 'react-virtuoso';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { useWindowState } from '@/contexts/FloatingWindowContext';

// ============================================================================
// Types - FULL DATA STRUCTURES
// ============================================================================

interface VotingAuthority {
  sole: number;
  shared: number;
  none: number;
}

interface InvestmentDiscretionBreakdown {
  [key: string]: {
    shares: number;
    value: number;
    votingSole: number;
    votingShared: number;
    votingNone: number;
  };
}

interface HolderInfo {
  cik: string;
  name: string;
  nameOfIssuer: string;
  cusip: string;
  titleOfClass: string;
  shares: number;
  sharesType: string;
  value: number;
  filedAt: string;
  periodOfReport: string;
  accessionNo: string;
  formType: string;
  linkToFilingDetails: string;
  linkToHtml: string;
  hasPut: boolean;
  hasCall: boolean;
  investmentDiscretion: InvestmentDiscretionBreakdown;
  votingAuthority: VotingAuthority;
  changeShares?: number;
  changePercent?: number | null;
  prevShares?: number;
  prevValue?: number;
  isNew?: boolean;
  isClosed?: boolean;
}

interface FundHolding {
  ticker: string;
  cusip: string;
  nameOfIssuer: string;
  titleOfClass: string;
  value: number;
  shares: number;
  sharesType: string;
  investmentDiscretion: string;
  votingAuthority: {
    Sole: number;
    Shared: number;
    None: number;
  };
  putCall?: string;
  cik: string;
}

interface FundAddress {
  street: string;
  city: string;
  state: string;
  zip: string | number;
}

interface FundSignature {
  name: string;
  title: string;
  phone: string;
  signature: string;
  city: string;
  stateOrCountry: string;
  signatureDate: string;
}

interface FundManager {
  name: string;
  address: FundAddress;
}

interface FundProfile {
  cik: string;
  name: string;
  accessionNo: string;
  formType: string;
  periodOfReport: string;
  filedAt: string;
  linkToFilingDetails: string;
  linkToHtml: string;
  crdNumber?: string;
  form13FFileNumber?: string;
  isAmendment?: boolean;
  reportType?: string;
  tableEntryTotal?: number;
  tableValueTotal?: number;
  additionalInformation?: string;
  filingManager?: FundManager;
  signature?: FundSignature;
  otherIncludedManagersCount?: number;
  otherIncludedManagers?: Array<{ name: string; cik?: string }>;
}

interface FundSummary {
  totalHoldings: number;
  totalValue: number;
  totalShares: number;
  byDiscretion: {
    [key: string]: { count: number; value: number };
  };
}

interface FundSearchResult {
  cik: string;
  name: string;
  crdNumber?: string;
  form13FFileNumber?: string;
  tableValueTotal: number;
  tableEntryTotal: number;
  periodOfReport: string;
  filedAt: string;
  reportType: string;
  address: FundAddress;
}

interface HoldersResponse {
  ticker: string;
  currentPeriod: string;
  previousPeriod: string;
  totalHolders: number;
  totalValue: number;
  totalShares: number;
  totalFilings: number;
  stats: {
    newPositions: number;
    increased: number;
    decreased: number;
    unchanged: number;
    closed: number;
  };
  holders: HolderInfo[];
}

interface FundResponse {
  profile: FundProfile;
  summary: FundSummary;
  holdings: FundHolding[];
}

interface InstitutionalWindowState {
  ticker?: string;
  fundCik?: string;
  viewMode?: ViewMode;
  [key: string]: unknown;
}

type ViewMode = 'by_ticker' | 'by_fund' | 'search_funds';

// ============================================================================
// Constants
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const FONT_CLASSES: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono',
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

const DISCRETION_LABELS: Record<string, string> = {
  SOLE: 'Sole Discretion',
  DFND: 'Defined (Other Manager)',
  OTR: 'Other',
  UNKNOWN: 'Unknown',
};

// ============================================================================
// Helpers
// ============================================================================

function formatNumber(num: number): string {
  if (num >= 1_000_000_000) return `${(num / 1_000_000_000).toFixed(2)}B`;
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toLocaleString('en-US');
}

function formatNumberFull(num: number): string {
  return num.toLocaleString('en-US');
}

function formatCurrency(num: number): string {
  if (num >= 1_000_000_000) return `$${(num / 1_000_000_000).toFixed(2)}B`;
  if (num >= 1_000_000) return `$${(num / 1_000_000).toFixed(2)}M`;
  if (num >= 1_000) return `$${(num / 1_000).toFixed(1)}K`;
  return `$${num.toLocaleString('en-US')}`;
}

function formatCurrencyFull(num: number): string {
  return `$${num.toLocaleString('en-US')}`;
}

function formatPercent(num: number | undefined | null, showPlus = true): string {
  if (num === undefined || num === null) return '--';
  const sign = showPlus && num > 0 ? '+' : '';
  return `${sign}${num.toFixed(2)}%`;
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
  } catch {
    return dateStr;
  }
}

function formatDateFull(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

/**
 * Format period to show quarter clearly
 * e.g., "2025-12-31" -> "Q4 2025 (Dec 31)"
 * e.g., "2025-09-30" -> "Q3 2025 (Sep 30)"
 */
function formatQuarter(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    const q = Math.ceil((d.getMonth() + 1) / 3);
    const monthDay = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    return `Q${q} ${d.getFullYear()} (${monthDay})`;
  } catch {
    return dateStr;
  }
}

/**
 * Short quarter format for tables
 * e.g., "2025-12-31" -> "Q4 '25"
 */
function formatQuarterShort(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    const q = Math.ceil((d.getMonth() + 1) / 3);
    const year = d.getFullYear().toString().slice(-2);
    return `Q${q} '${year}`;
  } catch {
    return dateStr;
  }
}

function formatAddress(addr: FundAddress): string {
  const parts = [];
  if (addr.street) parts.push(addr.street);
  if (addr.city) parts.push(addr.city);
  if (addr.state) parts.push(addr.state);
  if (addr.zip) parts.push(String(addr.zip));
  return parts.join(', ');
}

// ============================================================================
// Collapsible Section Component
// ============================================================================

interface CollapsibleSectionProps {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function CollapsibleSection({ title, defaultOpen = true, children }: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-slate-200">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-2 py-1.5 flex items-center gap-1 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
      >
        <span className="text-[10px] text-slate-500">{isOpen ? '[-]' : '[+]'}</span>
        <span className="text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{title}</span>
      </button>
      {isOpen && <div className="px-2 py-2">{children}</div>}
    </div>
  );
}

// ============================================================================
// Info Row Component
// ============================================================================

interface InfoRowProps {
  label: string;
  value: React.ReactNode;
  className?: string;
}

function InfoRow({ label, value, className = '' }: InfoRowProps) {
  return (
    <div className={`flex items-start gap-2 py-0.5 ${className}`}>
      <span className="text-[10px] text-slate-500 min-w-[100px]">{label}:</span>
      <span className="text-[10px] text-slate-800 flex-1">{value}</span>
    </div>
  );
}

// ============================================================================
// Expanded Row Component (for detailed holder info)
// ============================================================================

interface ExpandedHolderRowProps {
  holder: HolderInfo;
  totalValue: number;
}

function ExpandedHolderRow({ holder, totalValue }: ExpandedHolderRowProps) {
  const ownershipPct = totalValue > 0 ? (holder.value / totalValue * 100).toFixed(4) : '0';

  return (
    <tr className="bg-slate-50">
      <td colSpan={8} className="px-3 py-2">
        <div className="grid grid-cols-3 gap-4 text-[9px]">
          {/* Column 1: Filing Info */}
          <div className="space-y-1">
            <div className="font-semibold text-slate-600 uppercase tracking-wider mb-1">Filing Info</div>
            <div className="flex gap-2">
              <span className="text-slate-500">CIK:</span>
              <span className="font-mono text-slate-800">{holder.cik}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-500">Accession:</span>
              <span className="font-mono text-slate-800">{holder.accessionNo}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-500">Form:</span>
              <span className="text-slate-800">{holder.formType}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-500">Period:</span>
              <span className="text-slate-800">{formatQuarter(holder.periodOfReport)}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-500">Filed:</span>
              <span className="text-slate-800">{formatDateFull(holder.filedAt)}</span>
            </div>
            {holder.linkToHtml && (
              <a
                href={holder.linkToHtml}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block text-blue-600 hover:text-blue-700 hover:underline mt-1"
              >
                [View on SEC]
              </a>
            )}
          </div>

          {/* Column 2: Position Details */}
          <div className="space-y-1">
            <div className="font-semibold text-slate-600 uppercase tracking-wider mb-1">Position Details</div>
            <div className="flex gap-2">
              <span className="text-slate-500">CUSIP:</span>
              <span className="font-mono text-slate-800">{holder.cusip}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-500">Class:</span>
              <span className="text-slate-800">{holder.titleOfClass}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-500">Shares:</span>
              <span className="text-slate-800">{formatNumberFull(holder.shares)} {holder.sharesType}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-500">Value:</span>
              <span className="text-slate-800">{formatCurrencyFull(holder.value)}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-500">% of Total:</span>
              <span className="text-slate-800">{ownershipPct}%</span>
            </div>
            {holder.hasPut && <span className="inline-block px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-[8px] mr-1">PUT</span>}
            {holder.hasCall && <span className="inline-block px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded text-[8px]">CALL</span>}
          </div>

          {/* Column 3: Discretion & Voting */}
          <div className="space-y-1">
            <div className="font-semibold text-slate-600 uppercase tracking-wider mb-1">Discretion & Voting</div>
            {/* Investment Discretion Breakdown */}
            {Object.entries(holder.investmentDiscretion).map(([type, data]) => (
              <div key={type} className="pl-2 border-l-2 border-slate-200 mb-1">
                <div className="font-medium text-slate-700">{DISCRETION_LABELS[type] || type}</div>
                <div className="text-slate-500 pl-2">
                  Shares: {formatNumber(data.shares)} | Value: {formatCurrency(data.value)}
                </div>
              </div>
            ))}
            {/* Voting Authority */}
            <div className="mt-2">
              <div className="font-medium text-slate-700 mb-1">Voting Authority:</div>
              <div className="flex gap-3 pl-2">
                <span className="text-slate-600">Sole: {formatNumber(holder.votingAuthority.sole)}</span>
                <span className="text-slate-600">Shared: {formatNumber(holder.votingAuthority.shared)}</span>
                <span className="text-slate-600">None: {formatNumber(holder.votingAuthority.none)}</span>
              </div>
            </div>
            {/* Change Details */}
            {holder.prevShares !== undefined && (
              <div className="mt-2">
                <div className="font-medium text-slate-700 mb-1">QoQ Change:</div>
                <div className="pl-2 text-slate-600">
                  Prev: {formatNumber(holder.prevShares)} shares ({formatCurrency(holder.prevValue || 0)})
                </div>
              </div>
            )}
          </div>
        </div>
      </td>
    </tr>
  );
}

// ============================================================================
// Main Component
// ============================================================================

interface InstitutionalHoldingsContentProps {
  initialTicker?: string;
}

export function InstitutionalHoldingsContent({ initialTicker }: InstitutionalHoldingsContentProps = {}) {
  const { t } = useTranslation();
  const font = useUserPreferencesStore(selectFont);
  const fontClass = FONT_CLASSES[font] || 'font-jetbrains-mono';
  const { state: windowState, updateState: updateWindowState } = useWindowState<InstitutionalWindowState>();

  // Persisted state
  const savedTicker = windowState.ticker || initialTicker || '';
  const savedViewMode = windowState.viewMode || 'by_ticker';

  // State
  const [viewMode, setViewMode] = useState<ViewMode>(savedViewMode);
  const [ticker, setTicker] = useState(savedTicker);
  const [inputValue, setInputValue] = useState(savedTicker);
  const [fundCik, setFundCik] = useState(windowState.fundCik || '');
  const [fundSearchValue, setFundSearchValue] = useState('');

  // Data state
  const [holdersData, setHoldersData] = useState<HoldersResponse | null>(null);
  const [fundData, setFundData] = useState<FundResponse | null>(null);
  const [fundSearchResults, setFundSearchResults] = useState<FundSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Expanded rows tracking
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  // Persist state changes
  useEffect(() => {
    updateWindowState({ ticker, fundCik, viewMode });
  }, [ticker, fundCik, viewMode, updateWindowState]);

  // Toggle row expansion
  const toggleRowExpansion = useCallback((cik: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(cik)) {
        next.delete(cik);
      } else {
        next.add(cik);
      }
      return next;
    });
  }, []);

  // Fetch holders for a ticker
  const fetchHoldersByTicker = useCallback(async (symbol: string) => {
    if (!symbol.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/institutional/holders/${symbol.toUpperCase()}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data: HoldersResponse = await response.json();
      setHoldersData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading data');
      setHoldersData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch fund holdings by CIK
  const fetchFundHoldings = useCallback(async (cik: string) => {
    if (!cik.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/institutional/fund/${cik}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data: FundResponse = await response.json();
      setFundData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading data');
      setFundData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Search funds
  const searchFunds = useCallback(async (query: string) => {
    if (!query.trim() || query.length < 2) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/institutional/search/funds?q=${encodeURIComponent(query)}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();
      setFundSearchResults(data.funds || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading data');
      setFundSearchResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    if (viewMode === 'by_ticker' && ticker) {
      fetchHoldersByTicker(ticker);
    } else if (viewMode === 'by_fund' && fundCik) {
      fetchFundHoldings(fundCik);
    }
  }, []);

  // Handle ticker search
  const handleTickerSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim()) {
      const symbol = inputValue.toUpperCase();
      setTicker(symbol);
      setViewMode('by_ticker');
      fetchHoldersByTicker(symbol);
    }
  };

  const handleTickerSelect = (selected: { symbol: string }) => {
    setInputValue(selected.symbol);
    setTicker(selected.symbol);
    setViewMode('by_ticker');
    fetchHoldersByTicker(selected.symbol);
  };

  // Handle fund search
  const handleFundSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (fundSearchValue.trim()) {
      if (viewMode === 'search_funds') {
        searchFunds(fundSearchValue.trim());
      } else {
        setFundCik(fundSearchValue.trim());
        fetchFundHoldings(fundSearchValue.trim());
      }
    }
  };

  // Select fund from search results
  const selectFund = (fund: FundSearchResult) => {
    setFundCik(fund.cik);
    setFundSearchValue(fund.cik);
    setViewMode('by_fund');
    fetchFundHoldings(fund.cik);
  };

  return (
    <div className={`h-full flex flex-col bg-white text-slate-800 ${fontClass}`}>
      {/* Header - View Toggle & Search */}
      <div className={`flex items-center gap-2 px-2 py-1.5 border-b border-slate-200 bg-slate-50 ${fontClass}`}>
        {/* View Toggle */}
        <div className="flex items-center bg-white rounded border border-slate-200 overflow-hidden">
          <button
            onClick={() => setViewMode('by_ticker')}
            className={`px-2 py-1 text-[10px] font-medium transition-colors ${viewMode === 'by_ticker' ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'
              }`}
          >
            By Ticker
          </button>
          <button
            onClick={() => setViewMode('by_fund')}
            className={`px-2 py-1 text-[10px] font-medium transition-colors ${viewMode === 'by_fund' ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'
              }`}
          >
            By Fund
          </button>
          <button
            onClick={() => setViewMode('search_funds')}
            className={`px-2 py-1 text-[10px] font-medium transition-colors ${viewMode === 'search_funds' ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'
              }`}
          >
            Search
          </button>
        </div>

        {/* Ticker Search */}
        {viewMode === 'by_ticker' && (
          <form onSubmit={handleTickerSearch} className="flex items-center gap-1">
            <TickerSearch
              value={inputValue}
              onChange={setInputValue}
              onSelect={handleTickerSelect}
              placeholder="Ticker"
              className="w-20"
            />
            <button
              type="submit"
              disabled={loading || !inputValue.trim()}
              className={`px-2 py-1 text-[10px] font-medium bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors ${fontClass}`}
            >
              {loading ? '...' : 'Go'}
            </button>
          </form>
        )}

        {/* Fund Search */}
        {(viewMode === 'by_fund' || viewMode === 'search_funds') && (
          <form onSubmit={handleFundSearch} className="flex items-center gap-1">
            <input
              type="text"
              value={fundSearchValue}
              onChange={(e) => setFundSearchValue(e.target.value)}
              placeholder={viewMode === 'search_funds' ? 'Fund Name' : 'CIK'}
              className={`w-40 px-2 py-1 text-[10px] border border-slate-200 rounded focus:outline-none focus:border-blue-400 ${fontClass}`}
            />
            <button
              type="submit"
              disabled={loading || !fundSearchValue.trim()}
              className={`px-2 py-1 text-[10px] font-medium bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors ${fontClass}`}
            >
              {loading ? '...' : 'Go'}
            </button>
          </form>
        )}

        <div className="flex-1" />

        {/* Context */}
        {viewMode === 'by_ticker' && ticker && (
          <span className={`px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-slate-800 border border-slate-300 rounded ${fontClass}`}>
            {ticker}
          </span>
        )}
        {viewMode === 'by_fund' && fundData?.profile && (
          <span className={`px-2 py-0.5 text-[10px] font-medium bg-slate-100 text-slate-800 border border-slate-300 rounded truncate max-w-[200px] ${fontClass}`}>
            {fundData.profile.name}
          </span>
        )}

        {/* Refresh */}
        <button
          onClick={() => {
            if (viewMode === 'by_ticker' && ticker) fetchHoldersByTicker(ticker);
            else if (viewMode === 'by_fund' && fundCik) fetchFundHoldings(fundCik);
            else if (viewMode === 'search_funds' && fundSearchValue) searchFunds(fundSearchValue);
          }}
          disabled={loading}
          className={`px-1.5 py-0.5 text-[9px] text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors ${fontClass}`}
        >
          {loading ? '[...]' : '[Refresh]'}
        </button>
      </div>

      {/* Summary Stats Panel - By Ticker */}
      {viewMode === 'by_ticker' && holdersData && holdersData.holders.length > 0 && (
        <div className={`px-2 py-1.5 border-b border-slate-200 bg-white ${fontClass}`}>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px]">
            <div className="flex items-center gap-1">
              <span className="text-slate-500">Holders:</span>
              <span className="font-semibold text-slate-800">{holdersData.totalHolders}</span>
            </div>
            <span className="text-slate-300">|</span>
            <div className="flex items-center gap-1">
              <span className="text-slate-500">Value:</span>
              <span className="font-semibold text-slate-800">{formatCurrency(holdersData.totalValue)}</span>
            </div>
            <span className="text-slate-300">|</span>
            <div className="flex items-center gap-1">
              <span className="text-slate-500">Shares:</span>
              <span className="font-semibold text-slate-800">{formatNumber(holdersData.totalShares)}</span>
            </div>
            <span className="text-slate-300">|</span>
            <div className="flex items-center gap-1">
              <span className="text-slate-500">Report Period:</span>
              <span className="text-slate-800 font-medium">{formatQuarter(holdersData.currentPeriod)}</span>
              {holdersData.previousPeriod && (
                <span className="text-slate-400">vs {formatQuarterShort(holdersData.previousPeriod)}</span>
              )}
            </div>
            <span className="text-slate-300">|</span>
            <div className="flex items-center gap-1">
              <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded text-[9px]">
                {holdersData.stats.increased} Increased
              </span>
              <span className="px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-[9px]">
                {holdersData.stats.decreased} Decreased
              </span>
              <span className="px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded text-[9px]">
                {holdersData.stats.unchanged} Unchanged
              </span>
              <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-[9px]">
                {holdersData.stats.newPositions} N/A
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Fund Profile Panel - By Fund */}
      {viewMode === 'by_fund' && fundData?.profile && (
        <div className={`border-b border-slate-200 bg-white max-h-[200px] overflow-y-auto ${fontClass}`}>
          <CollapsibleSection title="Fund Profile" defaultOpen={true}>
            <div className="grid grid-cols-2 gap-4">
              {/* Left Column */}
              <div className="space-y-0.5">
                <InfoRow label="Name" value={<span className="font-semibold">{fundData.profile.name}</span>} />
                <InfoRow label="CIK" value={<span className="font-mono">{fundData.profile.cik}</span>} />
                {fundData.profile.crdNumber && (
                  <InfoRow label="CRD Number" value={<span className="font-mono">{fundData.profile.crdNumber}</span>} />
                )}
                {fundData.profile.form13FFileNumber && (
                  <InfoRow label="13F File No" value={<span className="font-mono">{fundData.profile.form13FFileNumber}</span>} />
                )}
                <InfoRow label="Form Type" value={fundData.profile.formType} />
                <InfoRow label="Report Type" value={fundData.profile.reportType || 'Holdings Report'} />
                {fundData.profile.isAmendment && (
                  <InfoRow label="Amendment" value={<span className="text-amber-600 font-medium">Yes</span>} />
                )}
              </div>

              {/* Right Column */}
              <div className="space-y-0.5">
                <InfoRow label="Report Period" value={formatQuarter(fundData.profile.periodOfReport)} />
                <InfoRow label="Filed Date" value={formatDateFull(fundData.profile.filedAt)} />
                <InfoRow label="AUM" value={<span className="font-semibold">{formatCurrency(fundData.summary.totalValue)}</span>} />
                <InfoRow label="Holdings" value={`${fundData.summary.totalHoldings} positions`} />
                {fundData.profile.filingManager?.address && (
                  <InfoRow
                    label="Address"
                    value={formatAddress(fundData.profile.filingManager.address)}
                  />
                )}
                {fundData.profile.signature && (
                  <>
                    <InfoRow
                      label="Signer"
                      value={`${fundData.profile.signature.name}, ${fundData.profile.signature.title}`}
                    />
                    {fundData.profile.signature.phone && (
                      <InfoRow
                        label="Phone"
                        value={fundData.profile.signature.phone}
                      />
                    )}
                  </>
                )}
              </div>
            </div>

            {/* Additional Information */}
            {fundData.profile.additionalInformation && (
              <div className="mt-2 pt-2 border-t border-slate-100">
                <p className="text-[10px] text-slate-600 whitespace-pre-wrap">
                  <span className="font-medium text-slate-500">Notes: </span>
                  {fundData.profile.additionalInformation}
                </p>
              </div>
            )}

            {/* Investment Discretion Breakdown */}
            {Object.keys(fundData.summary.byDiscretion).length > 1 && (
              <div className="mt-2 pt-2 border-t border-slate-100">
                <div className="text-[9px] font-semibold text-slate-500 uppercase tracking-wider mb-1">By Investment Discretion</div>
                <div className="flex gap-3">
                  {Object.entries(fundData.summary.byDiscretion).map(([type, data]) => (
                    <div key={type} className="text-[10px]">
                      <span className="text-slate-500">{DISCRETION_LABELS[type] || type}:</span>{' '}
                      <span className="text-slate-800">{data.count} positions ({formatCurrency(data.value)})</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* SEC Links */}
            <div className="mt-2 pt-2 border-t border-slate-100 flex gap-3">
              {fundData.profile.linkToHtml && (
                <a
                  href={fundData.profile.linkToHtml}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-blue-600 hover:text-blue-700 hover:underline"
                >
                  [View Filing on SEC]
                </a>
              )}
              {fundData.profile.linkToFilingDetails && (
                <a
                  href={fundData.profile.linkToFilingDetails}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-blue-600 hover:text-blue-700 hover:underline"
                >
                  [View XML]
                </a>
              )}
            </div>
          </CollapsibleSection>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className={`mx-2 mt-2 px-2 py-1.5 bg-red-50 border border-red-200 rounded text-red-700 text-[10px] ${fontClass}`}>
          Error: {error}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {loading && !holdersData && !fundData && fundSearchResults.length === 0 ? (
          <div className={`flex items-center justify-center h-full ${fontClass}`}>
            <div className="text-center">
              <p className="text-[10px] text-slate-500">Loading data...</p>
            </div>
          </div>
        ) : viewMode === 'by_ticker' ? (
          // ================================================================
          // HOLDERS TABLE (By Ticker) - FULL DATA
          // ================================================================
          !holdersData || holdersData.holders.length === 0 ? (
            <div className={`flex items-center justify-center h-full ${fontClass}`}>
              <div className="text-center">
                <p className="text-[10px] text-slate-500">
                  {ticker ? 'No institutional holders found' : 'Enter a ticker to view institutional holders'}
                </p>
              </div>
            </div>
          ) : (
            <TableVirtuoso
              style={{ height: '100%' }}
              data={holdersData.holders}
              overscan={20}
              fixedHeaderContent={() => (
                <tr className={`bg-slate-100 border-b border-slate-200 ${fontClass}`}>
                  <th className="px-2 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-8"></th>
                  <th className="px-2 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider">Fund Name</th>
                  <th className="px-2 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-24">Shares</th>
                  <th className="px-2 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-24">Value</th>
                  <th className="px-2 py-1.5 text-center text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-16">Type</th>
                  <th className="px-2 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-20">Change</th>
                  <th className="px-2 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-16">Chg %</th>
                  <th className="px-2 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-16">Period</th>
                </tr>
              )}
              itemContent={(index, holder) => {
                const isExpanded = expandedRows.has(holder.cik);
                const isNew = holder.isNew;
                const isClosed = holder.isClosed;
                const changePercent = holder.changePercent;
                const isPositive = changePercent !== null && changePercent !== undefined && changePercent > 0;
                const isNegative = changePercent !== null && changePercent !== undefined && changePercent < 0;

                return (
                  <>
                    <td className="px-2 py-1.5">
                      <button
                        onClick={() => toggleRowExpansion(holder.cik)}
                        className="p-0.5 text-slate-400 hover:text-slate-600 transition-colors text-[10px]"
                      >
                        {isExpanded ? '[-]' : '[+]'}
                      </button>
                    </td>
                    <td className="px-2 py-1.5 text-[10px]">
                      <div className="flex items-center gap-1">
                        <span
                          className="font-medium text-slate-800 truncate max-w-[180px] cursor-pointer hover:text-blue-600"
                          onClick={() => {
                            setFundCik(holder.cik);
                            setFundSearchValue(holder.cik);
                            setViewMode('by_fund');
                            fetchFundHoldings(holder.cik);
                          }}
                          title={holder.name}
                        >
                          {holder.name}
                        </span>
                        {isClosed && <span className="px-1 py-0 text-[8px] bg-red-100 text-red-700 rounded">CLOSED</span>}
                        {holder.hasPut && <span className="px-1 py-0 text-[8px] bg-purple-100 text-purple-700 rounded">PUT</span>}
                        {holder.hasCall && <span className="px-1 py-0 text-[8px] bg-cyan-100 text-cyan-700 rounded">CALL</span>}
                      </div>
                    </td>
                    <td className="px-2 py-1.5 text-right text-[10px] text-slate-700 tabular-nums">
                      <span title={formatNumberFull(holder.shares)}>{formatNumber(holder.shares)}</span>
                      <span className="text-slate-400 text-[8px] ml-0.5">{holder.sharesType}</span>
                    </td>
                    <td className="px-2 py-1.5 text-right text-[10px] text-slate-800 font-medium tabular-nums">
                      <span title={formatCurrencyFull(holder.value)}>{formatCurrency(holder.value)}</span>
                    </td>
                    <td className="px-2 py-1.5 text-center text-[9px]">
                      {Object.keys(holder.investmentDiscretion).map(type => (
                        <span
                          key={type}
                          className="px-1 py-0.5 bg-slate-100 text-slate-600 rounded mr-0.5"
                          title={DISCRETION_LABELS[type] || type}
                        >
                          {type}
                        </span>
                      ))}
                    </td>
                    <td className={`px-2 py-1.5 text-right text-[10px] tabular-nums ${isPositive ? 'text-emerald-600' : isNegative ? 'text-red-600' : 'text-slate-500'
                      }`}>
                      {holder.changeShares !== undefined ? (
                        <span title={formatNumberFull(Math.abs(holder.changeShares))}>
                          {holder.changeShares > 0 ? '+' : ''}{formatNumber(holder.changeShares)}
                        </span>
                      ) : '--'}
                    </td>
                    <td className={`px-2 py-1.5 text-right text-[10px] font-medium tabular-nums ${isPositive ? 'text-emerald-600' : isNegative ? 'text-red-600' : 'text-slate-500'
                      }`}>
                      {formatPercent(changePercent)}
                    </td>
                    <td className="px-2 py-1.5 text-right text-[10px] text-slate-500 tabular-nums" title={formatQuarter(holder.periodOfReport)}>
                      {formatQuarterShort(holder.periodOfReport)}
                    </td>
                  </>
                );
              }}
              components={{
                Table: ({ style, ...props }) => (
                  <table {...props} style={{ ...style, width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }} className={`text-[10px] ${fontClass}`} />
                ),
                TableHead: React.forwardRef(({ style, ...props }, ref) => (
                  <thead {...props} ref={ref} style={{ ...style, position: 'sticky', top: 0, zIndex: 1 }} />
                )),
                TableRow: ({ style, item, ...props }) => {
                  const isExpanded = expandedRows.has(item.cik);
                  return (
                    <>
                      <tr {...props} style={{ ...style }} className="hover:bg-blue-50 border-b border-slate-100" />
                      {isExpanded && <ExpandedHolderRow holder={item} totalValue={holdersData?.totalValue || 0} />}
                    </>
                  );
                },
              }}
            />
          )
        ) : viewMode === 'by_fund' ? (
          // ================================================================
          // FUND HOLDINGS TABLE (By Fund) - FULL DATA
          // ================================================================
          !fundData || fundData.holdings.length === 0 ? (
            <div className={`flex items-center justify-center h-full ${fontClass}`}>
              <div className="text-center">
                <p className="text-[10px] text-slate-500">
                  {fundCik ? 'No holdings found' : 'Enter a fund CIK to view holdings'}
                </p>
              </div>
            </div>
          ) : (
            <TableVirtuoso
              style={{ height: '100%' }}
              data={fundData.holdings}
              overscan={20}
              fixedHeaderContent={() => (
                <tr className={`bg-slate-100 border-b border-slate-200 ${fontClass}`}>
                  <th className="px-2 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-16">Ticker</th>
                  <th className="px-2 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-24">CUSIP</th>
                  <th className="px-2 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider">Issuer</th>
                  <th className="px-2 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-16">Class</th>
                  <th className="px-2 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-24">Shares</th>
                  <th className="px-2 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-24">Value</th>
                  <th className="px-2 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-14">% Port</th>
                  <th className="px-2 py-1.5 text-center text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-14">Disc</th>
                  <th className="px-2 py-1.5 text-center text-[9px] font-semibold text-slate-500 uppercase tracking-wider w-20">Voting</th>
                </tr>
              )}
              itemContent={(index, holding) => {
                const portfolioPct = fundData.summary.totalValue > 0
                  ? (holding.value / fundData.summary.totalValue * 100).toFixed(2)
                  : '0.00';
                const isPut = holding.putCall === 'Put';
                const isCall = holding.putCall === 'Call';
                const votingTotal = (holding.votingAuthority?.Sole || 0) +
                  (holding.votingAuthority?.Shared || 0) +
                  (holding.votingAuthority?.None || 0);
                const votingSolePct = votingTotal > 0
                  ? ((holding.votingAuthority?.Sole || 0) / votingTotal * 100).toFixed(0)
                  : '0';

                return (
                  <>
                    <td className="px-2 py-1.5 text-[10px]">
                      <span
                        className={`font-semibold ${holding.ticker ? 'text-slate-900 cursor-pointer hover:text-blue-600' : 'text-slate-400'}`}
                        onClick={() => {
                          if (holding.ticker) {
                            setInputValue(holding.ticker);
                            setTicker(holding.ticker);
                            setViewMode('by_ticker');
                            fetchHoldersByTicker(holding.ticker);
                          }
                        }}
                      >
                        {holding.ticker || '--'}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-[9px] text-slate-600">
                      {holding.cusip}
                    </td>
                    <td className="px-2 py-1.5 text-[10px] text-slate-700">
                      <div className="flex items-center gap-1 truncate" title={holding.nameOfIssuer}>
                        <span className="truncate">{holding.nameOfIssuer}</span>
                        {isPut && <span className="px-1 py-0 text-[8px] bg-red-100 text-red-700 rounded flex-shrink-0">PUT</span>}
                        {isCall && <span className="px-1 py-0 text-[8px] bg-emerald-100 text-emerald-700 rounded flex-shrink-0">CALL</span>}
                      </div>
                    </td>
                    <td className="px-2 py-1.5 text-[9px] text-slate-500">
                      {holding.titleOfClass}
                    </td>
                    <td className="px-2 py-1.5 text-right text-[10px] text-slate-700 tabular-nums">
                      <span title={formatNumberFull(holding.shares)}>{formatNumber(holding.shares)}</span>
                      <span className="text-slate-400 text-[8px] ml-0.5">{holding.sharesType}</span>
                    </td>
                    <td className="px-2 py-1.5 text-right text-[10px] text-slate-800 font-medium tabular-nums">
                      <span title={formatCurrencyFull(holding.value)}>{formatCurrency(holding.value)}</span>
                    </td>
                    <td className="px-2 py-1.5 text-right text-[10px] text-slate-600 tabular-nums">
                      {portfolioPct}%
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <span
                        className="px-1 py-0.5 text-[8px] bg-slate-100 text-slate-600 rounded"
                        title={DISCRETION_LABELS[holding.investmentDiscretion] || holding.investmentDiscretion}
                      >
                        {holding.investmentDiscretion}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-center text-[9px] text-slate-500">
                      <span title={`Sole: ${holding.votingAuthority?.Sole || 0} | Shared: ${holding.votingAuthority?.Shared || 0} | None: ${holding.votingAuthority?.None || 0}`}>
                        {votingSolePct}% Sole
                      </span>
                    </td>
                  </>
                );
              }}
              components={{
                Table: ({ style, ...props }) => (
                  <table {...props} style={{ ...style, width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }} className={`text-[10px] ${fontClass}`} />
                ),
                TableHead: React.forwardRef(({ style, ...props }, ref) => (
                  <thead {...props} ref={ref} style={{ ...style, position: 'sticky', top: 0, zIndex: 1 }} />
                )),
                TableRow: ({ style, ...props }) => (
                  <tr {...props} style={{ ...style }} className="hover:bg-blue-50 border-b border-slate-100" />
                ),
              }}
            />
          )
        ) : (
          // ================================================================
          // SEARCH FUNDS RESULTS
          // ================================================================
          fundSearchResults.length === 0 ? (
            <div className={`flex items-center justify-center h-full ${fontClass}`}>
              <div className="text-center">
                <p className="text-[10px] text-slate-500">
                  Search for funds by name
                </p>
              </div>
            </div>
          ) : (
            <div className={`h-full overflow-y-auto ${fontClass}`}>
              <div className="divide-y divide-slate-100">
                {fundSearchResults.map((fund) => (
                  <div
                    key={fund.cik}
                    className="px-3 py-2 hover:bg-blue-50 cursor-pointer transition-colors"
                    onClick={() => selectFund(fund)}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-[11px] text-slate-800 truncate">{fund.name}</div>
                        <div className="flex items-center gap-3 mt-1 text-[10px] text-slate-500">
                          <span>CIK: {fund.cik}</span>
                          {fund.crdNumber && <span>CRD: {fund.crdNumber}</span>}
                          <span>{formatQuarterShort(fund.periodOfReport)}</span>
                        </div>
                        {fund.address && (fund.address.city || fund.address.state) && (
                          <div className="mt-0.5 text-[9px] text-slate-400">
                            {[fund.address.city, fund.address.state].filter(Boolean).join(', ')}
                          </div>
                        )}
                      </div>
                      <div className="text-right flex-shrink-0">
                        <div className="font-semibold text-[11px] text-slate-800">
                          {formatCurrency(fund.tableValueTotal)}
                        </div>
                        <div className="text-[9px] text-slate-500">
                          {fund.tableEntryTotal} positions
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        )}
      </div>

      {/* Footer */}
      <div className={`px-2 py-1 border-t border-slate-200 text-[9px] text-slate-400 flex justify-between bg-slate-50 ${fontClass}`}>
        <span>SEC Form 13F Data</span>
        <span>
          {viewMode === 'by_ticker' && holdersData ? `${holdersData.holders.length} holders` : ''}
          {viewMode === 'by_fund' && fundData ? `${fundData.holdings.length} holdings` : ''}
          {viewMode === 'search_funds' && fundSearchResults.length > 0 ? `${fundSearchResults.length} funds` : ''}
        </span>
      </div>
    </div>
  );
}
