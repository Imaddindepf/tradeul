'use client';

import { memo } from 'react';
import { TradingChart } from './TradingChart';

interface ChartContentProps {
    ticker?: string;
    exchange?: string;
    onTickerChange?: (ticker: string) => void;
}

/**
 * ChartContent - Professional Trading Chart
 * 
 * Uses lightweight-charts library for high-performance candlestick charts.
 * Data fetched from FMP API with intelligent caching.
 * 
 * Features:
 * - Multiple timeframes (1m, 5m, 15m, 30m, 1H, 4H, 1D)
 * - Candlestick chart with volume
 * - Moving averages (MA20, MA50)
 * - Bloomberg-inspired dark theme
 * - Responsive and fullscreen support
 */
function ChartContentComponent({ ticker = 'AAPL', exchange, onTickerChange }: ChartContentProps) {
    return (
        <TradingChart
            ticker={ticker}
            exchange={exchange}
            onTickerChange={onTickerChange}
        />
    );
}

export const ChartContent = memo(ChartContentComponent);
export default ChartContent;
