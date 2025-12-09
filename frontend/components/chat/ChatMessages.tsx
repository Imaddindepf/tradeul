'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';
import { Loader2 } from 'lucide-react';
import { useChatStore, selectTypingUsers } from '@/stores/useChatStore';
import { ChatMessage } from './ChatMessage';
import { motion, AnimatePresence } from 'framer-motion';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'http://localhost:8016';

export function ChatMessages() {
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  
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

  // Initial load
  useEffect(() => {
    if (!activeTarget) return;

    const loadMessages = async () => {
      setLoadingMessages(true);
      try {
        const endpoint = activeTarget.type === 'channel'
          ? `${CHAT_API_URL}/api/chat/messages/channel/${activeTarget.id}`
          : `${CHAT_API_URL}/api/chat/messages/group/${activeTarget.id}`;

        const res = await fetch(endpoint, { credentials: 'include' });
        if (res.ok) {
          const data = await res.json();
          addMessages(getTargetKey(activeTarget), data);
          setHasMoreMessages(getTargetKey(activeTarget), data.length >= 50);
        }
      } catch (error) {
        console.error('Failed to load messages:', error);
      } finally {
        setLoadingMessages(false);
      }
    };

    // Only load if we don't have messages
    if (currentMessages.length === 0) {
      loadMessages();
    }
  }, [activeTarget, currentMessages.length, addMessages, getTargetKey, setHasMoreMessages, setLoadingMessages]);

  // Load more (older messages)
  const loadMore = useCallback(async () => {
    if (!activeTarget || isLoadingMore || !hasMore || currentMessages.length === 0) return;

    setIsLoadingMore(true);
    try {
      const oldestId = currentMessages[0]?.id;
      const endpoint = activeTarget.type === 'channel'
        ? `${CHAT_API_URL}/api/chat/messages/channel/${activeTarget.id}?before=${oldestId}`
        : `${CHAT_API_URL}/api/chat/messages/group/${activeTarget.id}?before=${oldestId}`;

      const res = await fetch(endpoint, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        if (data.length > 0) {
          addMessages(getTargetKey(activeTarget), data, true); // prepend
        }
        setHasMoreMessages(getTargetKey(activeTarget), data.length >= 50);
      }
    } catch (error) {
      console.error('Failed to load more messages:', error);
    } finally {
      setIsLoadingMore(false);
    }
  }, [activeTarget, isLoadingMore, hasMore, currentMessages, addMessages, getTargetKey, setHasMoreMessages]);

  // Scroll to bottom on new messages
  useEffect(() => {
    if (currentMessages.length > 0) {
      virtuosoRef.current?.scrollToIndex({
        index: currentMessages.length - 1,
        behavior: 'smooth',
      });
    }
  }, [currentMessages.length]);

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
          itemContent={(index, message) => (
            <ChatMessage key={message.id} message={message} />
          )}
          components={{
            Header: () => (
              isLoadingMore ? (
                <div className="flex justify-center py-2">
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                </div>
              ) : hasMore ? (
                <div className="flex justify-center py-2">
                  <button 
                    onClick={loadMore}
                    className="text-xs text-primary hover:underline"
                  >
                    Load more
                  </button>
                </div>
              ) : null
            ),
          }}
          className="flex-1"
        />
      )}

      {/* Typing indicator */}
      <AnimatePresence>
        {typingUsers.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute bottom-0 left-0 right-0 px-4 py-2 bg-gradient-to-t from-background"
          >
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="flex gap-0.5">
                <span className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
              <span>
                {typingUsers.length === 1
                  ? `${typingUsers[0].user_name} is typing...`
                  : `${typingUsers.length} people are typing...`}
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

