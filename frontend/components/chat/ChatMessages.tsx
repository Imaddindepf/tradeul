'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@clerk/nextjs';
import { useChatStore, selectTypingUsers, type ChatMessage as ChatMessageType } from '@/stores/useChatStore';
import { ChatMessage } from './ChatMessage';
import { motion, AnimatePresence } from 'framer-motion';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';

export function ChatMessages() {
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const { getToken } = useAuth();

  const {
    activeTarget,
    getTargetKey,
    messages,
    addMessages,
    setHasMoreMessages,
    hasMoreMessages,
    isLoadingMessages,
    setLoadingMessages
  } = useChatStore();

  const typingUsers = useChatStore(selectTypingUsers);

  const targetKey = activeTarget ? getTargetKey(activeTarget) : null;
  const currentMessages = targetKey ? messages[targetKey] || [] : [];
  const hasMore = targetKey ? hasMoreMessages[targetKey] ?? true : false;

  // Load messages when target changes (only if not already loaded)
  useEffect(() => {
    if (!activeTarget) return;

    // Skip if already have messages for this target
    const key = `${activeTarget.type}:${activeTarget.id}`;
    if (currentMessages.length > 0) return;

    const loadMessages = async () => {
      setLoadingMessages(true);
      try {
        const endpoint = activeTarget.type === 'channel'
          ? `${CHAT_API_URL}/api/chat/messages/channel/${activeTarget.id}`
          : `${CHAT_API_URL}/api/chat/messages/group/${activeTarget.id}`;

        // Groups require auth
        const headers: Record<string, string> = {};
        if (activeTarget.type === 'group') {
          const token = await getToken();
          if (token) headers['Authorization'] = `Bearer ${token}`;
        }

        const res = await fetch(endpoint, { headers });
        if (res.ok) {
          const data = await res.json();
          addMessages(key, data);
          setHasMoreMessages(key, data.length >= 50);
        }
      } catch (error) {
        console.error('Failed to load messages:', error);
      } finally {
        setLoadingMessages(false);
      }
    };

    loadMessages();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTarget?.id, activeTarget?.type]);

  // Load more (older messages)
  const loadMore = useCallback(async () => {
    const target = useChatStore.getState().activeTarget;
    const key = target ? `${target.type}:${target.id}` : null;
    const msgs = key ? useChatStore.getState().messages[key] || [] : [];
    const hasMoreMsgs = key ? useChatStore.getState().hasMoreMessages[key] ?? true : false;

    if (!target || isLoadingMore || !hasMoreMsgs || msgs.length === 0) return;

    setIsLoadingMore(true);
    try {
      const oldestId = msgs[0]?.id;
      const endpoint = target.type === 'channel'
        ? `${CHAT_API_URL}/api/chat/messages/channel/${target.id}?before=${oldestId}`
        : `${CHAT_API_URL}/api/chat/messages/group/${target.id}?before=${oldestId}`;

      const headers: Record<string, string> = {};
      if (target.type === 'group') {
        const token = await getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(endpoint, { headers });
      if (res.ok) {
        const data = await res.json();
        if (data.length > 0) {
          addMessages(key!, data, true); // prepend
        }
        setHasMoreMessages(key!, data.length >= 50);
      }
    } catch (error) {
      console.error('Failed to load more messages:', error);
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore, addMessages, setHasMoreMessages, getToken]);

  // Scroll to bottom on new messages
  useEffect(() => {
    if (currentMessages.length > 0) {
      virtuosoRef.current?.scrollToIndex({
        index: currentMessages.length - 1,
        behavior: 'smooth',
      });
    }
  }, [currentMessages.length]);

  // Scroll to a specific message (for reply quotes)
  const scrollToMessage = useCallback((messageId: string) => {
    const index = currentMessages.findIndex(m => m.id === messageId);
    if (index !== -1) {
      virtuosoRef.current?.scrollToIndex({
        index,
        behavior: 'smooth',
        align: 'center',
      });
    }
  }, [currentMessages]);

  if (isLoadingMessages) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col relative">
      {currentMessages.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted-foreground">
          <p>No messages yet. Start the conversation!</p>
        </div>
      ) : (
        <Virtuoso
          ref={virtuosoRef}
          data={currentMessages}
          startReached={loadMore}
          initialTopMostItemIndex={currentMessages.length - 1}
          followOutput="smooth"
          itemContent={(_index: number, message: ChatMessageType) => (
            <ChatMessage
              key={message.id}
              message={message}
              onScrollToMessage={scrollToMessage}
            />
          )}
          components={{
            Header: () => (
              isLoadingMore ? (
                <div className="text-center py-0.5 text-[10px] text-muted-foreground/50">...</div>
              ) : hasMore ? (
                <button onClick={loadMore} className="w-full py-0.5 text-[10px] text-primary/60 hover:text-primary">more</button>
              ) : null
            ),
            Footer: () => <div className="h-5" />, // Space for typing indicator
          }}
          className="flex-1"
        />
      )}

      {/* Typing indicator */}
      <AnimatePresence>
        {typingUsers.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute bottom-0 left-1 text-[10px] text-muted-foreground/60"
          >
            {typingUsers.length === 1 ? `${typingUsers[0].user_name}...` : `${typingUsers.length} typing...`}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

