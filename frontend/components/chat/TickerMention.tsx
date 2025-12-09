'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';

interface TickerMentionProps {
  symbol: string;
  priceData?: {
    price: number;
    change: number;
    changePercent: number;
    volume?: number;
  };
  onClick?: () => void;
}

export function TickerMention({ symbol, priceData, onClick }: TickerMentionProps) {
  const isPositive = priceData && priceData.change > 0;
  const isNegative = priceData && priceData.change < 0;
  const isNeutral = priceData && priceData.change === 0;

  const handleClick = () => {
    if (onClick) {
      onClick();
    } else {
      // Default: open in scanner or chart
      // Could dispatch to a global event or router
      console.log('Ticker clicked:', symbol);
    }
  };

  return (
    <motion.button
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      onClick={handleClick}
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-xs font-semibold transition-colors",
        "bg-primary/10 text-primary hover:bg-primary/20",
        "cursor-pointer"
      )}
    >
      <span className="text-primary">${symbol}</span>
      
      {priceData && (
        <>
          <span className="text-foreground font-mono">
            ${priceData.price.toFixed(2)}
          </span>
          
          <span className={cn(
            "flex items-center gap-0.5",
            isPositive && "text-success",
            isNegative && "text-danger",
            isNeutral && "text-muted-foreground"
          )}>
            {isPositive && <TrendingUp className="w-3 h-3" />}
            {isNegative && <TrendingDown className="w-3 h-3" />}
            {isNeutral && <Minus className="w-3 h-3" />}
            <span>
              {isPositive && '+'}
              {priceData.changePercent.toFixed(2)}%
            </span>
          </span>
        </>
      )}
    </motion.button>
  );
}

