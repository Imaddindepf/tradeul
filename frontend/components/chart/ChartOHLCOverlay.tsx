'use client';

import { useMemo } from 'react';
import { useChartContext } from './ChartContext';
import { useDisplayBar } from './hoveredBarStore';
import { formatPrice } from './formatters';
import { INTERVALS } from './constants';
import { ChartLiveBadge } from './ChartLiveBadge';

/**
 * Top-left symbol legend, TradingView-style:
 *
 *   ▸ Row 1 — logo · TICKER · company name · interval · exchange · LIVE
 *   ▸ Row 2 — O H L C of the hovered (or last) bar, all coloured by the bar's
 *             direction (green when close ≥ open, red otherwise), plus the
 *             absolute / percentage change vs. the previous bar.
 *
 * The whole block reads from `useDisplayBar()` so only this overlay re-renders
 * as the crosshair moves; the long name truncates with an ellipsis so narrow
 * floating windows never overflow.
 */
export function ChartOHLCOverlay() {
    const ctx = useChartContext();
    const { tickerMeta, currentTicker, selectedInterval } = ctx;
    const { displayBar, prevBar } = useDisplayBar();

    const intervalLabel = useMemo(
        () => INTERVALS.find(i => i.interval === selectedInterval)?.shortLabel ?? selectedInterval,
        [selectedInterval],
    );

    const hasClose = displayBar?.close != null && prevBar?.close != null
        && Number.isFinite(displayBar.close) && Number.isFinite(prevBar.close);
    const priceChange = hasClose ? displayBar!.close - prevBar!.close : 0;
    const priceChangePercent = hasClose && prevBar!.close !== 0
        ? (priceChange / prevBar!.close) * 100
        : 0;
    const changeUp = priceChange >= 0;

    // Bar direction drives the OHLC colour (TradingView paints all four cells).
    const barUp = displayBar ? displayBar.close >= displayBar.open : true;
    const ohlcColor = barUp ? 'var(--color-chart-up)' : 'var(--color-chart-down)';

    const logoUrl = tickerMeta?.icon_url
        ? `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/proxy/logo?url=${encodeURIComponent(tickerMeta.icon_url)}`
        : null;

    return (
        <div
            className="absolute top-1.5 left-2 z-10 pointer-events-none flex flex-col gap-0.5"
            style={{ maxWidth: 'calc(100% - 1rem)' }}
        >
            {/* ── Meta row ───────────────────────────────────────────── */}
            <div className="flex items-center gap-1.5 min-w-0">
                {logoUrl ? (
                    <img
                        src={logoUrl}
                        alt=""
                        className="w-4 h-4 rounded-sm object-contain flex-shrink-0"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                ) : (
                    <div className="w-4 h-4 rounded-sm bg-[color:var(--color-primary)] flex items-center justify-center text-white text-[8px] font-bold flex-shrink-0">
                        {currentTicker?.[0] || '?'}
                    </div>
                )}
                <span className="text-[11px] font-semibold text-[color:var(--color-fg)] flex-shrink-0">
                    {currentTicker}
                </span>
                {tickerMeta?.company_name && (
                    <span className="text-[10px] text-[color:var(--color-muted-fg)] truncate min-w-0">
                        {tickerMeta.company_name}
                    </span>
                )}
                <span className="text-[9.5px] font-medium text-[color:var(--color-muted-fg)] flex-shrink-0">
                    · {intervalLabel}
                </span>
                {tickerMeta?.exchange && (
                    <span className="text-[9.5px] font-medium text-[color:var(--color-muted-fg)] flex-shrink-0">
                        · {tickerMeta.exchange}
                    </span>
                )}
                <ChartLiveBadge />
            </div>

            {/* ── OHLC row ───────────────────────────────────────────── */}
            {displayBar && (
                <div className="flex items-center gap-2 font-mono text-[10.5px] tabular-nums whitespace-nowrap">
                    <OhlcCell label="O" value={formatPrice(displayBar.open)} color={ohlcColor} />
                    <OhlcCell label="H" value={formatPrice(displayBar.high)} color={ohlcColor} />
                    <OhlcCell label="L" value={formatPrice(displayBar.low)} color={ohlcColor} />
                    <OhlcCell label="C" value={formatPrice(displayBar.close)} color={ohlcColor} />
                    {hasClose && (
                        <span
                            className="font-semibold"
                            style={{ color: changeUp ? 'var(--color-chart-up)' : 'var(--color-chart-down)' }}
                        >
                            {changeUp ? '+' : ''}{priceChange.toFixed(2)}
                            <span className="ml-1">
                                ({changeUp ? '+' : ''}{priceChangePercent.toFixed(2)}%)
                            </span>
                        </span>
                    )}
                </div>
            )}
        </div>
    );
}

function OhlcCell({ label, value, color }: { label: string; value: string; color: string }) {
    return (
        <span className="flex items-center gap-0.5">
            <span className="text-[color:var(--color-muted-fg)]">{label}</span>
            <span className="font-semibold" style={{ color }}>{value}</span>
        </span>
    );
}
