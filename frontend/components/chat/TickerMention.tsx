'use client';

import React from 'react';
import { cn } from '@/lib/utils';

interface TickerMentionProps {
  symbol: string;
  priceData?: {
    price: number;
    change: number;
    changePercent: number;
  };
  onClick?: () => void;
}

export function TickerMention({ symbol, priceData, onClick }: TickerMentionProps) {
  const isPositive = priceData && priceData.change > 0;
  const isNegative = priceData && priceData.change < 0;

  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded",
        "border border-primary/40 hover:border-primary",
        "font-mono text-[11px] cursor-pointer transition-colors"
      )}
    >
      <span className="text-primary font-medium">${symbol}</span>
      {priceData && (
        <>
          <span className="text-muted-foreground/60">·</span>
          <span className="text-foreground/80">{priceData.price.toFixed(2)}</span>
          <span className={cn(
            "text-[10px]",
            isPositive && "text-success",
            isNegative && "text-danger",
            !isPositive && !isNegative && "text-muted-foreground"
          )}>
            {isPositive && '+'}
            {priceData.changePercent.toFixed(1)}%
          </span>
        </>
      )}
    </button>
  );
}

