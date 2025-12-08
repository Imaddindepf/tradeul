'use client';

/**
 * SquawkContext - Contexto global para el servicio de Squawk (TTS)
 * 
 * Resuelve el problema de multiples instancias del hook useSquawkService.
 * El estado del squawk es compartido entre todos los componentes.
 */

import { createContext, useContext, useRef, useState, useCallback, useMemo, ReactNode } from 'react';
import { useAuth } from '@clerk/nextjs';

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

  // Estado compartido
  const [isEnabled, setIsEnabled] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [queueSize, setQueueSize] = useState(0);

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

  // Toggle habilitado
  const toggleEnabled = useCallback(() => {
    setIsEnabled(prev => {
      if (prev) {
        stop();
      }
      return !prev;
    });
  }, [stop]);

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

