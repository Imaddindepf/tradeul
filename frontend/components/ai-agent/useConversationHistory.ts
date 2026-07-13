'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { useAuth } from '@clerk/nextjs';
import { authFetchStandalone } from '@/hooks/useAuthFetch';
import type { SessionSummary, SessionMessage } from './types';

const AGENT_BASE = process.env.NEXT_PUBLIC_AI_AGENT_V4_API_URL || 'https://agent.tradeul.com/v4';

export function useConversationHistory() {
  const { getToken } = useAuth();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const fetchSessions = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setIsLoading(true);
    try {
      const res = await authFetchStandalone(`${AGENT_BASE}/api/sessions?limit=30`, getToken, {
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        console.error('Failed to fetch sessions:', e);
      }
    } finally {
      setIsLoading(false);
    }
  }, [getToken]);

  const loadSessionMessages = useCallback(async (sessionId: string): Promise<SessionMessage[]> => {
    try {
      const res = await authFetchStandalone(`${AGENT_BASE}/api/sessions/${encodeURIComponent(sessionId)}/messages?limit=100`, getToken);
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      return data.messages || [];
    } catch (e) {
      console.error('Failed to load session messages:', e);
      return [];
    }
  }, [getToken]);

  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      const res = await authFetchStandalone(`${AGENT_BASE}/api/sessions/${encodeURIComponent(sessionId)}`, getToken, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setSessions(prev => prev.filter(s => s.thread_id !== sessionId));
    } catch (e) {
      console.error('Failed to delete session:', e);
    }
  }, [getToken]);

  const toggle = useCallback(() => setIsOpen(p => !p), []);
  const close = useCallback(() => setIsOpen(false), []);

  // Fetch sessions when sidebar opens
  useEffect(() => {
    if (isOpen) fetchSessions();
  }, [isOpen, fetchSessions]);

  // Cleanup abort controller
  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  return {
    sessions,
    isOpen,
    isLoading,
    toggle,
    close,
    fetchSessions,
    loadSessionMessages,
    deleteSession,
  };
}
