/**
 * Hook para gestionar comandos favoritos (pinned)
 * Persiste en localStorage
 */

'use client';

import { useState, useEffect, useRef } from 'react';

const STORAGE_KEY = 'tradeul-pinned-commands';
const DEFAULT_PINNED = ['sc', 'dt']; // Favoritos por defecto: comandos principales

export function usePinnedCommands() {
  const [pinnedCommands, setPinnedCommands] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const isUpdatingRef = useRef(false);

  // Cargar favoritos del localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setPinnedCommands(JSON.parse(stored));
      } else {
        setPinnedCommands(DEFAULT_PINNED);
      }
    } catch (error) {
      console.error('Error loading pinned commands:', error);
      setPinnedCommands(DEFAULT_PINNED);
    } finally {
      setLoaded(true);
    }
  }, []);

  // Guardar en localStorage cuando cambian
  useEffect(() => {
    if (loaded && !isUpdatingRef.current) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(pinnedCommands));
        // Emitir evento para sincronizar otros componentes
        window.dispatchEvent(new CustomEvent('pinnedCommandsChanged', { 
          detail: pinnedCommands 
        }));
      } catch (error) {
        console.error('Error saving pinned commands:', error);
      }
    }
  }, [pinnedCommands, loaded]);

  // Escuchar cambios de otros componentes
  useEffect(() => {
    const handleStorageChange = (e: Event) => {
      const customEvent = e as CustomEvent<string[]>;
      if (customEvent.detail) {
        isUpdatingRef.current = true;
        setPinnedCommands(customEvent.detail);
        setTimeout(() => {
          isUpdatingRef.current = false;
        }, 0);
      }
    };
    
    window.addEventListener('pinnedCommandsChanged', handleStorageChange);
    return () => window.removeEventListener('pinnedCommandsChanged', handleStorageChange);
  }, []);

  const togglePin = (commandId: string) => {
    setPinnedCommands((prev) => {
      if (prev.includes(commandId)) {
        return prev.filter((id) => id !== commandId);
      } else {
        return [...prev, commandId];
      }
    });
  };

  const isPinned = (commandId: string) => {
    return pinnedCommands.includes(commandId);
  };

  const reorderPinned = (fromIndex: number, toIndex: number) => {
    setPinnedCommands((prev) => {
      const newOrder = [...prev];
      const [removed] = newOrder.splice(fromIndex, 1);
      newOrder.splice(toIndex, 0, removed);
      return newOrder;
    });
  };

  return {
    pinnedCommands,
    togglePin,
    isPinned,
    reorderPinned,
    loaded,
  };
}

