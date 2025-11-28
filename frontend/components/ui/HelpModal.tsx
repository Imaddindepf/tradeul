'use client';

import { useState, useEffect, useCallback } from 'react';
import { X } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { TICKER_COMMANDS, GLOBAL_COMMANDS } from '@/lib/terminal-parser';

interface HelpModalProps {
  open: boolean;
  onClose: () => void;
}

type TabType = 'start' | 'keys' | 'cmds';

/**
 * HelpModal - Modal de ayuda del terminal
 * Estilo compacto con colores blanco y azul
 */
export function HelpModal({ open, onClose }: HelpModalProps) {
  const [tab, setTab] = useState<TabType>('start');

  // Cerrar con Escape
  useEffect(() => {
    if (!open) return;
    
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  // Cerrar al hacer click en backdrop
  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  }, [onClose]);

  if (!open) return null;

  return (
    <div 
      className="fixed inset-0 bg-black/20 flex items-center justify-center"
      style={{ zIndex: Z_INDEX.MODAL }}
      onClick={handleBackdropClick}
    >
      <div 
        className="bg-white border border-slate-200 shadow-xl w-[520px] max-h-[70vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-200 bg-slate-50">
          <span className="text-xs font-mono text-slate-600 uppercase tracking-wide">Help</span>
          <button
            onClick={onClose}
            className="p-0.5 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-200 bg-slate-50">
          <TabButton active={tab === 'start'} onClick={() => setTab('start')}>
            Getting Started
          </TabButton>
          <TabButton active={tab === 'keys'} onClick={() => setTab('keys')}>
            Keystrokes
          </TabButton>
          <TabButton active={tab === 'cmds'} onClick={() => setTab('cmds')}>
            Commands
          </TabButton>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-3 text-slate-700 text-[11px]">
          {tab === 'start' && <GettingStartedTab />}
          {tab === 'keys' && <KeystrokesTab />}
          {tab === 'cmds' && <CommandsTab />}
        </div>
      </div>
    </div>
  );
}

function TabButton({ 
  active, 
  onClick, 
  children, 
}: { 
  active: boolean; 
  onClick: () => void; 
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide transition-colors
        ${active 
          ? 'text-blue-600 border-b-2 border-blue-600 -mb-[1px]' 
          : 'text-slate-400 hover:text-slate-600'
        }`}
    >
      {children}
    </button>
  );
}

function GettingStartedTab() {
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-[11px] font-semibold text-slate-800 mb-1">Terminal</h3>
        <p className="text-[10px] text-slate-500 leading-relaxed">
          El Terminal es un sistema de comandos CLI. Accede haciendo click en el prompt 
          o presionando <Kbd>Ctrl+K</Kbd>. Usa comandos para acceder a todas las funciones.
        </p>
      </div>

      <div>
        <h3 className="text-[11px] font-semibold text-slate-800 mb-1">Sintaxis</h3>
        <div className="bg-slate-50 border border-slate-200 rounded px-2 py-1.5 font-mono text-[10px]">
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400">{'>'}</span>
            <span className="px-1 py-0.5 bg-amber-50 text-amber-700 rounded text-[9px]">TICKER</span>
            <span className="px-1 py-0.5 bg-blue-50 text-blue-700 rounded text-[9px]">COMMAND</span>
          </div>
        </div>
      </div>

      <div>
        <h3 className="text-[11px] font-semibold text-slate-800 mb-1">Ejemplo</h3>
        <p className="text-[10px] text-slate-500 mb-1.5">
          Para abrir un grafico de Apple:
        </p>
        <div className="bg-slate-50 border border-slate-200 rounded px-2 py-1.5 font-mono text-[10px]">
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400">{'>'}</span>
            <span className="px-1 py-0.5 bg-slate-100 border border-slate-200 text-slate-700 rounded text-[9px] font-semibold">AAPL</span>
            <span className="px-1 py-0.5 bg-blue-50 border border-blue-200 text-blue-700 rounded text-[9px] font-semibold">G</span>
          </div>
        </div>
        <p className="text-[9px] text-slate-400 mt-1.5">
          AAPL es el ticker. G es el comando (Graph).
        </p>
      </div>
    </div>
  );
}

function KeystrokesTab() {
  const shortcuts = [
    { keys: ['Ctrl', 'K'], description: 'Abrir terminal' },
    { keys: ['Esc'], description: 'Cerrar' },
    { keys: ['Enter'], description: 'Ejecutar comando' },
    { keys: ['Tab'], description: 'Autocompletar' },
    { keys: ['?'], description: 'Mostrar ayuda' },
    { keys: ['Ctrl', 'D'], description: 'Dilution Tracker' },
    { keys: ['Ctrl', 'F'], description: 'SEC Filings' },
    { keys: ['Ctrl', 'N'], description: 'News' },
    { keys: ['Ctrl', ','], description: 'Settings' },
  ];

  return (
    <div className="space-y-0.5">
      {shortcuts.map((s, i) => (
        <div 
          key={i} 
          className="flex items-center justify-between py-1 px-1.5 rounded hover:bg-slate-50"
        >
          <div className="flex items-center gap-0.5">
            {s.keys.map((key, j) => (
              <span key={j} className="flex items-center">
                <Kbd>{key}</Kbd>
                {j < s.keys.length - 1 && <span className="text-slate-300 mx-0.5 text-[9px]">+</span>}
              </span>
            ))}
          </div>
          <span className="text-[10px] text-slate-500">{s.description}</span>
        </div>
      ))}
    </div>
  );
}

function CommandsTab() {
  return (
    <div className="space-y-3">
      {/* Comandos con Ticker */}
      <div>
        <h4 className="text-[9px] font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
          Comandos con Ticker
        </h4>
        <div className="space-y-0.5">
          {Object.entries(TICKER_COMMANDS).map(([key, cmd]) => (
            <CommandRow 
              key={key}
              label={key}
              description={cmd.description}
            />
          ))}
        </div>
      </div>

      {/* Comandos Globales */}
      <div>
        <h4 className="text-[9px] font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
          Comandos Globales
        </h4>
        <div className="space-y-0.5">
          {Object.entries(GLOBAL_COMMANDS).map(([key, cmd]) => (
            <CommandRow 
              key={key}
              label={key}
              description={cmd.description}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function CommandRow({ label, description }: { label: string; description: string }) {
  return (
    <div className="flex items-center gap-2 py-1 px-1.5 rounded hover:bg-slate-50">
      <span className="px-1.5 py-0.5 bg-blue-50 border border-blue-200 text-blue-700 rounded text-[9px] font-mono font-semibold min-w-[40px] text-center">
        {label}
      </span>
      <span className="text-[10px] text-slate-500">{description}</span>
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[18px] h-4 px-1 
                    bg-slate-100 border border-slate-200 rounded text-[9px] font-mono 
                    text-slate-600">
      {children}
    </kbd>
  );
}

export default HelpModal;
