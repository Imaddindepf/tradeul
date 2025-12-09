'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Send, DollarSign, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth, useUser } from '@clerk/nextjs';
import { useChatStore } from '@/stores/useChatStore';
import { useChatWebSocket } from '@/hooks/useChatWebSocket';
import { cn } from '@/lib/utils';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://tradeul.com';

interface TickerResult {
  symbol: string;
  name: string;
  type?: string;
}

export function ChatInput() {
  const [content, setContent] = useState('');
  const [isSending, setIsSending] = useState(false);
  
  // Ticker search state
  const [showTickerSearch, setShowTickerSearch] = useState(false);
  const [tickerQuery, setTickerQuery] = useState('');
  const [tickerResults, setTickerResults] = useState<TickerResult[]>([]);
  const [tickerLoading, setTickerLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  
  const inputRef = useRef<HTMLInputElement>(null);
  const tickerInputRef = useRef<HTMLInputElement>(null);
  const pickerRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const { isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const { activeTarget, addMessage, getTargetKey } = useChatStore();
  const { sendTyping } = useChatWebSocket();

  // Close picker on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setShowTickerSearch(false);
        setTickerQuery('');
        setTickerResults([]);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Focus ticker input when opened
  useEffect(() => {
    if (showTickerSearch) {
      tickerInputRef.current?.focus();
    }
  }, [showTickerSearch]);

  // Search tickers
  useEffect(() => {
    if (!tickerQuery || tickerQuery.length < 1) {
      setTickerResults([]);
      return;
    }

    // Cancel previous request
    if (abortRef.current) {
      abortRef.current.abort();
    }
    abortRef.current = new AbortController();

    const timer = setTimeout(async () => {
      setTickerLoading(true);
      try {
        const response = await fetch(
          `${API_URL}/api/v1/metadata/search?q=${encodeURIComponent(tickerQuery)}&limit=8`,
          { signal: abortRef.current?.signal }
        );
        if (response.ok) {
          const data = await response.json();
          setTickerResults(data.results || []);
          setSelectedIndex(0);
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          console.error('Ticker search error:', err);
        }
      } finally {
        setTickerLoading(false);
      }
    }, 150);

    return () => clearTimeout(timer);
  }, [tickerQuery]);

  // Handle typing in main input
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setContent(value);

    if (activeTarget && value.length > 0) {
      sendTyping(activeTarget);
    }

    // Open ticker search when $ is typed
    if (value.endsWith('$')) {
      setShowTickerSearch(true);
      setTickerQuery('');
    }
  };

  // Insert ticker
  const insertTicker = useCallback((symbol: string) => {
    // Remove trailing $ if present
    const base = content.endsWith('$') ? content.slice(0, -1) : content;
    setContent(base + `$${symbol} `);
    setShowTickerSearch(false);
    setTickerQuery('');
    setTickerResults([]);
    inputRef.current?.focus();
  }, [content]);

  // Handle ticker search keyboard
  const handleTickerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setShowTickerSearch(false);
      setTickerQuery('');
      inputRef.current?.focus();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(i => Math.min(i + 1, tickerResults.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && tickerResults.length > 0) {
      e.preventDefault();
      insertTicker(tickerResults[selectedIndex].symbol);
    }
  };

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
      const displayName = user?.username || user?.fullName || user?.firstName || 'anon';
      
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
          user_name: displayName,
          user_avatar: user?.imageUrl,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to send message');
      }

      // Add message to store immediately (optimistic update)
      const data = await response.json();
      const targetKey = getTargetKey(activeTarget);
      addMessage(targetKey, data);
    } catch (error) {
      console.error('Failed to send message:', error);
      setContent(messageContent);
    } finally {
      setIsSending(false);
    }
  };

  // Handle enter key
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="relative border-t border-border px-2 py-1.5">
      {/* Ticker Search Dropdown */}
      <AnimatePresence>
        {showTickerSearch && (
          <motion.div
            ref={pickerRef}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 5 }}
            className="absolute bottom-full left-2 right-2 mb-1 bg-background border border-border rounded shadow-lg z-10"
          >
            {/* Search input */}
            <div className="p-1.5 border-b border-border">
              <input
                ref={tickerInputRef}
                type="text"
                value={tickerQuery}
                onChange={(e) => setTickerQuery(e.target.value.toUpperCase())}
                onKeyDown={handleTickerKeyDown}
                placeholder="Search ticker..."
                className="w-full px-2 py-1 text-xs bg-muted rounded focus:outline-none focus:ring-1 focus:ring-primary/50"
                autoComplete="off"
              />
            </div>
            
            {/* Results */}
            <div className="max-h-40 overflow-y-auto">
              {tickerLoading ? (
                <div className="flex items-center justify-center py-2">
                  <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
                </div>
              ) : tickerResults.length > 0 ? (
                tickerResults.map((result, idx) => (
                  <button
                    key={result.symbol}
                    onClick={() => insertTicker(result.symbol)}
                    className={cn(
                      "w-full px-2 py-1 text-left text-xs flex items-center gap-2 transition-colors",
                      idx === selectedIndex ? "bg-primary/20" : "hover:bg-muted"
                    )}
                  >
                    <span className="font-mono font-medium text-primary">${result.symbol}</span>
                    <span className="text-muted-foreground truncate text-[10px]">{result.name}</span>
                  </button>
                ))
              ) : tickerQuery.length > 0 ? (
                <div className="px-2 py-2 text-[10px] text-muted-foreground text-center">
                  No results
                </div>
              ) : (
                <div className="px-2 py-2 text-[10px] text-muted-foreground text-center">
                  Type to search...
                </div>
              )}
            </div>
            
            {/* Help text */}
            <div className="px-2 py-1 border-t border-border text-[9px] text-muted-foreground/60">
              ↑↓ navigate · Enter select · Esc cancel
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input Area */}
      <div className="flex items-center gap-1.5">
        {/* Ticker button */}
        <button
          onClick={() => setShowTickerSearch(!showTickerSearch)}
          className={cn(
            "p-1 rounded transition-colors shrink-0",
            showTickerSearch ? "bg-primary text-white" : "hover:bg-muted text-muted-foreground"
          )}
          title="Insert ticker ($)"
        >
          <DollarSign className="w-3.5 h-3.5" />
        </button>

        {/* Text input */}
        <input
          ref={inputRef}
          type="text"
          value={content}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder={isSignedIn ? "Message... ($ for ticker)" : "Sign in"}
          disabled={!isSignedIn || isSending}
          className={cn(
            "flex-1 px-2 py-1 text-xs rounded bg-muted border-0",
            "focus:ring-1 focus:ring-primary/50 focus:outline-none",
            "placeholder:text-muted-foreground/60",
            "disabled:opacity-50"
          )}
        />

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!content.trim() || !isSignedIn || isSending}
          className={cn(
            "p-1 rounded transition-colors shrink-0",
            content.trim() && isSignedIn
              ? "bg-primary text-white hover:bg-primary-hover"
              : "bg-muted text-muted-foreground/40"
          )}
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
