'use client';

import { memo, useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export interface SlashCommand {
  id: string;
  label: string;
  description: string;
  category: string;
  template: string;
  hint: string;
}

const COMMANDS: SlashCommand[] = [
  {
    id: 'backtest',
    label: '/backtest',
    description: 'Ejecutar un backtest profesional con lenguaje natural',
    category: 'Analisis',
    template: '/backtest ',
    hint: 'Ej: Buy when RSI < 30 and price > SMA200, sell at 5% profit or 3% stop, 2024-2025',
  },
];

interface SlashCommandMenuProps {
  input: string;
  visible: boolean;
  onSelect: (command: SlashCommand) => void;
  onClose: () => void;
  anchorRef: React.RefObject<HTMLElement | null>;
}

export function useSlashCommands(input: string) {
  const slashActive = useMemo(() => {
    const trimmed = input.trimStart();
    return trimmed.startsWith('/') && !trimmed.includes(' ');
  }, [input]);

  const query = useMemo(() => {
    if (!slashActive) return '';
    return input.trimStart().slice(1).toLowerCase();
  }, [slashActive, input]);

  const filtered = useMemo(() => {
    if (!slashActive) return [];
    if (!query) return COMMANDS;
    return COMMANDS.filter(c =>
      c.id.includes(query) || c.label.includes('/' + query)
    );
  }, [slashActive, query]);

  return { slashActive, filtered };
}

export const SlashCommandMenu = memo(function SlashCommandMenu({
  input,
  visible,
  onSelect,
  onClose,
  anchorRef,
}: SlashCommandMenuProps) {
  const { filtered } = useSlashCommands(input);
  const [activeIndex, setActiveIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setActiveIndex(0);
  }, [filtered.length]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!visible || filtered.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(prev => (prev + 1) % filtered.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(prev => (prev - 1 + filtered.length) % filtered.length);
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      onSelect(filtered[activeIndex]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  }, [visible, filtered, activeIndex, onSelect, onClose]);

  useEffect(() => {
    if (visible) {
      window.addEventListener('keydown', handleKeyDown, true);
      return () => window.removeEventListener('keydown', handleKeyDown, true);
    }
  }, [visible, handleKeyDown]);

  if (!visible || filtered.length === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        ref={menuRef}
        initial={{ opacity: 0, y: 6, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 6, scale: 0.97 }}
        transition={{ duration: 0.15 }}
        className="absolute bottom-full left-0 right-0 mb-1.5 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden z-50"
      >
        <div className="px-2.5 py-1.5 border-b border-slate-100">
          <span className="text-[9px] font-semibold text-slate-400 uppercase tracking-wider">
            Prompt Library
          </span>
        </div>

        <div className="py-1">
          {filtered.map((cmd, idx) => (
            <button
              key={cmd.id}
              onMouseDown={(e) => {
                e.preventDefault();
                onSelect(cmd);
              }}
              onMouseEnter={() => setActiveIndex(idx)}
              className={`w-full text-left px-2.5 py-2 flex items-start gap-2.5 transition-colors ${
                idx === activeIndex ? 'bg-indigo-50/70' : 'hover:bg-slate-50'
              }`}
            >
              <div className="flex-shrink-0 mt-0.5 w-5 h-5 rounded bg-indigo-100 flex items-center justify-center">
                <span className="text-[10px] font-bold text-indigo-600">/</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-semibold text-slate-800">{cmd.label}</span>
                  <span className="text-[9px] text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
                    {cmd.category}
                  </span>
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5 leading-snug">{cmd.description}</p>
                <p className="text-[9px] text-slate-400 mt-0.5 truncate italic">{cmd.hint}</p>
              </div>
              {idx === activeIndex && (
                <span className="flex-shrink-0 mt-1 text-[9px] text-indigo-400 font-mono">
                  Enter
                </span>
              )}
            </button>
          ))}
        </div>
      </motion.div>
    </AnimatePresence>
  );
});
