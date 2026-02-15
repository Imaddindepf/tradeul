'use client';

import { useState, useEffect, useCallback, memo } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, ExternalLink, TrendingUp, TrendingDown, Users, Building2, Calendar, Globe, Phone } from 'lucide-react';
import { TickerStrip } from '@/components/ticker/TickerStrip';
import { TradingChart } from '@/components/chart/TradingChart';
import { useFloatingWindow, useWindowState } from '@/contexts/FloatingWindowContext';
import { ChartContent } from '@/components/chart/ChartContent';
import { TickerNewsMini } from '@/components/news/TickerNewsMini';

interface DescriptionWindowState {
  ticker?: string;
  [key: string]: unknown;
}

// ============================================================================
// Types
// ============================================================================

interface TickerDescription {
  symbol: string;
  updatedAt: string;
  company: {
    symbol: string;
    name: string;
    exchange?: string;
    exchangeFullName?: string;
    sector?: string;
    industry?: string;
    is_spac?: boolean;
    is_de_spac?: boolean;
    former_spac_name?: string;
    merger_date?: string;
    sic_code?: string;
    description?: string;
    ceo?: string;
    website?: string;
    address?: string;
    city?: string;
    state?: string;
    country?: string;
    phone?: string;
    employees?: number;
    ipoDate?: string;
    logoUrl?: string;
    iconUrl?: string;
  };
  stats: {
    price?: number;
    change?: number;
    changePercent?: number;
    volume?: number;
    avgVolume?: number;
    marketCap?: number;
    sharesOutstanding?: number;
    freeFloat?: number;
    freeFloatPercent?: number;
    yearLow?: number;
    yearHigh?: number;
    range52Week?: string;
    beta?: number;
  };
  valuation: {
    peRatio?: number;
    forwardPE?: number;
    pegRatio?: number;
    pbRatio?: number;
    psRatio?: number;
    evToEbitda?: number;
  };
  dividend: {
    trailingYield?: number;
    payoutRatio?: number;
    dividendPerShare?: number;
  };
  risk: {
    beta?: number;
    shortInterest?: number;
    shortRatio?: number;
  };
  analystRating?: {
    analystRatingsbuy?: number;
    analystRatingsHold?: number;
    analystRatingsSell?: number;
    analystRatingsStrongBuy?: number;
    analystRatingsStrongSell?: number;
  };
  priceTargets: Array<{
    analystCompany?: string;
    analystName?: string;
    priceTarget?: number;
    publishedDate?: string;
  }>;
  consensusTarget?: number;
  targetUpside?: number;
}

interface DescriptionContentProps {
  ticker: string;
  exchange?: string;
}

// ============================================================================
// Helpers
// ============================================================================

const formatNumber = (n?: number, decimals = 2): string => {
  if (n === null || n === undefined) return '-';
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
};

const formatCompact = (n?: number): string => {
  if (n === null || n === undefined) return '-';
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toString();
};

const formatPercent = (n?: number): string => {
  if (n === null || n === undefined) return '-';
  return `${n.toFixed(2)}%`;
};

