'use client';

import { useState, useRef, useMemo, useCallback, useEffect } from 'react';
import { Loader2 } from 'lucide-react';

interface CandlestickData {
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
}

interface CandlestickSelectorProps {
    symbol: string;
    date: string;
    onSelectionChange: (startTime: string | null, endTime: string | null, minutes: number) => void;
    fontFamily?: string;
    maxMinutes?: number;
}

const API_BASE = process.env.NEXT_PUBLIC_PATTERN_API_URL || 'https://tradeul.com/patterns';

export function CandlestickSelector({
    symbol,
    date,
    onSelectionChange,
    fontFamily = 'inherit',
    maxMinutes = 120,
}: CandlestickSelectorProps) {
    const svgRef = useRef<SVGSVGElement>(null);
    const [candles, setCandles] = useState<CandlestickData[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Selection state
    const [isDragging, setIsDragging] = useState(false);
    const [selectionStart, setSelectionStart] = useState<number | null>(null);
    const [selectionEnd, setSelectionEnd] = useState<number | null>(null);
    const [hoverIndex, setHoverIndex] = useState<number | null>(null);

    // Dimensions
    const width = 600;
    const height = 160;
    const padding = { top: 20, right: 15, bottom: 25, left: 45 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Fetch OHLC candle data
    useEffect(() => {
        if (!symbol || !date) return;

        const fetchCandles = async () => {
            setLoading(true);
            setError(null);
            setSelectionStart(null);
            setSelectionEnd(null);
            
            try {
                // Fetch minute bars with OHLC
                const res = await fetch(
                    `${API_BASE}/api/historical/ohlc/${symbol}?date=${date}&start_time=09:30&end_time=16:00`
                );
                
                if (!res.ok) {
                    // Fallback to regular prices endpoint
                    const priceRes = await fetch(
                        `${API_BASE}/api/historical/prices/${symbol}?date=${date}&start_time=09:30&end_time=16:00`
                    );
                    if (!priceRes.ok) throw new Error('Failed to load data');
                    
                    const priceData = await priceRes.json();
                    if (priceData.error) throw new Error(priceData.error);
                    
                    // Convert prices to pseudo-candles
                    const times = priceData.times || [];
                    const prices = priceData.prices || [];
                    
                    const candleData: CandlestickData[] = times.map((t: string, i: number) => {
                        const price = prices[i];
                        const prevPrice = i > 0 ? prices[i - 1] : price;
                        return {
                            time: t,
                            open: prevPrice,
                            high: Math.max(price, prevPrice),
                            low: Math.min(price, prevPrice),
                            close: price,
                        };
                    });
                    
                    setCandles(candleData);
                    return;
                }

                const data = await res.json();
                if (data.error) throw new Error(data.error);
                setCandles(data.candles || []);
            } catch (e: any) {
                setError(e.message);
            } finally {
                setLoading(false);
            }
        };

        fetchCandles();
    }, [symbol, date]);

    // Notify parent of selection changes (limited to maxMinutes)
    useEffect(() => {
        if (selectionStart !== null && selectionEnd !== null && candles.length > 0) {
            const start = Math.min(selectionStart, selectionEnd);
            const rawEnd = Math.max(selectionStart, selectionEnd);
            // Limit to maxMinutes
            const end = Math.min(rawEnd, start + maxMinutes - 1);
            const minutes = Math.min(end - start + 1, maxMinutes);
            onSelectionChange(candles[start]?.time || null, candles[end]?.time || null, minutes);
        } else {
            onSelectionChange(null, null, 0);
        }
    }, [selectionStart, selectionEnd, candles, onSelectionChange, maxMinutes]);

    // Calculate scales
    const { minPrice, maxPrice, priceRange, candleWidth } = useMemo(() => {
        if (candles.length === 0) return { minPrice: 0, maxPrice: 0, priceRange: 1, candleWidth: 1 };

        const prices = candles.flatMap(c => [c.high, c.low]);
        const min = Math.min(...prices);
        const max = Math.max(...prices);
        const range = max - min || 1;

        return {
            minPrice: min - range * 0.05,
            maxPrice: max + range * 0.05,
            priceRange: range * 1.1,
            candleWidth: Math.max(1, (chartWidth / candles.length) * 0.7),
        };
    }, [candles, chartWidth]);

    const xScale = useCallback((i: number) => 
        padding.left + ((i + 0.5) / candles.length) * chartWidth, 
        [candles.length, chartWidth]
    );
    
    const yScale = useCallback((price: number) => 
        padding.top + (1 - (price - minPrice) / priceRange) * chartHeight, 
        [minPrice, priceRange, chartHeight]
    );

    // Get index from mouse position
    const getIndexFromX = useCallback((clientX: number) => {
        if (!svgRef.current || candles.length === 0) return null;
        const rect = svgRef.current.getBoundingClientRect();
        const x = clientX - rect.left - padding.left;
        const index = Math.floor((x / chartWidth) * candles.length);
        return Math.max(0, Math.min(candles.length - 1, index));
    }, [candles.length, chartWidth]);

    // Mouse handlers
    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        const index = getIndexFromX(e.clientX);
        if (index !== null) {
            setIsDragging(true);
            setSelectionStart(index);
            setSelectionEnd(index);
        }
    }, [getIndexFromX]);

    const handleMouseMove = useCallback((e: React.MouseEvent) => {
        const index = getIndexFromX(e.clientX);
        setHoverIndex(index);

        if (isDragging && index !== null) {
            setSelectionEnd(index);
        }
    }, [isDragging, getIndexFromX]);

    const handleMouseUp = useCallback(() => {
        setIsDragging(false);
    }, []);

    const handleMouseLeave = useCallback(() => {
        setHoverIndex(null);
        if (isDragging) {
            setIsDragging(false);
        }
    }, [isDragging]);

    // Computed selection bounds (with limit indicator)
    const selectionBounds = useMemo(() => {
        if (selectionStart === null || selectionEnd === null) return null;

        const start = Math.min(selectionStart, selectionEnd);
        const rawEnd = Math.max(selectionStart, selectionEnd);
        const rawMinutes = rawEnd - start + 1;
        const exceeds = rawMinutes > maxMinutes;
        const end = exceeds ? start + maxMinutes - 1 : rawEnd;

        return {
            startIndex: start,
            endIndex: end,
            x: xScale(start) - candleWidth / 2 - 1,
            width: xScale(end) - xScale(start) + candleWidth + 2,
            minutes: Math.min(rawMinutes, maxMinutes),
            exceeds,
            rawMinutes,
        };
    }, [selectionStart, selectionEnd, xScale, candleWidth, maxMinutes]);

    // Format time for display
    const formatDuration = (minutes: number) => {
        if (minutes < 60) return `${minutes} min`;
        const h = Math.floor(minutes / 60);
        const m = minutes % 60;
        return m > 0 ? `${h}h ${m}m` : `${h}h`;
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-[160px] text-slate-400" style={{ fontFamily }}>
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                <span style={{ fontSize: '10px' }}>Loading {symbol} {date}...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-[160px] text-red-400" style={{ fontFamily, fontSize: '10px' }}>
                {error}
            </div>
        );
    }

    if (candles.length === 0) {
        return (
            <div className="flex items-center justify-center h-[160px] text-slate-400" style={{ fontFamily, fontSize: '10px' }}>
                Select ticker and date above
            </div>
        );
    }

    return (
        <div style={{ fontFamily }}>
            <div className="flex items-center justify-between mb-1 px-1">
                <span className="text-slate-400" style={{ fontSize: '9px' }}>
                    drag to select (max {maxMinutes} min)
                </span>
                {selectionBounds && (
                    <span className={`${selectionBounds.exceeds ? 'text-amber-500' : 'text-slate-600'}`} style={{ fontSize: '9px' }}>
                        {candles[selectionBounds.startIndex]?.time} → {candles[selectionBounds.endIndex]?.time}
                        <span className={`ml-1 ${selectionBounds.exceeds ? 'text-amber-400' : 'text-slate-400'}`}>
                            ({formatDuration(selectionBounds.minutes)}{selectionBounds.exceeds ? ` max` : ''})
                        </span>
                    </span>
                )}
            </div>

            <svg
                ref={svgRef}
                width={width}
                height={height}
                className="block cursor-crosshair select-none"
                style={{ background: '#fafafa' }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseLeave}
            >
                {/* Grid lines */}
                {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
                    const price = minPrice + priceRange * pct;
                    const y = yScale(price);
                    return (
                        <g key={i}>
                            <line 
                                x1={padding.left} 
                                y1={y} 
                                x2={padding.left + chartWidth} 
                                y2={y} 
                                stroke="#e5e7eb" 
                                strokeWidth="0.5" 
                            />
                            <text 
                                x={padding.left - 4} 
                                y={y + 3} 
                                textAnchor="end" 
                                fill="#9ca3af" 
                                style={{ fontSize: '8px' }}
                            >
                                {price.toFixed(2)}
                            </text>
                        </g>
                    );
                })}

                {/* Selection highlight */}
                {selectionBounds && (
                    <rect
                        x={selectionBounds.x}
                        y={padding.top - 2}
                        width={selectionBounds.width}
                        height={chartHeight + 4}
                        fill="rgba(59, 130, 246, 0.12)"
                        stroke="rgba(59, 130, 246, 0.5)"
                        strokeWidth="1"
                        rx="2"
                    />
                )}

                {/* Candlesticks */}
                {candles.map((candle, i) => {
                    const x = xScale(i);
                    const isUp = candle.close >= candle.open;
                    const bodyTop = yScale(Math.max(candle.open, candle.close));
                    const bodyBottom = yScale(Math.min(candle.open, candle.close));
                    const bodyHeight = Math.max(1, bodyBottom - bodyTop);
                    
                    const isSelected = selectionBounds && 
                        i >= selectionBounds.startIndex && 
                        i <= selectionBounds.endIndex;

                    const fillColor = isUp ? '#10b981' : '#ef4444';
                    const strokeColor = isUp ? '#059669' : '#dc2626';

                    return (
                        <g key={i}>
                            {/* Wick */}
                            <line
                                x1={x}
                                y1={yScale(candle.high)}
                                x2={x}
                                y2={yScale(candle.low)}
                                stroke={isSelected ? '#3b82f6' : strokeColor}
                                strokeWidth={isSelected ? 1.5 : 0.8}
                            />
                            {/* Body */}
                            <rect
                                x={x - candleWidth / 2}
                                y={bodyTop}
                                width={candleWidth}
                                height={bodyHeight}
                                fill={isSelected ? '#3b82f6' : fillColor}
                                stroke={isSelected ? '#2563eb' : strokeColor}
                                strokeWidth={0.5}
                                rx={0.5}
                            />
                        </g>
                    );
                })}

                {/* Hover indicator */}
                {hoverIndex !== null && !isDragging && (
                    <>
                        <line
                            x1={xScale(hoverIndex)}
                            y1={padding.top}
                            x2={xScale(hoverIndex)}
                            y2={padding.top + chartHeight}
                            stroke="#64748b"
                            strokeWidth="1"
                            strokeDasharray="3,3"
                            opacity={0.5}
                        />
                        <rect
                            x={xScale(hoverIndex) - 18}
                            y={height - 18}
                            width={36}
                            height={14}
                            fill="white"
                            stroke="#e2e8f0"
                            strokeWidth={0.5}
                            rx={2}
                        />
                        <text
                            x={xScale(hoverIndex)}
                            y={height - 8}
                            textAnchor="middle"
                            fill="#475569"
                            style={{ fontSize: '8px' }}
                        >
                            {candles[hoverIndex]?.time}
                        </text>
                    </>
                )}

                {/* Time labels */}
                {['09:30', '10:30', '11:30', '12:30', '13:30', '14:30', '15:30'].map((time) => {
                    const index = candles.findIndex(c => c.time === time);
                    if (index === -1) return null;
                    return (
                        <text
                            key={time}
                            x={xScale(index)}
                            y={height - 6}
                            textAnchor="middle"
                            fill="#9ca3af"
                            style={{ fontSize: '8px' }}
                        >
                            {time}
                        </text>
                    );
                })}
            </svg>
        </div>
    );
}
