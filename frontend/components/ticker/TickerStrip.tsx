'use client';

import { memo, useRef, useEffect, useCallback } from 'react';
import { useRealtimeQuote, QuoteData } from '@/hooks/useRealtimeQuote';
import { getUserTimezone } from '@/lib/date-utils';

// ============================================================================
// Tipos
// ============================================================================

interface TickerStripProps {
  symbol: string;
  exchange?: string;
  previousClose?: number;
  onClose?: () => void;
}

// ============================================================================
// Helpers - Pure functions (no state)
// ============================================================================

const formatPrice = (price: number): string => {
  if (price >= 1000) return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price >= 1) return price.toFixed(2);
  return price.toFixed(4);
};

const formatVolume = (size: number): string => {
  if (size >= 1000000) return `${(size / 1000000).toFixed(1)}M`;
  if (size >= 1000) return `${(size / 1000).toFixed(0)}K`;
  return size.toString();
};

const formatTime = (date: Date): string => {
  return date.toLocaleTimeString('en-US', { timeZone: getUserTimezone(), hour12: false });
};

// ============================================================================
// Componente Principal: TickerStrip (Ultra-optimizado, tema claro)
// ============================================================================

/**
 * Tira compacta de precio en tiempo real
 * 
 * OPTIMIZACIONES:
 * - useRef para DOM updates directos (sin re-render)
 * - requestAnimationFrame para throttling
 * - Sin animaciones de flash (evita parpadeo)
 * - memo con comparador shallow
 */
function TickerStripComponent({ symbol, exchange = 'US', previousClose, onClose }: TickerStripProps) {
  // Refs para actualización directa del DOM (sin re-render)
  const priceRef = useRef<HTMLSpanElement>(null);
  const changeRef = useRef<HTMLSpanElement>(null);
  const bidRef = useRef<HTMLSpanElement>(null);
  const askRef = useRef<HTMLSpanElement>(null);
  const timeRef = useRef<HTMLSpanElement>(null);
  const arrowRef = useRef<HTMLSpanElement>(null);
  
  // Track del último precio para detectar dirección
  const lastPriceRef = useRef<number>(0);
  const rafRef = useRef<number>(0);

  // Callback optimizado para actualizar DOM directamente
  const updateDOM = useCallback((quote: QuoteData) => {
    // Cancelar RAF anterior
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
    }

    // Usar requestAnimationFrame para batch visual updates
    rafRef.current = requestAnimationFrame(() => {
      const midPrice = quote.midPrice;
      const isUp = midPrice >= lastPriceRef.current;
      lastPriceRef.current = midPrice;

      // Actualizar precio (colores del tema claro)
      if (priceRef.current) {
        priceRef.current.textContent = `$${formatPrice(midPrice)}`;
        priceRef.current.className = `font-mono font-semibold ${isUp ? 'text-green-600' : 'text-red-600'}`;
      }

      // Actualizar flecha de dirección
      if (arrowRef.current) {
        arrowRef.current.textContent = isUp ? '▲' : '▼';
        arrowRef.current.className = `text-[10px] ${isUp ? 'text-green-600' : 'text-red-600'}`;
      }

      // Actualizar cambio si hay previousClose
      if (changeRef.current && previousClose) {
        const change = midPrice - previousClose;
        const changePct = ((change / previousClose) * 100);
        const sign = change >= 0 ? '+' : '';
        changeRef.current.textContent = `${sign}${change.toFixed(2)} ${sign}${changePct.toFixed(2)}%`;
        changeRef.current.className = `text-xs font-mono ${change >= 0 ? 'text-green-600' : 'text-red-600'}`;
      }

      // Actualizar bid/ask
      if (bidRef.current) {
        bidRef.current.textContent = `B${formatPrice(quote.bidPrice)}x${formatVolume(quote.bidSize)}`;
      }
      if (askRef.current) {
        askRef.current.textContent = `${formatPrice(quote.askPrice)}x${formatVolume(quote.askSize)}A`;
      }

      // Actualizar timestamp y latencia
      if (timeRef.current) {
        const latencyInfo = (quote as any)._latency;
        if (latencyInfo && latencyInfo.latencyMs !== null) {
          const endToEndLatency = Date.now() - latencyInfo.polygonTs;
          timeRef.current.textContent = `${formatTime(quote.lastUpdate)} | ${endToEndLatency}ms`;
        } else {
          timeRef.current.textContent = `At: ${formatTime(quote.lastUpdate)}`;
        }
      }
    });
  }, [previousClose]);

  // Suscribirse a quotes
  const { quote, isLoading } = useRealtimeQuote(symbol);

  // Actualizar DOM cuando llega un quote (sin causar re-render)
  useEffect(() => {
    if (quote) {
      updateDOM(quote);
    }
  }, [quote, updateDOM]);

  // Cleanup RAF on unmount
  useEffect(() => {
    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs font-mono">
        <span className="text-slate-600 font-semibold">{symbol}</span>
        <span className="text-slate-400">...</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-xs font-mono select-none">
      {/* Symbol & Exchange */}
      <span className="font-bold text-slate-800">{symbol}</span>
      <span className="text-slate-400 text-[10px]">{exchange}</span>

      {/* Direction Arrow */}
      <span ref={arrowRef} className="text-[10px] text-slate-400">▲</span>

      {/* Price */}
      <span ref={priceRef} className="font-semibold text-slate-800">
        {quote ? `$${formatPrice(quote.midPrice)}` : '--'}
      </span>

      {/* Bid/Ask compact */}
      <span className="text-slate-400">
        <span ref={bidRef} className="text-green-600">
          {quote ? `B${formatPrice(quote.bidPrice)}` : 'B--'}
        </span>
        <span className="text-slate-300">/</span>
        <span ref={askRef} className="text-red-500">
          {quote ? `${formatPrice(quote.askPrice)}A` : '--A'}
        </span>
      </span>

      {/* Timestamp */}
      <span ref={timeRef} className="text-slate-400 text-[10px]">
        {quote ? formatTime(quote.lastUpdate) : '--:--:--'}
      </span>

      {/* Live indicator */}
      <span className="relative flex h-1.5 w-1.5">
        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500" />
      </span>
    </div>
  );
}

// Memo con comparador shallow para evitar re-renders innecesarios
export const TickerStrip = memo(TickerStripComponent, (prevProps, nextProps) => {
  return (
    prevProps.symbol === nextProps.symbol &&
    prevProps.exchange === nextProps.exchange &&
    prevProps.previousClose === nextProps.previousClose
  );
});

export default TickerStrip;

