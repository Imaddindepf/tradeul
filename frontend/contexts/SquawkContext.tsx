'use client';

/**
 * SquawkContext - Contexto global para el servicio de Squawk (TTS)
 * 
 * Sincroniza con useUserPreferencesStore para persistir el estado.
 * El estado del squawk es compartido entre todos los componentes.
 */

import { createContext, useContext, useRef, useState, useCallback, useMemo, useEffect, ReactNode } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';

interface SquawkService {
  isEnabled: boolean;
  isSpeaking: boolean;
  toggleEnabled: () => void;
  speak: (text: string) => void;
  stop: () => void;
  queueSize: number;
}

const SquawkContext = createContext<SquawkService | null>(null);

// Voz Rachel de Eleven Labs (multilingue)
const DEFAULT_VOICE_ID = '21m00Tcm4TlvDq8ikWAM';

interface SquawkProviderProps {
  children: ReactNode;
  voiceId?: string;
}

export function SquawkProvider({ children, voiceId = DEFAULT_VOICE_ID }: SquawkProviderProps) {
  const { getToken } = useAuth();
  
  // Sincronizar con store de preferencias
  const newsSquawkEnabled = useUserPreferencesStore((s) => s.theme?.newsSquawkEnabled ?? false);
  const setNewsSquawkEnabled = useUserPreferencesStore((s) => s.setNewsSquawkEnabled);

  // Estado local (sincronizado con store)
  const [isEnabled, setIsEnabled] = useState(newsSquawkEnabled);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [queueSize, setQueueSize] = useState(0);

  // Sincronizar estado local con store al montar
  useEffect(() => {
    setIsEnabled(newsSquawkEnabled);
  }, [newsSquawkEnabled]);

  // Refs
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const queueRef = useRef<string[]>([]);
  const isProcessingRef = useRef(false);
  const voiceIdRef = useRef(voiceId);
  voiceIdRef.current = voiceId;

  // Procesar la cola de mensajes
  const processQueue = useCallback(async () => {
    if (isProcessingRef.current || queueRef.current.length === 0) return;

    isProcessingRef.current = true;
    setIsSpeaking(true);

    while (queueRef.current.length > 0) {
      const text = queueRef.current.shift()!;
      setQueueSize(queueRef.current.length);

      try {
        const token = await getToken();
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        
        const response = await fetch(`${apiUrl}/api/v1/tts/speak`, {
          method: 'POST',
          headers: {
            'Accept': 'audio/mpeg',
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            text,
            voice_id: voiceIdRef.current,
          }),
        });

        if (!response.ok) {
          console.error('[Squawk] TTS error:', response.status);
          continue;
        }

        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);

        await new Promise<void>((resolve) => {
          const audio = new Audio(audioUrl);
          audioRef.current = audio;

          audio.onended = () => {
            URL.revokeObjectURL(audioUrl);
            resolve();
          };

          audio.onerror = () => {
            URL.revokeObjectURL(audioUrl);
            resolve();
          };

          audio.play().catch(() => resolve());
        });

      } catch (error) {
        console.error('[Squawk] Error:', error);
      }
    }

    isProcessingRef.current = false;
    setIsSpeaking(false);
    setQueueSize(0);
  }, [getToken]);

  // Stop
  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    queueRef.current = [];
    setQueueSize(0);
    setIsSpeaking(false);
    isProcessingRef.current = false;
  }, []);

  // Toggle habilitado (sincroniza con store para persistir)
  const toggleEnabled = useCallback(() => {
    const newValue = !isEnabled;
    setIsEnabled(newValue);
    setNewsSquawkEnabled(newValue); // Persiste en store -> BD
    
    if (!newValue) {
      stop();
    }
  }, [isEnabled, setNewsSquawkEnabled, stop]);

  // Speak - ref para isEnabled
  const isEnabledRef = useRef(isEnabled);
  isEnabledRef.current = isEnabled;
  
  const speak = useCallback((text: string) => {
    if (!isEnabledRef.current) return;

    const cleanText = text
      .replace(/<[^>]*>/g, '')
      .replace(/&[^;]+;/g, '')
      .substring(0, 200);

    queueRef.current.push(cleanText);
    setQueueSize(queueRef.current.length);
    processQueue();
  }, [processQueue]);

  // Valor memoizado
  const value = useMemo(() => ({
    isEnabled,
    isSpeaking,
    toggleEnabled,
    speak,
    stop,
    queueSize,
  }), [isEnabled, isSpeaking, toggleEnabled, speak, stop, queueSize]);

  return (
    <SquawkContext.Provider value={value}>
      {children}
    </SquawkContext.Provider>
  );
}

// Hook para usar el squawk
export function useSquawk(): SquawkService {
  const context = useContext(SquawkContext);
  if (!context) {
    throw new Error('useSquawk must be used within a SquawkProvider');
  }
  return context;
}

export default SquawkContext;