const formatRatio = (n?: number): string => {
  if (n === null || n === undefined) return '-';
  return n.toFixed(2);
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ============================================================================
// Sub-components
// ============================================================================

const StatRow = memo(({ label, value, valueClass = '' }: { label: string; value: string; valueClass?: string }) => (
  <div className="flex justify-between items-center py-0.5">
    <span className="text-slate-500 text-xs">{label}</span>
    <span className={`text-xs font-mono ${valueClass || 'text-slate-800'}`}>{value}</span>
  </div>
));
StatRow.displayName = 'StatRow';

const SectionHeader = memo(({ title }: { title: string }) => (
  <div className="text-[10px] font-semibold text-blue-600 uppercase tracking-wider mb-1 pb-1 border-b border-slate-200">
    {title}
  </div>
));
SectionHeader.displayName = 'SectionHeader';

// ============================================================================
// Expandable Text — collapsible description with "more/less" toggle
// ============================================================================

function ExpandableText({ text, className = '' }: { text: string; className?: string }) {
  const [expanded, setExpanded] = useState(false);
  const needsExpand = text.length > 200;

  return (
    <div className={className}>
      <p className={expanded ? '' : 'line-clamp-3'}>
        {text}
      </p>
      {needsExpand && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-blue-500 hover:text-blue-600 text-[10px] font-medium mt-0.5 cursor-pointer"
        >
          {expanded ? '▲ Show less' : '▼ Read more'}
        </button>
      )}
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

function DescriptionContentComponent({ ticker: initialTicker, exchange }: DescriptionContentProps) {
  const { t } = useTranslation();
  const { openWindow } = useFloatingWindow();
  const { state: windowState, updateState: updateWindowState } = useWindowState<DescriptionWindowState>();
  
  // Use persisted ticker or prop
  const ticker = windowState.ticker || initialTicker;
  
  const [data, setData] = useState<TickerDescription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Persist ticker when it changes
  useEffect(() => {
    if (ticker) {
      updateWindowState({ ticker });
    }
  }, [ticker, updateWindowState]);

  // Callback to open full Chart window
  const handleOpenChart = useCallback(() => {
    const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

    openWindow({
      title: 'Chart',
      content: <ChartContent ticker={ticker} exchange={exchange} />,
      width: 900,
      height: 600,
      x: Math.max(50, screenWidth / 2 - 450),
      y: Math.max(80, screenHeight / 2 - 300),
      minWidth: 600,
      minHeight: 400,
    });
  }, [ticker, exchange, openWindow]);

  // Callback to open News window for this ticker
  const handleOpenNews = useCallback(() => {
    const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

    openWindow({
      title: 'News',  // Siempre "News" - el ticker se filtra internamente
      content: <TickerNewsMini ticker={ticker} />,
      width: 500,
      height: 500,
      x: Math.max(50, screenWidth / 2 - 250),
      y: Math.max(80, screenHeight / 2 - 250),
      minWidth: 400,
      minHeight: 300,
    });
  }, [ticker, openWindow]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/ticker/${ticker}/description`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      setData(result);
    } catch (err) {
      console.error('Description fetch error:', err);
      setError(err instanceof Error ? err.message : t('description.errorLoading'));
    } finally {
      setLoading(false);
    }
  }, [ticker, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-white">
        <RefreshCw className="w-6 h-6 text-blue-500 animate-spin" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-full bg-white text-red-500">
        {t('common.error')}: {error || t('description.noData')}
      </div>
    );
  }

  const { company, stats, valuation, dividend, risk, analystRating, priceTargets, consensusTarget, targetUpside } = data;

  // Calculate analyst totals
  const totalAnalysts = (analystRating?.analystRatingsStrongBuy || 0) +
    (analystRating?.analystRatingsbuy || 0) +
    (analystRating?.analystRatingsHold || 0) +
    (analystRating?.analystRatingsSell || 0) +
    (analystRating?.analystRatingsStrongSell || 0);

  return (
    <div className="h-full flex flex-col bg-white text-slate-800 overflow-hidden">
      {/* Header: Quote Strip */}
      <div className="px-3 py-2 border-b border-slate-200 bg-slate-50">
        <TickerStrip symbol={ticker} exchange={exchange || 'US'} />
      </div>

      {/* Main Content Grid - min-h-0 for proper flex shrinking */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <div className="grid grid-cols-[1fr_220px] h-full overflow-auto">
          {/* Left Column - min-h-0 critical for flex children to shrink */}
          <div className="flex flex-col min-h-0 border-r border-slate-200 overflow-auto">
            {/* Company Header */}
            <div className="p-3 border-b border-slate-200">
              <div className="flex items-start gap-3">
                {/* Logo - usa proxy solo para URLs de Polygon */}
                {company.logoUrl && (
                  <img
                    src={company.logoUrl.includes('polygon.io')
                      ? `${API_URL}/api/v1/proxy/logo?url=${encodeURIComponent(company.logoUrl)}`
                      : company.logoUrl
                    }
                    alt={company.name}
                    className="w-14 h-14 rounded-lg bg-slate-100 p-1.5 object-contain border border-slate-200"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                )}

                {/* Company Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="px-1.5 py-0.5 text-[10px] font-bold bg-blue-600 text-white rounded">EQ</span>
                    {company.is_spac && (
                      <span className="px-1.5 py-0.5 text-[10px] font-medium bg-amber-100 text-amber-700 border border-amber-200 rounded">SPAC</span>
                    )}
                    {company.is_de_spac && (
                      <span className="px-1.5 py-0.5 text-[10px] font-medium bg-purple-100 text-purple-700 border border-purple-200 rounded" title={`Former: ${company.former_spac_name}`}>
                        de-SPAC
                      </span>
                    )}
                    <span className="text-sm font-semibold text-slate-800 truncate">{company.name}</span>
                  </div>

                  {/* de-SPAC info */}
                  {company.is_de_spac && company.former_spac_name && (
                    <div className="text-[10px] text-purple-600 mt-0.5">
                      via {company.former_spac_name} {company.merger_date && `(${new Date(company.merger_date).toLocaleDateString()})`}
                    </div>
                  )}

                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    {company.ceo && <span>CEO: {company.ceo}</span>}
                    {company.sector && <span className="text-slate-400">• {company.sector}</span>}
                  </div>

                  {company.website && (
                    <a
                      href={company.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 mt-1 text-xs text-blue-600 hover:text-blue-700"
                    >
                      <Globe className="w-3 h-3" />
                      {company.website.replace('https://', '').replace('http://', '').replace('www.', '')}
                    </a>
                  )}
                </div>
              </div>

              {/* Description */}
              {company.description && (
                <ExpandableText text={company.description} className="mt-2 text-xs text-slate-500" />
              )}
            </div>

            {/* Chart - min-h-0 allows proper shrinking after fullscreen */}
            <div className="flex-1 min-h-0 border-b border-slate-200 overflow-hidden" style={{ minHeight: '250px' }}>
              <TradingChart
                ticker={ticker}
                exchange={exchange}
                minimal={true}
                onOpenChart={handleOpenChart}
                onOpenNews={handleOpenNews}
              />
            </div>

            {/* Stats Row */}
            <div className="grid grid-cols-3 gap-4 p-3 bg-slate-50">
              {/* Stats */}
              <div>
                <SectionHeader title={t('description.stats')} />
                <StatRow label={t('description.price')} value={`$${formatNumber(stats.price)}`} />
                <StatRow label={t('description.sharesOut')} value={formatCompact(stats.sharesOutstanding)} />
                <StatRow label={t('description.marketCap')} value={formatCompact(stats.marketCap)} />
                <StatRow label="Free Float" value={formatCompact(stats.freeFloat)} />
                <StatRow label={t('description.avgVol')} value={formatCompact(stats.avgVolume)} />
              </div>

              {/* Analyst Ratings */}
              <div>
                <SectionHeader title={t('description.analystRatings')} />
                {analystRating && totalAnalysts > 0 ? (
                  <>
                    <div className="flex items-center gap-1 mb-1">
                      <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden flex">
                        <div
                          className="bg-green-500 h-full"
                          style={{ width: `${((analystRating.analystRatingsStrongBuy || 0) + (analystRating.analystRatingsbuy || 0)) / totalAnalysts * 100}%` }}
                        />
                        <div
                          className="bg-yellow-500 h-full"
                          style={{ width: `${(analystRating.analystRatingsHold || 0) / totalAnalysts * 100}%` }}
                        />
                        <div
                          className="bg-red-500 h-full"
                          style={{ width: `${((analystRating.analystRatingsSell || 0) + (analystRating.analystRatingsStrongSell || 0)) / totalAnalysts * 100}%` }}
                        />
                      </div>
                    </div>
                    <StatRow label={t('description.strongBuy')} value={String(analystRating.analystRatingsStrongBuy || 0)} valueClass="text-green-600" />
                    <StatRow label={t('description.buy')} value={String(analystRating.analystRatingsbuy || 0)} valueClass="text-green-600" />
                    <StatRow label={t('description.hold')} value={String(analystRating.analystRatingsHold || 0)} valueClass="text-yellow-600" />
                    <StatRow label={t('description.sell')} value={String((analystRating.analystRatingsSell || 0) + (analystRating.analystRatingsStrongSell || 0))} valueClass="text-red-600" />
                  </>
                ) : (
                  <div className="text-xs text-slate-400">{t('description.noRatings')}</div>
                )}
              </div>

              {/* Price Targets */}
              <div>
                <SectionHeader title={t('description.priceTargets')} />
                {consensusTarget ? (
                  <>
                    <StatRow label={t('description.consensus')} value={`$${formatNumber(consensusTarget)}`} valueClass="text-blue-600" />
                    <StatRow
                      label={t('description.upside')}
                      value={formatPercent(targetUpside)}
                      valueClass={targetUpside && targetUpside > 0 ? 'text-green-600' : 'text-red-600'}
                    />
                    <StatRow label={t('description.52wLow')} value={`$${formatNumber(stats.yearLow)}`} />
                    <StatRow label={t('description.52wHigh')} value={`$${formatNumber(stats.yearHigh)}`} />
                  </>
                ) : (
                  <div className="text-xs text-slate-400">{t('description.noTargets')}</div>
                )}
              </div>
            </div>
          </div>

          {/* Right Column - Market Info */}
          <div className="overflow-auto p-3 bg-slate-50">
            {/* Market Info */}
            <div className="mb-4">
              <SectionHeader title={t('description.marketInfo')} />
              <StatRow label={t('description.exchange')} value={company.exchange || '-'} />
              <StatRow label={t('description.currency')} value="USD" />
              <StatRow label={t('description.float')} value={formatCompact(stats.freeFloat)} />
              <StatRow label={t('description.employees')} value={formatCompact(company.employees)} />
              {company.ipoDate && <StatRow label={t('description.ipoDate')} value={company.ipoDate} />}
            </div>

            {/* Valuation Ratios */}
            <div className="mb-4">
              <SectionHeader title={t('description.valuationRatios')} />
              <StatRow label="P/E" value={formatRatio(valuation.peRatio)} />
              <StatRow label="P/B" value={formatRatio(valuation.pbRatio)} />
              <StatRow label="P/S" value={formatRatio(valuation.psRatio)} />
              <StatRow label="EV/EBITDA" value={formatRatio(valuation.evToEbitda)} />
              <StatRow label="PEG" value={formatRatio(valuation.pegRatio)} />
            </div>

            {/* Dividend */}
            <div className="mb-4">
              <SectionHeader title={t('description.dividendYield')} />
              <StatRow label={t('description.yield')} value={formatPercent(dividend.trailingYield)} valueClass={dividend.trailingYield ? 'text-green-600' : ''} />
              <StatRow label={t('description.payoutRatio')} value={formatPercent(dividend.payoutRatio ? dividend.payoutRatio * 100 : undefined)} />
              <StatRow label={t('description.divPerShare')} value={dividend.dividendPerShare ? `$${formatNumber(dividend.dividendPerShare)}` : '-'} />
            </div>

            {/* Risk */}
            <div className="mb-4">
              <SectionHeader title={t('description.riskSentiment')} />
              <StatRow label="Beta" value={formatRatio(risk.beta)} />
              {risk.shortInterest && <StatRow label={t('description.shortInterest')} value={formatCompact(risk.shortInterest)} />}
              {risk.shortRatio && <StatRow label={t('description.shortRatio')} value={formatRatio(risk.shortRatio)} />}
            </div>

            {/* Recent Price Targets */}
            {priceTargets.length > 0 && (
              <div>
                <SectionHeader title={t('description.recentTargets')} />
                <div className="space-y-1.5">
                  {priceTargets.slice(0, 5).map((target, i) => (
                    <div key={i} className="text-[10px]">
                      <div className="flex justify-between">
                        <span className="text-slate-500 truncate max-w-[120px]">{target.analystCompany || t('description.unknown')}</span>
                        <span className="text-green-600 font-mono">${target.priceTarget}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export const DescriptionContent = memo(DescriptionContentComponent);
export default DescriptionContent;

