'use client';

import { useChartContext } from './ChartContext';
import { formatPrice } from './formatters';
import { ChartLiveBadge } from './ChartLiveBadge';

/**
 * Top-left overlay with ticker meta + live OHLC of the hovered (or last) bar.
 * Monospaced numeric columns, backdrop blur, two stacked rows to fit narrow
 * floating windows without truncating.
 */
export function ChartOHLCOverlay() {
    const ctx = useChartContext();
    const { tickerMeta, currentTicker, displayBar, prevBar } = ctx;

    const hasClose = displayBar?.close != null && prevBar?.close != null && Number.isFinite(displayBar.close) && Number.isFinite(prevBar.close);
    const priceChange = hasClose ? displayBar!.close - prevBar!.close : 0;
    const priceChangePercent = hasClose && prevBar!.close !== 0
        ? (priceChange / prevBar!.close) * 100
        : 0;
    const isPositive = priceChange >= 0;

    const logoUrl = tickerMeta?.icon_url
        ? `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/proxy/logo?url=${encodeURIComponent(tickerMeta.icon_url)}`
        : null;

    return (
        <div
            className="absolute top-1.5 left-2 z-10 pointer-events-none flex flex-col gap-0.5"
            style={{ maxWidth: '95%' }}
        >
            <div className="flex items-center gap-1.5">
                {logoUrl ? (
                    <img
                        src={logoUrl}
                        alt=""
                        className="w-4 h-4 rounded-sm object-contain"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                ) : (
                    <div className="w-4 h-4 rounded-sm bg-[color:var(--color-primary)] flex items-center justify-center text-white text-[8px] font-bold flex-shrink-0">
                        {currentTicker?.[0] || '?'}
                    </div>
                )}
                <span className="text-[11px] font-semibold text-[color:var(--color-fg)]">
                    {tickerMeta?.company_name || currentTicker}
                </span>
                {tickerMeta?.exchange && (
                    <span className="text-[9.5px] font-medium text-[color:var(--color-muted-fg)]">
                        {tickerMeta.exchange}
                    </span>
                )}
                <ChartLiveBadge />
            </div>
            {displayBar && (
                <div className="flex items-center gap-2 font-mono text-[10.5px] tabular-nums whitespace-nowrap">
                    <OhlcCell label="O" value={formatPrice(displayBar.open)} tone="neutral" />
                    <OhlcCell label="H" value={formatPrice(displayBar.high)} tone="up" />
                    <OhlcCell label="L" value={formatPrice(displayBar.low)} tone="down" />
                    <OhlcCell label="C" value={formatPrice(displayBar.close)} tone="neutral" />
                    {hasClose && (
                        <span className={`font-semibold ${isPositive ? 'text-[color:var(--color-chart-up)]' : 'text-[color:var(--color-chart-down)]'}`}>
                            {isPositive ? '+' : ''}{priceChange.toFixed(2)}
                            <span className="ml-1">
                                ({isPositive ? '+' : ''}{priceChangePercent.toFixed(2)}%)
                            </span>
                        </span>
                    )}
                </div>
            )}
        </div>
    );
}

function OhlcCell({ label, value, tone }: { label: string; value: string; tone: 'up' | 'down' | 'neutral' }) {
    const cls =
        tone === 'up' ? 'text-[color:var(--color-chart-up)]' :
        tone === 'down' ? 'text-[color:var(--color-chart-down)]' :
        'text-[color:var(--color-fg)]';
    return (
        <span className="flex items-center gap-0.5">
            <span className="text-[color:var(--color-muted-fg)]">{label}</span>
            <span className={`font-semibold ${cls}`}>{value}</span>
        </span>
    );
}
