'use client';

/**
 * Morning News Provider
 * 
 * Escucha notificaciones de Morning News Call del WebSocket
 * y abre automáticamente una ventana flotante cuando llega una nueva.
 * 
 * La suscripcion es automatica - todos los usuarios conectados reciben
 * la notificacion a las 7:30 AM ET cada dia de trading.
 */

import { useEffect, useRef, ReactNode } from 'react';
import { useRxWebSocket } from '@/hooks/useRxWebSocket';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { MorningNewsContent } from './MorningNewsContent';

interface MorningNewsProviderProps {
    children: ReactNode;
}

interface MorningNewsEvent {
    type: 'morning_news_call';
    data: {
        date: string;
        title: string;
        preview: string;
        generated_at: string;
        manual?: boolean;
    };
    timestamp: string;
}

export function MorningNewsProvider({ children }: MorningNewsProviderProps) {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
    const ws = useRxWebSocket(wsUrl);
    const { openWindow, windows } = useFloatingWindow();
    const hasOpenedTodayRef = useRef<string | null>(null);

    useEffect(() => {
        if (!ws.isConnected) return;

        // Suscribirse a todos los mensajes del WebSocket
        const subscription = ws.messages$.subscribe((message: any) => {
            // Verificar si es una notificacion de Morning News
            if (message.type === 'morning_news_call' && message.data) {
                const event = message as MorningNewsEvent;
                const newsDate = event.data.date;

                // Evitar abrir multiples veces para el mismo dia
                if (hasOpenedTodayRef.current === newsDate) {
                    return;
                }

                // Verificar si ya hay una ventana de Morning News abierta
                const existingWindow = windows.find(w => w.title === 'Morning News Call');
                if (existingWindow) {
                    return;
                }

                hasOpenedTodayRef.current = newsDate;

                // Calcular posicion centrada
                const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
                const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

                // Abrir ventana flotante con el Morning News
                openWindow({
                    title: 'Morning News Call',
                    content: <MorningNewsContent />,
                    x: Math.max(100, screenWidth / 2 - 400),
                    y: Math.max(50, screenHeight / 2 - 350),
                    width: 800,
                    height: 700,
                    minWidth: 600,
                    minHeight: 400,
                });
            }
        });

        return () => {
            subscription.unsubscribe();
        };
    }, [ws.isConnected, ws.messages$, openWindow, windows]);

    return <>{children}</>;
}

