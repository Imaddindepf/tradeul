'use client';

import React, { useMemo } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { type ChatMessage as ChatMessageType } from '@/stores/useChatStore';
import { TickerMention } from './TickerMention';
import { cn } from '@/lib/utils';

interface ChatMessageProps {
  message: ChatMessageType;
}

// Regex for ticker mentions
const TICKER_REGEX = /\$([A-Z]{1,5})\b/g;

export function ChatMessage({ message }: ChatMessageProps) {
  const timeAgo = useMemo(
    () => formatDistanceToNow(new Date(message.created_at), { addSuffix: true }),
    [message.created_at]
  );

  // Parse content and replace ticker mentions with components
  const parsedContent = useMemo(() => {
    const parts: (string | React.ReactNode)[] = [];
    let lastIndex = 0;
    let match;

    const content = message.content;
    const regex = new RegExp(TICKER_REGEX);

    while ((match = regex.exec(content)) !== null) {
      // Add text before the match
      if (match.index > lastIndex) {
        parts.push(content.slice(lastIndex, match.index));
      }

      // Add ticker component
      const ticker = match[1];
      const priceData = message.ticker_prices?.[ticker];
      parts.push(
        <TickerMention 
          key={`${ticker}-${match.index}`}
          symbol={ticker} 
          priceData={priceData}
        />
      );

      lastIndex = regex.lastIndex;
    }

    // Add remaining text
    if (lastIndex < content.length) {
      parts.push(content.slice(lastIndex));
    }

    return parts.length > 0 ? parts : content;
  }, [message.content, message.ticker_prices]);

  // Get initials for avatar
  const initials = message.user_name
    .split(' ')
    .map(n => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  // Random color based on user_id
  const avatarColor = useMemo(() => {
    const colors = [
      'bg-red-500',
      'bg-orange-500',
      'bg-amber-500',
      'bg-emerald-500',
      'bg-teal-500',
      'bg-cyan-500',
      'bg-blue-500',
      'bg-indigo-500',
      'bg-violet-500',
      'bg-purple-500',
      'bg-pink-500',
    ];
    const hash = message.user_id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return colors[hash % colors.length];
  }, [message.user_id]);

  return (
    <div className="group px-4 py-2 hover:bg-muted/30 transition-colors">
      <div className="flex gap-3">
        {/* Avatar */}
        {message.user_avatar ? (
          <img
            src={message.user_avatar}
            alt={message.user_name}
            className="w-9 h-9 rounded-full shrink-0 object-cover"
          />
        ) : (
          <div className={cn(
            "w-9 h-9 rounded-full shrink-0 flex items-center justify-center text-white text-xs font-bold",
            avatarColor
          )}>
            {initials}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="font-semibold text-sm">{message.user_name}</span>
            <span className="text-[10px] text-muted-foreground">{timeAgo}</span>
            {message.edited_at && (
              <span className="text-[10px] text-muted-foreground italic">(edited)</span>
            )}
          </div>

          {/* Message content */}
          <div className="text-sm leading-relaxed break-words">
            {parsedContent}
          </div>

          {/* Reactions */}
          {Object.keys(message.reactions).length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {Object.entries(message.reactions).map(([emoji, userIds]) => (
                <button
                  key={emoji}
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-muted hover:bg-muted/80 text-xs transition-colors"
                >
                  <span>{emoji}</span>
                  <span className="text-muted-foreground">{userIds.length}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

