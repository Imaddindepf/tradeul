'use client';

/**
 * Insights Provider
 * 
 * Escucha notificaciones de insights (Morning News, etc.) del WebSocket
 * y abre automaticamente una ventana flotante cuando llega una nueva.
 */

import { useEffect, useRef, ReactNode } from 'react';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { useFloatingWindowActions, useFloatingWindowsList } from '@/contexts/FloatingWindowContext';
import { InsightContent } from './InsightContent';

interface InsightsProviderProps {
    children: ReactNode;
}

interface InsightEvent {
    type: 'morning_news_call' | 'insight_update';
    data: {
        date: string;
        title: string;
        preview: string;
        generated_at: string;
        manual?: boolean;
        insight_type?: string;
    };
    timestamp: string;
}

export function InsightsProvider({ children }: InsightsProviderProps) {
    // Use the shared, authenticated WebSocket from AuthWebSocketProvider.
    // Previously this called useRxWebSocket(WS_BASE_URL) directly which
    // bypassed the central token negotiation and caused the singleton to
    // (re)connect with an un-authenticated URL, triggering 2-3s of
    // "offline" while the backend rejected and the provider re-issued
    // a token via updateToken().
    const ws = useWebSocket();
    const { openWindow } = useFloatingWindowActions();
    const windows = useFloatingWindowsList();
    const hasOpenedTodayRef = useRef<string | null>(null);

    useEffect(() => {
        if (!ws.isConnected) return;

        const subscription = ws.messages$.subscribe((message: any) => {
            // Notificacion de Morning News u otro insight
            if ((message.type === 'morning_news_call' || message.type === 'insight_update') && message.data) {
                const event = message as InsightEvent;
                const eventDate = event.data.date;
                const insightType = event.data.insight_type || 'morning';

                // Evitar abrir multiples veces para el mismo dia
                const cacheKey = `${insightType}-${eventDate}`;
                if (hasOpenedTodayRef.current === cacheKey) {
                    return;
                }

                // Verificar si ya hay una ventana de Insights abierta
                const existingWindow = windows.find(w => 
                    w.title === 'Insights' || 
                    w.title === 'Morning News Call'
                );
                if (existingWindow) {
                    return;
                }

                hasOpenedTodayRef.current = cacheKey;

                const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
                const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

                // Abrir ventana con el insight
                openWindow({
                    title: 'Insights',
                    content: <InsightContent insightType="morning" />,
                    x: Math.max(100, screenWidth / 2 - 350),
                    y: Math.max(50, screenHeight / 2 - 300),
                    width: 700,
                    height: 600,
                    minWidth: 500,
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

