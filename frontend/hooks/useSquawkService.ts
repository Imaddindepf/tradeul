'use client';

/**
 * useSquawkService - Versión memoizada del hook de Squawk
 * 
 * El objeto retornado es ESTABLE (mismo referencia entre renders)
 * para evitar re-suscripciones innecesarias en useEffects.
 * 
 * Usa:
 * - useMemo para el objeto de retorno
 * - useRef para valores que no necesitan trigger re-render
 */

import { useRef, useState, useCallback, useMemo } from 'react';
import { useAuth } from '@clerk/nextjs';

interface SquawkServiceOptions {
    voiceId?: string;
}

export interface SquawkService {
    isEnabled: boolean;
    isSpeaking: boolean;
    toggleEnabled: () => void;
    speak: (text: string) => void;
    stop: () => void;
    queueSize: number;
}

// Voz Rachel de Eleven Labs (multilingüe, español)
const DEFAULT_VOICE_ID = '21m00Tcm4TlvDq8ikWAM';

export function useSquawkService(options: SquawkServiceOptions = {}): SquawkService {
    const { voiceId = DEFAULT_VOICE_ID } = options;
    const { getToken } = useAuth();

    // Estado con useState (triggers re-render cuando cambia)
    const [isEnabled, setIsEnabled] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [queueSize, setQueueSize] = useState(0);

    // Refs para datos que NO necesitan trigger re-render
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

    // Stop - detener reproducción
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

    // Speak - agregar texto a la cola
    // NOTA: Usa useRef para isEnabled para evitar dependencia
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

    // ================================================================
    // RETORNO MEMOIZADO - Solo cambia cuando cambian los valores
    // ================================================================
    return useMemo(() => ({
        isEnabled,
        isSpeaking,
        toggleEnabled,
        speak,
        stop,
        queueSize,
    }), [isEnabled, isSpeaking, toggleEnabled, speak, stop, queueSize]);
}

export default useSquawkService;

