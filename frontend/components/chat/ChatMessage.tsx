'use client';

import React, { useMemo, useCallback, useState, useRef, useEffect } from 'react';
import { MoreVertical, Copy, Reply, Smile, MessageCircle, CornerDownRight } from 'lucide-react';
import { type ChatMessage as ChatMessageType, useChatStore } from '@/stores/useChatStore';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { useAuth } from '@clerk/nextjs';
import { DescriptionContent } from '@/components/description/DescriptionContent';
import { TickerMention } from './TickerMention';
import { cn } from '@/lib/utils';
import EmojiPicker, { Theme } from 'emoji-picker-react';
import { getUserTimezone } from '@/lib/date-utils';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';

// Quick reactions for fast access
const QUICK_REACTIONS = ['👍', '❤️', '😂', '🚀', '💯', '👀'];

interface ChatMessageProps {
  message: ChatMessageType;
  onScrollToMessage?: (messageId: string) => void;
}

const TICKER_REGEX = /\$([A-Z]{1,5})\b/g;

export function ChatMessage({ message, onScrollToMessage }: ChatMessageProps) {
  const { openWindow } = useFloatingWindow();
  const { getToken, userId } = useAuth();
  const { groups, setGroups, setActiveTarget, messages, activeTarget, getTargetKey } = useChatStore();

  // Find the original message if this is a reply
  const replyToMessage = useMemo(() => {
    if (!message.reply_to_id || !activeTarget) return null;
    const targetKey = getTargetKey(activeTarget);
    const targetMessages = messages[targetKey] || [];
    return targetMessages.find(m => m.id === message.reply_to_id) || null;
  }, [message.reply_to_id, activeTarget, getTargetKey, messages]);
  
  const [showMenu, setShowMenu] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ x: 0, y: 0 });
  const [showReactions, setShowReactions] = useState(false);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
        setShowReactions(false);
        setShowEmojiPicker(false);
      }
    };
    if (showMenu || showReactions || showEmojiPicker) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMenu, showReactions, showEmojiPicker]);

  // Handle right click
  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setMenuPosition({ x: e.clientX, y: e.clientY });
    setShowMenu(true);
  }, []);

  // Copy message
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content);
    setShowMenu(false);
  }, [message.content]);

  // Reply to message
  const handleReply = useCallback(() => {
    useChatStore.getState().setReplyingTo(message);
    setShowMenu(false);
  }, [message]);

  // Toggle reaction (add/remove)
  const handleReaction = useCallback(async (emoji: string) => {
    try {
      const token = await getToken();
      const encodedEmoji = encodeURIComponent(emoji);
      
      // Check if user already reacted with this emoji
      const hasReacted = message.reactions?.[emoji]?.includes(userId || '');
      
      // Toggle: DELETE if already reacted, POST if not
      await fetch(`${CHAT_API_URL}/api/chat/messages/${message.id}/react/${encodedEmoji}`, {
        method: hasReacted ? 'DELETE' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      });
    } catch (error) {
      console.error('Failed to toggle reaction:', error);
    }
    setShowReactions(false);
    setShowEmojiPicker(false);
    setShowMenu(false);
  }, [message.id, message.reactions, userId, getToken]);

  // Open DM with user
  const handleOpenDM = useCallback(async () => {
    if (message.user_id === userId) return; // Can't DM yourself
    
    try {
      const token = await getToken();
      // Create or get existing DM group
      const response = await fetch(`${CHAT_API_URL}/api/chat/groups`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: `DM: ${message.user_name}`,
          is_dm: true,
          member_ids: [message.user_id],
        }),
      });

      if (response.ok) {
        const group = await response.json();
        // Add to groups if not exists
        if (!groups.some(g => g.id === group.id)) {
          setGroups([...groups, group]);
        }
        setActiveTarget({ type: 'group', id: group.id });
      }
    } catch (error) {
      console.error('Failed to open DM:', error);
    }
    setShowMenu(false);
  }, [message.user_id, message.user_name, userId, getToken, groups, setGroups, setActiveTarget]);

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
    return d.toLocaleTimeString('en-US', { timeZone: getUserTimezone(), hour: 'numeric', minute: '2-digit', hour12: true });
  }, [message.created_at]);

  const isOwnMessage = message.user_id === userId;
  const isSystemMessage = message.user_id === 'system' || message.content_type === 'system';

  // Color for replied message author
  const replyNameColor = useMemo(() => {
    if (!replyToMessage) return '';
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
    const hash = replyToMessage.user_id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return colors[hash % colors.length];
  }, [replyToMessage]);

  // System messages have a different style
  if (isSystemMessage) {
    return (
      <div className="flex justify-center py-1">
        <span className="text-[10px] text-muted-foreground/60 bg-muted/30 px-2 py-0.5 rounded-full">
          {message.content}
        </span>
      </div>
    );
  }

  return (
    <>
      <div 
        className="group relative px-1 leading-tight hover:bg-muted/10"
        onContextMenu={handleContextMenu}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Reply quote */}
        {replyToMessage && (
          <button
            onClick={() => onScrollToMessage?.(replyToMessage.id)}
            className="flex items-center gap-1 mb-0.5 pl-2 border-l-2 border-primary/40 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          >
            <CornerDownRight className="w-2.5 h-2.5 opacity-50" />
            <span className={cn("opacity-80", replyNameColor)}>{replyToMessage.user_name}</span>
            <span className="truncate max-w-[200px] opacity-60">{replyToMessage.content}</span>
          </button>
        )}
        
        <span className="text-[9px] text-muted-foreground/40">{time}</span>
        {' '}
        <span className={nameColor}>{message.user_name}</span>
        <span className="text-muted-foreground/30">:</span>
        {' '}
        <span>{parsedContent}</span>

        {/* Reactions display - clean, no background */}
        {message.reactions && Object.keys(message.reactions).length > 0 && (
          <span className="inline-flex items-center gap-0.5 ml-1">
            {Object.entries(message.reactions).map(([emoji, userIds]) => {
              const hasReacted = userIds.includes(userId || '');
              return (
                <button
                  key={emoji}
                  onClick={() => handleReaction(emoji)}
                  className={cn(
                    "inline-flex items-center text-sm transition-all cursor-pointer",
                    "hover:scale-125 active:scale-95",
                    hasReacted && "drop-shadow-[0_0_3px_rgba(59,130,246,0.5)]"
                  )}
                  title={hasReacted 
                    ? `Clic para quitar tu reacción (${userIds.length} total)`
                    : `${userIds.length} ${userIds.length === 1 ? 'reacción' : 'reacciones'}`
                  }
                >
                  <span>{emoji}</span>
                  {userIds.length > 1 && (
                    <span className="text-[9px] text-muted-foreground/70 ml-0.5">{userIds.length}</span>
                  )}
                </button>
              );
            })}
          </span>
        )}

        {/* Three dots menu button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            setMenuPosition({ x: e.clientX, y: e.clientY });
            setShowMenu(true);
          }}
          className={cn(
            "absolute right-1 top-0 p-0.5 rounded transition-opacity",
            "hover:bg-muted text-muted-foreground",
            isHovered ? "opacity-100" : "opacity-0"
          )}
        >
          <MoreVertical className="w-3 h-3" />
        </button>
      </div>

      {/* Context Menu */}
      {showMenu && (
        <div
          ref={menuRef}
          className="fixed z-50 bg-background border border-border rounded-md shadow-lg py-1 min-w-[150px]"
          style={{ 
            left: Math.min(menuPosition.x, window.innerWidth - 160),
            top: Math.min(menuPosition.y, window.innerHeight - 200)
          }}
        >
          <button
            onClick={handleCopy}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-muted transition-colors"
          >
            <Copy className="w-3 h-3" />
            Copiar
          </button>
          
          <button
            onClick={handleReply}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-muted transition-colors"
          >
            <Reply className="w-3 h-3" />
            Responder
          </button>

          <button
            onClick={() => setShowReactions(!showReactions)}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-muted transition-colors"
          >
            <Smile className="w-3 h-3" />
            Reaccionar
          </button>

          {!isOwnMessage && (
            <button
              onClick={handleOpenDM}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-muted transition-colors"
            >
              <MessageCircle className="w-3 h-3" />
              Mensaje directo
            </button>
          )}

          {/* Quick reactions */}
          {showReactions && (
            <div className="border-t border-border mt-1">
              <div className="flex items-center gap-1 px-2 py-1.5">
                {QUICK_REACTIONS.map((emoji) => (
                  <button
                    key={emoji}
                    onClick={() => handleReaction(emoji)}
                    className="p-1 hover:scale-125 transition-transform text-base"
                  >
                    {emoji}
                  </button>
                ))}
                <button
                  onClick={() => setShowEmojiPicker(!showEmojiPicker)}
                  className="p-1 hover:bg-muted rounded text-muted-foreground hover:text-foreground transition-colors ml-1"
                  title="Más emojis"
                >
                  <Smile className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Full emoji picker - minimal white design */}
      {showEmojiPicker && (
        <div 
          className="fixed z-[100] rounded-xl overflow-hidden shadow-[0_4px_20px_rgba(0,0,0,0.08)] border border-gray-100"
          style={{
            left: Math.min(Math.max(menuPosition.x - 100, 10), window.innerWidth - 270),
            top: Math.min(Math.max(menuPosition.y - 50, 10), window.innerHeight - 300),
          }}
        >
          <EmojiPicker
            onEmojiClick={(emojiData) => {
              handleReaction(emojiData.emoji);
              setShowEmojiPicker(false);
            }}
            theme={Theme.LIGHT}
            width={250}
            height={280}
            searchPlaceholder="Buscar..."
            previewConfig={{ showPreview: false }}
            skinTonesDisabled
            lazyLoadEmojis
          />
        </div>
      )}
    </>
  );
}
