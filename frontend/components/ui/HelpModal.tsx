'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
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
        className="bg-surface border border-border shadow-xl w-[520px] max-h-[70vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface-hover">
          <span className="text-xs font-mono text-foreground/80 uppercase tracking-wide">{t('help.title')}</span>
          <button
            onClick={onClose}
            className="p-0.5 rounded hover:bg-surface-inset text-muted-fg hover:text-foreground transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border bg-surface-hover">
          <TabButton active={tab === 'start'} onClick={() => setTab('start')}>
            {t('help.tabs.gettingStarted')}
          </TabButton>
          <TabButton active={tab === 'keys'} onClick={() => setTab('keys')}>
            {t('help.tabs.keystrokes')}
          </TabButton>
          <TabButton active={tab === 'cmds'} onClick={() => setTab('cmds')}>
            {t('help.tabs.commands')}
          </TabButton>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-3 text-foreground text-[11px]">
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
          ? 'text-primary border-b-2 border-primary -mb-[1px]'
          : 'text-muted-fg hover:text-foreground'
        }`}
    >
      {children}
    </button>
  );
}

function GettingStartedTab() {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-[11px] font-semibold text-foreground mb-1">{t('help.terminal')}</h3>
        <p className="text-[10px] text-muted-fg leading-relaxed">
          {t('help.terminalDescription')} <Kbd>Ctrl+K</Kbd>. {t('help.useCommands')}
        </p>
      </div>

      <div>
        <h3 className="text-[11px] font-semibold text-foreground mb-1">{t('help.syntax')}</h3>
        <div className="bg-surface-hover border border-border rounded px-2 py-1.5 font-mono text-[10px]">
          <div className="flex items-center gap-1.5">
            <span className="text-muted-fg">{'>'}</span>
            <span className="px-1 py-0.5 bg-amber-500/10 text-amber-700 dark:text-amber-400 rounded text-[9px]">TICKER</span>
            <span className="px-1 py-0.5 bg-primary/10 text-primary rounded text-[9px]">COMMAND</span>
          </div>
        </div>
      </div>

      <div>
        <h3 className="text-[11px] font-semibold text-foreground mb-1">{t('help.example')}</h3>
        <p className="text-[10px] text-muted-fg mb-1.5">
          {t('help.toOpenChart')}
        </p>
        <div className="bg-surface-hover border border-border rounded px-2 py-1.5 font-mono text-[10px]">
          <div className="flex items-center gap-1.5">
            <span className="text-muted-fg">{'>'}</span>
            <span className="px-1 py-0.5 bg-surface-inset border border-border text-foreground rounded text-[9px] font-semibold">AAPL</span>
            <span className="px-1 py-0.5 bg-primary/10 border border-primary text-primary rounded text-[9px] font-semibold">G</span>
          </div>
        </div>
        <p className="text-[9px] text-muted-fg mt-1.5">
          {t('help.exampleDescription')}
        </p>
      </div>
    </div>
  );
}

function KeystrokesTab() {
  const { t } = useTranslation();
  const shortcuts = [
    { keys: ['Ctrl', 'K'], description: t('help.shortcuts.openTerminal') },
    { keys: ['Esc'], description: t('help.shortcuts.close') },
    { keys: ['Enter'], description: t('help.shortcuts.executeCommand') },
    { keys: ['Tab'], description: t('help.shortcuts.autocomplete') },
    { keys: ['?'], description: t('help.shortcuts.showHelp') },
    { keys: ['Ctrl', 'D'], description: t('dilution.title') },
    { keys: ['Ctrl', 'F'], description: t('secFilings.title') },
    { keys: ['Ctrl', 'N'], description: t('news.title') },
    { keys: ['Ctrl', ','], description: t('settings.title') },
  ];

  return (
    <div className="space-y-0.5">
      {shortcuts.map((s, i) => (
        <div
          key={i}
          className="flex items-center justify-between py-1 px-1.5 rounded hover:bg-surface-hover"
        >
          <div className="flex items-center gap-0.5">
            {s.keys.map((key, j) => (
              <span key={j} className="flex items-center">
                <Kbd>{key}</Kbd>
                {j < s.keys.length - 1 && <span className="text-muted-fg/50 mx-0.5 text-[9px]">+</span>}
              </span>
            ))}
          </div>
          <span className="text-[10px] text-muted-fg">{s.description}</span>
        </div>
      ))}
    </div>
  );
}

function CommandsTab() {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      {/* Ticker Commands */}
      <div>
        <h4 className="text-[9px] font-semibold text-muted-fg uppercase tracking-wide mb-1.5">
          {t('help.tickerCommands')}
        </h4>
        <div className="space-y-0.5">
          {Object.entries(TICKER_COMMANDS).map(([key, cmd]) => (
            <CommandRow
              key={key}
              label={key}
              description={t(cmd.descriptionKey)}
            />
          ))}
        </div>
      </div>

      {/* Global Commands */}
      <div>
        <h4 className="text-[9px] font-semibold text-muted-fg uppercase tracking-wide mb-1.5">
          {t('help.globalCommands')}
        </h4>
        <div className="space-y-0.5">
          {Object.entries(GLOBAL_COMMANDS).map(([key, cmd]) => (
            <CommandRow
              key={key}
              label={key}
              description={t(cmd.descriptionKey)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function CommandRow({ label, description }: { label: string; description: string }) {
  return (
    <div className="flex items-center gap-2 py-1 px-1.5 rounded hover:bg-surface-hover">
      <span className="px-1.5 py-0.5 bg-primary/10 border border-primary text-primary rounded text-[9px] font-mono font-semibold min-w-[40px] text-center">
        {label}
      </span>
      <span className="text-[10px] text-muted-fg">{description}</span>
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[18px] h-4 px-1 
                    bg-surface-inset border border-border rounded text-[9px] font-mono 
                    text-foreground/80">
      {children}
    </kbd>
  );
}

export default HelpModal;
