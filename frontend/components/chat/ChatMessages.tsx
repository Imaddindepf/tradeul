'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@clerk/nextjs';
import { useChatStore, selectTypingUsers, type ChatMessage as ChatMessageType } from '@/stores/useChatStore';
import { ChatMessage } from './ChatMessage';
import { motion, AnimatePresence } from 'framer-motion';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';
const PAGE_SIZE = 50;
const MAX_MESSAGES_IN_VIEW = 500; // Límite para rendimiento

/**
 * ChatMessages - Lista invertida con flex-direction: column-reverse
 * 
 * Técnica probada que funciona:
 * - CSS flex-direction: column-reverse
 * - Scroll natural (dirección correcta)
 * - Scroll position 0 = abajo (mensajes recientes)
 * - Límite de mensajes en memoria para rendimiento
 */
export function ChatMessages() {
  const containerRef = useRef<HTMLDivElement>(null);
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

  // Limitar mensajes para rendimiento (mantener los más recientes)
  const displayMessages = currentMessages.length > MAX_MESSAGES_IN_VIEW
    ? currentMessages.slice(-MAX_MESSAGES_IN_VIEW)
    : currentMessages;

  // Cargar mensajes iniciales
  useEffect(() => {
    if (!activeTarget) return;

    const key = getTargetKey(activeTarget);
    if (messages[key]?.length > 0) return;

    const loadMessages = async () => {
      setLoadingMessages(true);
      try {
        const endpoint = activeTarget.type === 'channel'
          ? `${CHAT_API_URL}/api/chat/messages/channel/${activeTarget.id}`
          : `${CHAT_API_URL}/api/chat/messages/group/${activeTarget.id}`;

        const headers: Record<string, string> = {};
        if (activeTarget.type === 'group') {
          const token = await getToken();
          if (token) headers['Authorization'] = `Bearer ${token}`;
        }

        const res = await fetch(endpoint, { headers });
        if (res.ok) {
          const data = await res.json();
          addMessages(key, data);
          setHasMoreMessages(key, data.length >= PAGE_SIZE);
        }
      } catch (error) {
        console.error('[ChatMessages] Failed to load:', error);
      } finally {
        setLoadingMessages(false);
      }
    };

    loadMessages();
  }, [activeTarget, getTargetKey, messages, addMessages, setHasMoreMessages, setLoadingMessages, getToken]);

  // Cargar mensajes antiguos
  const loadOlderMessages = useCallback(async () => {
    if (!activeTarget || isLoadingMore || !hasMore || currentMessages.length === 0) return;

    const key = getTargetKey(activeTarget);
    const oldestId = currentMessages[0]?.id;
    if (!oldestId) return;

    setIsLoadingMore(true);
    try {
      const endpoint = activeTarget.type === 'channel'
        ? `${CHAT_API_URL}/api/chat/messages/channel/${activeTarget.id}?before=${oldestId}`
        : `${CHAT_API_URL}/api/chat/messages/group/${activeTarget.id}?before=${oldestId}`;

      const headers: Record<string, string> = {};
      if (activeTarget.type === 'group') {
        const token = await getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(endpoint, { headers });
      if (res.ok) {
        const data = await res.json();
        if (data.length > 0) {
          addMessages(key, data, true);
        }
        setHasMoreMessages(key, data.length >= PAGE_SIZE);
      }
    } catch (error) {
      console.error('[ChatMessages] Failed to load more:', error);
    } finally {
      setIsLoadingMore(false);
    }
  }, [activeTarget, getTargetKey, currentMessages, isLoadingMore, hasMore, addMessages, setHasMoreMessages, getToken]);

  // Detectar scroll hacia arriba (mensajes antiguos)
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    // En column-reverse: scrollTop es negativo, cerca de 0 = arriba (antiguos)
    const distanceFromTop = scrollHeight + scrollTop - clientHeight;

    if (distanceFromTop < 100 && hasMore && !isLoadingMore) {
      loadOlderMessages();
    }
  }, [hasMore, isLoadingMore, loadOlderMessages]);

  // Scroll a un mensaje específico
  const scrollToMessage = useCallback((messageId: string) => {
    const element = document.getElementById(`msg-${messageId}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, []);

  // Estado: Cargando
  if (isLoadingMessages) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-primary" />
      </div>
    );
  }

  // Estado: Sin mensajes
  if (currentMessages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground text-xs">
        <p>No hay mensajes. ¡Inicia la conversación!</p>
      </div>
    );
  }

  return (
    <div className="flex-1 relative overflow-hidden">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="absolute inset-0 overflow-y-auto flex flex-col-reverse"
      >
        {/* Espacio para typing indicator */}
        <div className="h-5 shrink-0" />

        {/* Mensajes (invertidos para column-reverse) */}
        {[...displayMessages].reverse().map((message) => (
          <div key={message.id} id={`msg-${message.id}`}>
            <ChatMessage
              message={message}
              onScrollToMessage={scrollToMessage}
            />
          </div>
        ))}

        {/* Header: cargar más / inicio */}
        <div className="shrink-0">
          {isLoadingMore ? (
            <div className="flex justify-center py-3">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          ) : hasMore ? (
            <button
              onClick={loadOlderMessages}
              className="w-full py-2 text-[10px] text-muted-foreground hover:text-primary transition-colors"
            >
              Cargar más
            </button>
          ) : (
            <div className="py-3 text-center text-[10px] text-muted-foreground/50">
              Inicio de la conversación
            </div>
          )}
        </div>
      </div>

      {/* Indicador de escritura */}
      <AnimatePresence>
        {typingUsers.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 5 }}
            className="absolute bottom-1 left-2 text-[10px] text-muted-foreground/70 italic"
          >
            {typingUsers.length === 1
              ? `${typingUsers[0].user_name} está escribiendo...`
              : `${typingUsers.length} personas escribiendo...`}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
