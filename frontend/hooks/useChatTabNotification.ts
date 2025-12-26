/**
 * Hook para mostrar notificaciones de chat en la pestaña del navegador
 *
 * Alterna entre "Tradeul" y "(N) mensajes" cuando hay mensajes sin leer
 * y la pestaña no está activa. Efecto similar a Telegram.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '@/stores/useChatStore';
import { useUser } from '@clerk/nextjs';

const ORIGINAL_TITLE = 'Tradeul';
const BLINK_INTERVAL = 1500; // Alternar cada 1.5 segundos

export function useChatTabNotification() {
  const { user } = useUser();
  const unreadCountRef = useRef(0);
  const isTabVisibleRef = useRef(true);
  const blinkIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const showingNotificationRef = useRef(false);

  // Detener el parpadeo
  const stopBlinking = useCallback(() => {
    if (blinkIntervalRef.current) {
      clearInterval(blinkIntervalRef.current);
      blinkIntervalRef.current = null;
    }
    showingNotificationRef.current = false;
    document.title = ORIGINAL_TITLE;
  }, []);

  // Iniciar el parpadeo alternando títulos
  const startBlinking = useCallback((count: number) => {
    // Si ya está parpadeando, solo actualizar el contador
    if (blinkIntervalRef.current) {
      return;
    }

    const notificationTitle = count === 1
      ? '1 mensaje'
      : `${count} mensajes`;

    // Alternar entre título normal y notificación
    blinkIntervalRef.current = setInterval(() => {
      if (showingNotificationRef.current) {
        document.title = ORIGINAL_TITLE;
        showingNotificationRef.current = false;
      } else {
        // Actualizar con el contador actual
        const currentCount = unreadCountRef.current;
        document.title = currentCount === 1
          ? '1 mensaje'
          : `${currentCount} mensajes`;
        showingNotificationRef.current = true;
      }
    }, BLINK_INTERVAL);

    // Mostrar notificación inmediatamente
    document.title = notificationTitle;
    showingNotificationRef.current = true;
  }, []);

  // Resetear todo cuando la pestaña se vuelve visible
  const resetUnread = useCallback(() => {
    unreadCountRef.current = 0;
    stopBlinking();
  }, [stopBlinking]);

  useEffect(() => {
    // Detectar visibilidad de la pestaña
    const handleVisibilityChange = () => {
      isTabVisibleRef.current = !document.hidden;

      if (isTabVisibleRef.current) {
        // Usuario volvió a la pestaña - resetear notificaciones
        resetUnread();
      }
    };

    // Escuchar cambios de visibilidad
    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Suscribirse a nuevos mensajes del chat
    const unsubscribe = useChatStore.subscribe((state, prevState) => {
      // Solo procesar si el chat está activo (hay un target seleccionado)
      if (!state.activeTarget) return;

      const targetKey = state.getTargetKey(state.activeTarget);
      const currentMessages = state.messages[targetKey] || [];
      const prevMessages = prevState.messages[targetKey] || [];

      // Detectar mensajes nuevos
      if (currentMessages.length > prevMessages.length) {
        const newMessages = currentMessages.slice(prevMessages.length);

        // Filtrar mensajes propios
        const newFromOthers = newMessages.filter(
          (msg) => msg.user_id !== user?.id
        );

        if (newFromOthers.length > 0 && !isTabVisibleRef.current) {
          // Incrementar contador e iniciar parpadeo
          unreadCountRef.current += newFromOthers.length;
          startBlinking(unreadCountRef.current);
        }
      }
    });

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      unsubscribe();
      stopBlinking();
    };
  }, [user?.id, startBlinking, stopBlinking, resetUnread]);

  return {
    resetUnread,
  };
}






