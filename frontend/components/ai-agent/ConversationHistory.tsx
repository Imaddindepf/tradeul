'use client';

import { memo, useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { X, Trash2, Search, MessageSquare } from 'lucide-react';
import type { SessionSummary } from './types';

interface ConversationHistoryProps {
  sessions: SessionSummary[];
  isLoading: boolean;
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onClose: () => void;
}

// ── Time grouping helpers ──

function getTimeGroup(ts: number): string {
  const now = Date.now() / 1000;
  const diff = now - ts;
  const dayStart = new Date();
  dayStart.setHours(0, 0, 0, 0);
  const dayStartTs = dayStart.getTime() / 1000;

  if (ts >= dayStartTs) return 'Hoy';
  if (ts >= dayStartTs - 86400) return 'Ayer';
  if (diff < 7 * 86400) return 'Esta semana';
  return 'Anteriores';
}

function relativeTime(ts: number): string {
  const now = Date.now() / 1000;
  const diff = now - ts;

  if (diff < 60) return 'ahora';
  if (diff < 3600) return `hace ${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)}h`;
  if (diff < 172800) return 'ayer';
  if (diff < 604800) return `hace ${Math.floor(diff / 86400)}d`;
  return new Date(ts * 1000).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' });
}

// ── Session Entry ──

const SessionEntry = memo(function SessionEntry({
  session,
  isActive,
  onSelect,
  onDelete,
}: {
  session: SessionSummary;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirmDelete) {
      onDelete();
    } else {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 2000);
    }
  }, [confirmDelete, onDelete]);

  return (
    <button
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setConfirmDelete(false); }}
      className={`
        w-full text-left px-2.5 py-2 rounded-lg transition-all duration-150 group relative
        ${isActive
          ? 'bg-indigo-50 border border-indigo-200/60'
          : 'hover:bg-slate-50 border border-transparent'
        }
      `}
    >
      <div className="flex items-start gap-2 min-w-0">
        <MessageSquare className={`w-3.5 h-3.5 flex-shrink-0 mt-0.5 ${isActive ? 'text-indigo-500' : 'text-slate-300'}`} />
        <div className="flex-1 min-w-0">
          <p className={`text-[11px] leading-snug truncate ${isActive ? 'text-indigo-700 font-medium' : 'text-slate-700'}`}>
            {session.last_query || 'Sin título'}
          </p>
          <span className="text-[9px] text-slate-400 mt-0.5 block">
            {relativeTime(session.updated_at)}
          </span>
        </div>
        {hovered && (
          <button
            onClick={handleDelete}
            className={`flex-shrink-0 p-0.5 rounded transition-colors ${
              confirmDelete
                ? 'text-red-500 hover:text-red-600'
                : 'text-slate-300 hover:text-slate-500'
            }`}
            title={confirmDelete ? 'Confirmar eliminación' : 'Eliminar'}
          >
            <Trash2 className="w-3 h-3" />
          </button>
        )}
      </div>
    </button>
  );
});

// ── Main Sidebar ──

export const ConversationHistory = memo(function ConversationHistory({
  sessions,
  isLoading,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
  onClose,
}: ConversationHistoryProps) {
  const [search, setSearch] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = setTimeout(() => searchRef.current?.focus(), 200);
    return () => clearTimeout(t);
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return sessions;
    const q = search.toLowerCase();
    return sessions.filter(s => s.last_query?.toLowerCase().includes(q));
  }, [sessions, search]);

  const grouped = useMemo(() => {
    const groups: Record<string, SessionSummary[]> = {};
    const order = ['Hoy', 'Ayer', 'Esta semana', 'Anteriores'];

    for (const s of filtered) {
      const g = getTimeGroup(s.updated_at);
      if (!groups[g]) groups[g] = [];
      groups[g].push(s);
    }

    return order
      .filter(g => groups[g]?.length)
      .map(g => ({ label: g, sessions: groups[g] }));
  }, [filtered]);

  return (
    <motion.div
      initial={{ x: -280, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -280, opacity: 0 }}
      transition={{ type: 'spring', damping: 28, stiffness: 300 }}
      className="absolute left-0 top-0 bottom-0 w-[280px] bg-white border-r border-slate-200/80 z-20 flex flex-col shadow-lg"
    >
      {/* Header */}
      <div className="flex-shrink-0 px-3 py-2.5 border-b border-slate-100 flex items-center justify-between">
        <span className="text-[12px] font-semibold text-slate-700">Historial</span>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-600 transition-colors p-0.5"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Search */}
      <div className="flex-shrink-0 px-2.5 py-2 border-b border-slate-50">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-300" />
          <input
            ref={searchRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar..."
            className="w-full pl-7 pr-2 py-1.5 text-[11px] bg-slate-50 border border-slate-100 rounded-lg text-slate-700 placeholder-slate-400 focus:outline-none focus:border-slate-200 transition-colors"
          />
        </div>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto px-2 py-1.5">
        {isLoading && sessions.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <div className="flex items-center gap-2 text-[10px] text-slate-400">
              <motion.div
                className="w-3 h-3 border-2 border-slate-300 border-t-transparent rounded-full"
                animate={{ rotate: 360 }}
                transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
              />
              <span>Cargando...</span>
            </div>
          </div>
        ) : grouped.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <MessageSquare className="w-6 h-6 text-slate-200 mb-2" />
            <p className="text-[10px] text-slate-400">
              {search ? 'Sin resultados' : 'No hay conversaciones'}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {grouped.map(group => (
              <div key={group.label}>
                <div className="px-2 py-1">
                  <span className="text-[9px] font-medium text-slate-400 uppercase tracking-wider">
                    {group.label}
                  </span>
                </div>
                <div className="space-y-0.5">
                  {group.sessions.map(session => (
                    <SessionEntry
                      key={session.thread_id}
                      session={session}
                      isActive={session.thread_id === activeSessionId}
                      onSelect={() => onSelectSession(session.thread_id)}
                      onDelete={() => onDeleteSession(session.thread_id)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
});
