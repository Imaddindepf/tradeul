'use client';

import React, { useMemo, useCallback } from 'react';
import { type ChatMessage as ChatMessageType } from '@/stores/useChatStore';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { DescriptionContent } from '@/components/description/DescriptionContent';
import { TickerMention } from './TickerMention';

interface ChatMessageProps {
  message: ChatMessageType;
}

const TICKER_REGEX = /\$([A-Z]{1,5})\b/g;

export function ChatMessage({ message }: ChatMessageProps) {
  const { openWindow } = useFloatingWindow();

  // Open description window for ticker
  const openTickerDescription = useCallback((symbol: string) => {
    const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;
    
    openWindow({
      title: `Description: ${symbol}`,
      content: <DescriptionContent ticker={symbol} exchange="NASDAQ" />,
      width: 1100,
      height: 700,
      x: Math.max(50, screenWidth / 2 - 550),
      y: Math.max(70, screenHeight / 2 - 350),
      minWidth: 900,
      minHeight: 550,
    });
  }, [openWindow]);

  // Parse tickers
  const parsedContent = useMemo(() => {
    const parts: (string | React.ReactNode)[] = [];
    let lastIndex = 0;
    let match;
    const content = message.content;
    const regex = new RegExp(TICKER_REGEX);

    while ((match = regex.exec(content)) !== null) {
      if (match.index > lastIndex) {
        parts.push(content.slice(lastIndex, match.index));
      }
      const ticker = match[1];
      const priceData = message.ticker_prices?.[ticker];
      parts.push(
        <TickerMention 
          key={`${ticker}-${match.index}`}
          symbol={ticker} 
          priceData={priceData}
          onClick={() => openTickerDescription(ticker)}
        />
      );
      lastIndex = regex.lastIndex;
    }

    if (lastIndex < content.length) {
      parts.push(content.slice(lastIndex));
    }

    return parts.length > 0 ? parts : content;
  }, [message.content, message.ticker_prices]);

  // Color based on user_id
  const nameColor = useMemo(() => {
    const colors = [
      'text-red-400',
      'text-orange-400',
      'text-amber-400',
      'text-emerald-400',
      'text-cyan-400',
      'text-blue-400',
      'text-violet-400',
      'text-pink-400',
    ];
    const hash = message.user_id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return colors[hash % colors.length];
  }, [message.user_id]);

  // Format time as h:mm AM/PM
  const time = useMemo(() => {
    const d = new Date(message.created_at);
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  }, [message.created_at]);

  return (
    <div className="px-1 leading-tight hover:bg-muted/10">
      <span className="text-[9px] text-muted-foreground/40">{time}</span>
      {' '}
      <span className={nameColor}>{message.user_name}</span>
      <span className="text-muted-foreground/30">:</span>
      {' '}
      <span>{parsedContent}</span>
    </div>
  );
}
