'use client';

import { useState, useMemo } from 'react';
import { Search } from 'lucide-react';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';

// Indicator definitions - grouped by category
const INDICATORS = {
    price: [
        { id: 'price', name: 'Price', desc: 'Last closing price' },
        { id: 'change_1d', name: 'Change 1D', desc: '1-day price change percentage' },
        { id: 'change_5d', name: 'Change 5D', desc: '5-day price change percentage' },
        { id: 'change_20d', name: 'Change 20D', desc: '20-day price change percentage' },
        { id: 'gap_percent', name: 'Gap %', desc: 'Gap from previous close to current open' },
        { id: 'from_52w_high', name: 'From 52W High', desc: 'Distance from 52-week high. 0% = at high' },
        { id: 'from_52w_low', name: 'From 52W Low', desc: 'Distance from 52-week low. 0% = at low' },
    ],
    volume: [
        { id: 'volume', name: 'Volume', desc: 'Total shares traded today' },
        { id: 'relative_volume', name: 'Rel. Volume', desc: 'Current volume vs 20-day average. >2x = high activity' },
        { id: 'avg_volume_20', name: 'Avg Vol 20', desc: '20-day average daily volume' },
    ],
    trend: [
        { id: 'sma_20', name: 'SMA 20', desc: '20-day Simple Moving Average' },
        { id: 'sma_50', name: 'SMA 50', desc: '50-day Simple Moving Average' },
        { id: 'sma_200', name: 'SMA 200', desc: '200-day Simple Moving Average' },
        { id: 'dist_sma_20', name: 'Dist SMA 20', desc: 'Price distance from SMA 20 as percentage' },
        { id: 'dist_sma_50', name: 'Dist SMA 50', desc: 'Price distance from SMA 50 as percentage' },
    ],
    momentum: [
        { id: 'rsi_14', name: 'RSI (14)', desc: 'Relative Strength Index. <30 oversold, >70 overbought' },
    ],
    volatility: [
        { id: 'atr_14', name: 'ATR (14)', desc: 'Average True Range over 14 days' },
        { id: 'atr_percent', name: 'ATR %', desc: 'ATR as percentage of price. Higher = more volatile' },
        { id: 'bb_upper', name: 'BB Upper', desc: 'Bollinger Band upper (SMA20 + 2 std dev)' },
        { id: 'bb_lower', name: 'BB Lower', desc: 'Bollinger Band lower (SMA20 - 2 std dev)' },
        { id: 'bb_width', name: 'BB Width', desc: 'Band width as %. Lower = compression, breakout likely' },
        { id: 'bb_position', name: 'BB Position', desc: 'Price position within bands. 0% = lower, 100% = upper' },
    ],
    squeeze: [
        { id: 'squeeze_on', name: 'Squeeze ON', desc: 'TTM Squeeze active. Bollinger Bands inside Keltner Channels = low volatility consolidation, breakout imminent' },
        { id: 'squeeze_momentum', name: 'Squeeze Mom.', desc: 'Momentum direction during squeeze. Positive = bullish setup, negative = bearish setup' },
        { id: 'keltner_upper', name: 'Keltner Upper', desc: 'EMA(20) + ATR(10) x 1.5' },
        { id: 'keltner_lower', name: 'Keltner Lower', desc: 'EMA(20) - ATR(10) x 1.5' },
    ],
    adx: [
        { id: 'adx_14', name: 'ADX (14)', desc: 'Average Directional Index. Measures trend strength regardless of direction. <20 = weak/no trend, >25 = strong trend, >50 = very strong' },
        { id: 'plus_di_14', name: '+DI (14)', desc: 'Positive Directional Indicator. Measures upward movement strength' },
        { id: 'minus_di_14', name: '-DI (14)', desc: 'Negative Directional Indicator. Measures downward movement strength' },
        { id: 'adx_trend', name: 'ADX Trend', desc: 'Combined signal: 1 = bullish trend (ADX>25, +DI>-DI), -1 = bearish trend, 0 = no trend' },
    ],
    fundamental: [
        { id: 'market_cap', name: 'Market Cap', desc: 'Total market capitalization (price x shares outstanding)' },
        { id: 'float_shares', name: 'Float', desc: 'Shares available for public trading' },
        { id: 'sector', name: 'Sector', desc: 'Business sector classification' },
    ],
};

const CATEGORY_NAMES: Record<string, string> = {
    price: 'Price',
    volume: 'Volume',
    trend: 'Trend',
    momentum: 'Momentum',
    volatility: 'Volatility',
    squeeze: 'TTM Squeeze',
    adx: 'ADX',
    fundamental: 'Fundamental',
};

export function GlossaryContent() {
    const font = useUserPreferencesStore(selectFont);
    const [search, setSearch] = useState('');
    const [expandedCategory, setExpandedCategory] = useState<string | null>('squeeze');

    const filteredIndicators = useMemo(() => {
        if (!search.trim()) return INDICATORS;
        
        const term = search.toLowerCase();
        const filtered: typeof INDICATORS = {} as typeof INDICATORS;
        
        Object.entries(INDICATORS).forEach(([category, indicators]) => {
            const matches = indicators.filter(
                ind => ind.name.toLowerCase().includes(term) || 
                       ind.desc.toLowerCase().includes(term)
            );
            if (matches.length > 0) {
                filtered[category as keyof typeof INDICATORS] = matches;
            }
        });
        
        return filtered;
    }, [search]);

    return (
        <div 
            className="h-full flex flex-col bg-white text-slate-800 overflow-hidden"
            style={{ fontFamily: `var(--font-${font})` }}
        >
            {/* Search */}
            <div className="flex-shrink-0 p-2 border-b border-slate-100">
                <div className="relative">
                    <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400" />
                    <input
                        type="text"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search indicators..."
                        className="w-full pl-7 pr-2 py-1 text-xs bg-slate-50 border border-slate-200 rounded focus:outline-none focus:border-slate-300"
                        style={{ fontFamily: `var(--font-${font})` }}
                    />
                </div>
            </div>

            {/* Categories */}
            <div className="flex-1 overflow-y-auto">
                {Object.entries(filteredIndicators).map(([category, indicators]) => (
                    <div key={category} className="border-b border-slate-100 last:border-0">
                        <button
                            onClick={() => setExpandedCategory(expandedCategory === category ? null : category)}
                            className="w-full px-3 py-1.5 flex items-center justify-between hover:bg-slate-50 transition-colors"
                        >
                            <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wide">
                                {CATEGORY_NAMES[category] || category}
                            </span>
                            <span className="text-[9px] text-slate-400">
                                {indicators.length}
                            </span>
                        </button>
                        
                        {expandedCategory === category && (
                            <div className="px-3 pb-2 space-y-1">
                                {indicators.map((ind) => (
                                    <div key={ind.id} className="py-1">
                                        <div className="text-[10px] font-medium text-slate-700">
                                            {ind.name}
                                        </div>
                                        <div className="text-[9px] text-slate-500 leading-tight">
                                            {ind.desc}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {/* Footer */}
            <div className="flex-shrink-0 px-3 py-1.5 border-t border-slate-100 bg-slate-50">
                <div className="text-[8px] text-slate-400 text-center">
                    {Object.values(INDICATORS).flat().length} indicators
                </div>
            </div>
        </div>
    );
}

