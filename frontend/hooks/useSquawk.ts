'use client';

import { useRef, useState, useCallback } from 'react';

interface SquawkOptions {
    voiceId?: string;
    modelId?: string;
    stability?: number;
    similarityBoost?: number;
}

interface UseSquawkReturn {
    isEnabled: boolean;
    isSpeaking: boolean;
    toggleEnabled: () => void;
    speak: (text: string) => Promise<void>;
    stop: () => void;
    queueSize: number;
}

// Voz Rachel de Eleven Labs (multilingüe, español)
const DEFAULT_VOICE_ID = '21m00Tcm4TlvDq8ikWAM'; // Rachel - Spanish/Multilingual voice

export function useSquawk(options: SquawkOptions = {}): UseSquawkReturn {
    const {
        voiceId = DEFAULT_VOICE_ID,
        modelId = 'eleven_multilingual_v2',
        stability = 0.5,
        similarityBoost = 0.75,
    } = options;

    const [isEnabled, setIsEnabled] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [queueSize, setQueueSize] = useState(0);

    const audioRef = useRef<HTMLAudioElement | null>(null);
    const queueRef = useRef<string[]>([]);
    const isProcessingRef = useRef(false);

    // Procesar la cola de mensajes
    const processQueue = useCallback(async () => {
        if (isProcessingRef.current || queueRef.current.length === 0) return;

        isProcessingRef.current = true;
        setIsSpeaking(true);

        while (queueRef.current.length > 0) {
            const text = queueRef.current.shift()!;
            setQueueSize(queueRef.current.length);

            try {
                // Usar proxy del API Gateway para evitar CORS
                const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                const response = await fetch(`${apiUrl}/api/v1/tts/speak`, {
                    method: 'POST',
                    credentials: 'include', // Enviar cookies de autenticación
                    headers: {
                        'Accept': 'audio/mpeg',
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        text,
                        voice_id: voiceId,
                    }),
                });

                if (!response.ok) {
                    console.error('Eleven Labs error:', response.status);
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
                console.error('Squawk error:', error);
            }
        }

        isProcessingRef.current = false;
        setIsSpeaking(false);
        setQueueSize(0);
    }, [voiceId, modelId, stability, similarityBoost]);

    // Agregar texto a la cola
    const speak = useCallback(async (text: string) => {
        if (!isEnabled) return;

        // Limpiar y acortar el texto para squawk
        const cleanText = text
            .replace(/<[^>]*>/g, '') // Quitar HTML
            .replace(/&[^;]+;/g, '') // Quitar entidades HTML
            .substring(0, 200); // Máximo 200 caracteres

        queueRef.current.push(cleanText);
        setQueueSize(queueRef.current.length);

        processQueue();
    }, [isEnabled, processQueue]);

    // Detener reproducción
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
                stop(); // Si se desactiva, detener todo
            }
            return !prev;
        });
    }, [stop]);

    return {
        isEnabled,
        isSpeaking,
        toggleEnabled,
        speak,
        stop,
        queueSize,
    };
}

