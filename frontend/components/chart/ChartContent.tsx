'use client';

import { memo } from 'react';
import { TradingChart } from './TradingChart';

interface ChartContentProps {
    ticker?: string;
    exchange?: string;
    onTickerChange?: (ticker: string) => void;
}

function ChartContentComponent({ ticker = 'AAPL', onTickerChange }: ChartContentProps) {
    return (
        <TradingChart
            ticker={ticker}
            onTickerChange={onTickerChange}
        />
    );
}

export const ChartContent = memo(ChartContentComponent);
export default ChartContent;
