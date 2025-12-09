'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Send, Smile, AtSign, DollarSign, Paperclip } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth, useUser } from '@clerk/nextjs';
import { useChatStore } from '@/stores/useChatStore';
import { useChatWebSocket } from '@/hooks/useChatWebSocket';
import { cn } from '@/lib/utils';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'http://localhost:8016';

// Common tickers for suggestions
const POPULAR_TICKERS = ['AAPL', 'TSLA', 'NVDA', 'AMD', 'META', 'GOOGL', 'AMZN', 'MSFT', 'SPY', 'QQQ'];

export function ChatInput() {
  const [content, setContent] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [showTickerPicker, setShowTickerPicker] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const pickerRef = useRef<HTMLDivElement>(null);

  const { isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const { activeTarget, addMessage, getTargetKey } = useChatStore();
  const { sendTyping } = useChatWebSocket();

  // Close picker on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setShowTickerPicker(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Handle typing
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setContent(value);

    // Send typing indicator
    if (activeTarget && value.length > 0) {
      sendTyping(activeTarget);
    }

    // Check for $ at end for ticker picker
    if (value.endsWith('$')) {
      setShowTickerPicker(true);
    } else {
      setShowTickerPicker(false);
    }
  };

  // Insert ticker
  const insertTicker = useCallback((ticker: string) => {
    // Replace trailing $ with $TICKER
    if (content.endsWith('$')) {
      setContent(content.slice(0, -1) + `$${ticker} `);
    } else {
      setContent(content + `$${ticker} `);
    }
    setShowTickerPicker(false);
    inputRef.current?.focus();
  }, [content]);

  // Send message
  const handleSend = async () => {
    if (!content.trim() || !activeTarget || isSending) return;

    if (!isSignedIn) {
      alert('Please sign in to send messages');
      return;
    }

    setIsSending(true);
    const messageContent = content.trim();
    setContent('');

    try {
      const token = await getToken();
      
      const response = await fetch(`${CHAT_API_URL}/api/chat/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          content: messageContent,
          channel_id: activeTarget.type === 'channel' ? activeTarget.id : undefined,
          group_id: activeTarget.type === 'group' ? activeTarget.id : undefined,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to send message');
      }

      // Message will arrive via WebSocket
    } catch (error) {
      console.error('Failed to send message:', error);
      // Restore content on error
      setContent(messageContent);
    } finally {
      setIsSending(false);
    }
  };

  // Handle enter key
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="relative border-t border-border p-3">
      {/* Ticker Picker */}
      <AnimatePresence>
        {showTickerPicker && (
          <motion.div
            ref={pickerRef}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute bottom-full left-3 right-3 mb-2 p-2 bg-background border border-border rounded-lg shadow-lg z-10"
          >
            <p className="text-xs text-muted-foreground mb-2">Popular tickers:</p>
            <div className="flex flex-wrap gap-1.5">
              {POPULAR_TICKERS.map((ticker) => (
                <button
                  key={ticker}
                  onClick={() => insertTicker(ticker)}
                  className="px-2 py-1 text-xs font-mono bg-primary/10 text-primary rounded hover:bg-primary/20 transition-colors"
                >
                  ${ticker}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input Area */}
      <div className="flex items-end gap-2">
        {/* Action buttons */}
        <div className="flex gap-1 pb-2">
          <button
            onClick={() => setShowTickerPicker(!showTickerPicker)}
            className={cn(
              "p-1.5 rounded-lg transition-colors",
              showTickerPicker ? "bg-primary text-white" : "hover:bg-muted text-muted-foreground"
            )}
            title="Insert ticker ($)"
          >
            <DollarSign className="w-4 h-4" />
          </button>
        </div>

        {/* Text input */}
        <div className="flex-1 relative">
          <textarea
            ref={inputRef}
            value={content}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={isSignedIn ? "Type a message... Use $ for tickers" : "Sign in to chat"}
            disabled={!isSignedIn || isSending}
            rows={1}
            className={cn(
              "w-full px-3 py-2 text-sm rounded-lg resize-none",
              "bg-muted border-0 focus:ring-2 focus:ring-primary/50 focus:outline-none",
              "placeholder:text-muted-foreground",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "max-h-32"
            )}
            style={{
              minHeight: '40px',
              height: 'auto',
            }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = 'auto';
              target.style.height = Math.min(target.scrollHeight, 128) + 'px';
            }}
          />
        </div>

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!content.trim() || !isSignedIn || isSending}
          className={cn(
            "p-2.5 rounded-lg transition-colors mb-0.5",
            content.trim() && isSignedIn
              ? "bg-primary text-white hover:bg-primary-hover"
              : "bg-muted text-muted-foreground cursor-not-allowed"
          )}
        >
          <Send className="w-4 h-4" />
        </button>
      </div>

      {/* Character count */}
      {content.length > 3500 && (
        <div className="absolute bottom-1 right-16 text-[10px] text-muted-foreground">
          {content.length}/4000
        </div>
      )}
    </div>
  );
}

