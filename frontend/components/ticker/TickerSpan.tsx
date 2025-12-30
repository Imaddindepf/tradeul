'use client';

import { memo, useMemo } from 'react';
import { useRealtimeQuote, QuoteData } from '@/hooks/useRealtimeQuote';
import { cn } from '@/lib/utils';
import { getUserTimezone } from '@/lib/date-utils';

// ============================================================================
// Tipos
// ============================================================================

interface TickerSpanProps {
  symbol: string;
  showBidAsk?: boolean;
  showSpread?: boolean;
  showChange?: boolean;
  previousClose?: number;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  variant?: 'default' | 'compact' | 'detailed';
  className?: string;
}

// ============================================================================
// Helpers
// ============================================================================

function formatPrice(price: number): string {
  if (price >= 1000) {
    return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (price >= 1) {
    return price.toFixed(2);
  }
  return price.toFixed(4);
}

function formatChange(current: number, previous: number): { value: string; percent: string; isPositive: boolean } {
  const change = current - previous;
  const percent = ((change / previous) * 100);
  const isPositive = change >= 0;
  
  return {
    value: `${isPositive ? '+' : ''}${change.toFixed(2)}`,
    percent: `${isPositive ? '+' : ''}${percent.toFixed(2)}%`,
    isPositive
  };
}

function formatVolume(size: number): string {
  if (size >= 1000000) return `${(size / 1000000).toFixed(1)}M`;
  if (size >= 1000) return `${(size / 1000).toFixed(1)}K`;
  return size.toString();
}

// ============================================================================
// Subcomponentes
// ============================================================================

const LoadingSpan = memo(function LoadingSpan({ size }: { size: string }) {
  const sizeClasses = {
    sm: 'h-4 w-12',
    md: 'h-5 w-16',
    lg: 'h-6 w-20',
    xl: 'h-8 w-24',
  };
  
  return (
    <span className={cn(
      'inline-block animate-pulse bg-muted rounded',
      sizeClasses[size as keyof typeof sizeClasses]
    )} />
  );
});

const NoDataSpan = memo(function NoDataSpan({ symbol }: { symbol: string }) {
  return (
    <span className="text-muted-foreground">
      {symbol} --
    </span>
  );
});

// ============================================================================
// Componente Principal: TickerSpan
// ============================================================================

/**
 * Muestra precio en tiempo real de un ticker
 * 
 * Variantes:
 * - default: Precio mid con indicador de cambio
 * - compact: Solo precio
 * - detailed: Bid/Ask, spread, cambio
 * 
 * @example
 * ```tsx
 * <TickerSpan symbol="AAPL" />
 * <TickerSpan symbol="TSLA" variant="detailed" showChange previousClose={180.50} />
 * <TickerSpan symbol="NVDA" size="xl" className="font-bold" />
 * ```
 */
function TickerSpanComponent({
  symbol,
  showBidAsk = false,
  showSpread = false,
  showChange = false,
  previousClose,
  size = 'md',
  variant = 'default',
  className,
}: TickerSpanProps) {
  const { quote, isLoading } = useRealtimeQuote(symbol);

  const sizeClasses = useMemo(() => ({
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
    xl: 'text-lg',
  }), []);

  // Calcular cambio si tenemos previousClose
  const change = useMemo(() => {
    if (!showChange || !previousClose || !quote) return null;
    return formatChange(quote.midPrice, previousClose);
  }, [showChange, previousClose, quote]);

  if (isLoading) {
    return <LoadingSpan size={size} />;
  }

  if (!quote) {
    return <NoDataSpan symbol={symbol} />;
  }

  // Render según variante
  if (variant === 'compact') {
    return (
      <span className={cn(sizeClasses[size], 'font-mono', className)}>
        ${formatPrice(quote.midPrice)}
      </span>
    );
  }

  if (variant === 'detailed') {
    return (
      <span className={cn('inline-flex items-center gap-2', sizeClasses[size], className)}>
        {/* Símbolo */}
        <span className="font-semibold text-foreground">{symbol}</span>
        
        {/* Precio Mid */}
        <span className="font-mono font-medium">
          ${formatPrice(quote.midPrice)}
        </span>
        
        {/* Bid/Ask */}
        {showBidAsk && (
          <span className="text-muted-foreground text-xs">
            <span className="text-green-500">{formatPrice(quote.bidPrice)}</span>
            <span className="mx-1">×</span>
            <span className="text-red-500">{formatPrice(quote.askPrice)}</span>
          </span>
        )}
        
        {/* Spread */}
        {showSpread && (
          <span className="text-muted-foreground text-xs">
            ({quote.spreadPercent.toFixed(2)}%)
          </span>
        )}
        
        {/* Cambio */}
        {change && (
          <span className={cn(
            'text-xs font-medium',
            change.isPositive ? 'text-green-500' : 'text-red-500'
          )}>
            {change.value} ({change.percent})
          </span>
        )}
      </span>
    );
  }

  // Default variant
  return (
    <span className={cn('inline-flex items-center gap-1.5', sizeClasses[size], className)}>
      <span className="font-mono font-medium">
        ${formatPrice(quote.midPrice)}
      </span>
      
      {change && (
        <span className={cn(
          'text-xs',
          change.isPositive ? 'text-green-500' : 'text-red-500'
        )}>
          {change.percent}
        </span>
      )}
    </span>
  );
}

export const TickerSpan = memo(TickerSpanComponent);

// ============================================================================
// Componente: TickerCard (para mostrar en floating window)
// ============================================================================

interface TickerCardProps {
  symbol: string;
  previousClose?: number;
  companyName?: string;
  className?: string;
}

function TickerCardComponent({
  symbol,
  previousClose,
  companyName,
  className,
}: TickerCardProps) {
  const { quote, isLoading } = useRealtimeQuote(symbol);

  const change = useMemo(() => {
    if (!previousClose || !quote) return null;
    return formatChange(quote.midPrice, previousClose);
  }, [previousClose, quote]);

  if (isLoading) {
    return (
      <div className={cn('p-4 rounded-lg bg-card border animate-pulse', className)}>
        <div className="h-6 w-20 bg-muted rounded mb-2" />
        <div className="h-8 w-32 bg-muted rounded mb-2" />
        <div className="h-4 w-24 bg-muted rounded" />
      </div>
    );
  }

  if (!quote) {
    return (
      <div className={cn('p-4 rounded-lg bg-card border', className)}>
        <div className="text-lg font-bold">{symbol}</div>
        <div className="text-muted-foreground">No quote data available</div>
      </div>
    );
  }

  return (
    <div className={cn(
      'p-4 rounded-lg bg-card border transition-all duration-200',
      'hover:shadow-md hover:border-primary/50',
      className
    )}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-lg font-bold text-foreground">{symbol}</div>
          {companyName && (
            <div className="text-xs text-muted-foreground truncate max-w-[200px]">
              {companyName}
            </div>
          )}
        </div>
        
        {/* Indicador de live */}
        <div className="flex items-center gap-1">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
          </span>
          <span className="text-xs text-muted-foreground">LIVE</span>
        </div>
      </div>

      {/* Precio Principal */}
      <div className="text-3xl font-bold font-mono mb-2">
        ${formatPrice(quote.midPrice)}
      </div>

      {/* Cambio */}
      {change && (
        <div className={cn(
          'text-sm font-medium mb-3',
          change.isPositive ? 'text-green-500' : 'text-red-500'
        )}>
          {change.value} ({change.percent})
        </div>
      )}

      {/* Bid/Ask Table */}
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="bg-green-500/10 rounded p-2">
          <div className="text-xs text-muted-foreground mb-1">Bid</div>
          <div className="font-mono text-green-500 font-medium">
            ${formatPrice(quote.bidPrice)}
          </div>
          <div className="text-xs text-muted-foreground">
            {formatVolume(quote.bidSize)} shares
          </div>
        </div>
        
        <div className="bg-red-500/10 rounded p-2">
          <div className="text-xs text-muted-foreground mb-1">Ask</div>
          <div className="font-mono text-red-500 font-medium">
            ${formatPrice(quote.askPrice)}
          </div>
          <div className="text-xs text-muted-foreground">
            {formatVolume(quote.askSize)} shares
          </div>
        </div>
      </div>

      {/* Spread */}
      <div className="mt-3 pt-3 border-t flex justify-between text-xs text-muted-foreground">
        <span>Spread</span>
        <span className="font-mono">
          ${quote.spread.toFixed(4)} ({quote.spreadPercent.toFixed(2)}%)
        </span>
      </div>

      {/* Last Update */}
      <div className="mt-2 text-xs text-muted-foreground text-right">
        Updated: {quote.lastUpdate.toLocaleTimeString('en-US', { timeZone: getUserTimezone(), hour: '2-digit', minute: '2-digit', hour12: false })}
      </div>
    </div>
  );
}

export const TickerCard = memo(TickerCardComponent);

export default TickerSpan;

