'use client';

import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@clerk/nextjs';
import { useChatStore, selectTypingUsers, type ChatMessage as ChatMessageType } from '@/stores/useChatStore';
import { ChatMessage } from './ChatMessage';
import { motion, AnimatePresence } from 'framer-motion';
import { getUserTimezone } from '@/lib/date-utils';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';
const PAGE_SIZE = 50;
const MAX_MESSAGES_IN_VIEW = 500; // Límite para rendimiento

/**
 * Genera una clave de fecha para agrupar mensajes por día
 */
function getDateKey(dateStr: string, timezone: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-CA', { timeZone: timezone }); // YYYY-MM-DD format
}

/**
 * Formatea la etiqueta del separador de fecha
 */
function formatDateSeparator(dateKey: string, timezone: string): string {
  const today = new Date();
  const todayKey = today.toLocaleDateString('en-CA', { timeZone: timezone });
  
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayKey = yesterday.toLocaleDateString('en-CA', { timeZone: timezone });

  if (dateKey === todayKey) {
    return 'Hoy';
  } else if (dateKey === yesterdayKey) {
    return 'Ayer';
  } else {
    // Formatear como "Lun, 30 de diciembre"
    const date = new Date(dateKey + 'T12:00:00'); // Add time to avoid timezone issues
    return date.toLocaleDateString('es-ES', {
      timeZone: timezone,
      weekday: 'short',
      day: 'numeric',
      month: 'long',
    });
  }
}

/**
 * Componente separador de fecha estilo WhatsApp
 */
function DateSeparator({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center py-2">
      <div className="px-3 py-1 rounded-full bg-muted/50 text-[10px] font-medium text-muted-foreground/70 shadow-sm">
        {label}
      </div>
    </div>
  );
}

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
    // Ya se cargaron o intentaron cargar mensajes (array existe, aunque esté vacío)
    if (messages[key] !== undefined) return;

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

  // Timezone del usuario para agrupar por fecha (debe estar antes de useMemo)
  const timezone = getUserTimezone();

  // Agrupar mensajes por fecha con separadores (DEBE estar antes de cualquier return condicional)
  const messagesWithSeparators = useMemo(() => {
    if (displayMessages.length === 0) return [];

    const result: { type: 'message' | 'separator'; message?: ChatMessageType; dateLabel?: string; dateKey?: string }[] = [];
    let lastDateKey: string | null = null;

    // Recorremos en orden cronológico (antiguos a recientes)
    for (const message of displayMessages) {
      const dateKey = getDateKey(message.created_at, timezone);
      
      // Si cambió el día, añadimos un separador
      if (dateKey !== lastDateKey) {
        result.push({
          type: 'separator',
          dateLabel: formatDateSeparator(dateKey, timezone),
          dateKey,
        });
        lastDateKey = dateKey;
      }
      
      result.push({ type: 'message', message });
    }

    return result;
  }, [displayMessages, timezone]);

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

        {/* Mensajes con separadores de fecha (invertidos para column-reverse) */}
        {[...messagesWithSeparators].reverse().map((item, index) => {
          if (item.type === 'separator') {
            return (
              <DateSeparator key={`sep-${item.dateKey}`} label={item.dateLabel!} />
            );
          }
          return (
            <div key={item.message!.id} id={`msg-${item.message!.id}`}>
              <ChatMessage
                message={item.message!}
                onScrollToMessage={scrollToMessage}
              />
            </div>
          );
        })}

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
