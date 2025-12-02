'use client';

import { useTranslation } from 'react-i18next';
import { Pin } from 'lucide-react';
import { usePinnedCommands } from '@/hooks/usePinnedCommands';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { getCommandLabel } from '@/lib/commands';

interface PinnedCommandsProps {
  /** Callback para abrir CommandPalette con un valor inicial (para SC) */
  onOpenCommandPalette?: (initialValue: string) => void;
}

export function PinnedCommands({ onOpenCommandPalette }: PinnedCommandsProps) {
  const { t } = useTranslation();
  const { pinnedCommands, loaded } = usePinnedCommands();
  const { executeCommand } = useCommandExecutor();

  const handleClick = (cmdId: string) => {
    // SC es especial - abre el CommandPalette con "SC " pre-llenado
    if (cmdId === 'sc') {
      onOpenCommandPalette?.('SC ');
      return;
    }
    
    // Los demás comandos se ejecutan directamente
    executeCommand(cmdId);
  };

  if (!loaded) {
    return null;
  }

  return (
    <div className="flex items-center gap-2">
      {/* Pin Icon - Abre Settings */}
      <button
        onClick={() => executeCommand('settings')}
        className="p-2 rounded-lg hover:bg-blue-50 transition-colors group"
        title={t('settings.title')}
      >
        <Pin className="w-5 h-5 text-blue-500 group-hover:text-blue-600 transition-colors" />
      </button>

      {/* Pinned Commands */}
      {pinnedCommands.length > 0 ? (
        <div className="flex items-center gap-1.5">
          {pinnedCommands.slice(0, 6).map((cmdId) => (
            <button
              key={cmdId}
              onClick={() => handleClick(cmdId)}
              className="px-3 py-1.5 text-xs font-semibold bg-blue-500 text-white 
                       rounded-md hover:bg-blue-600 transition-colors
                       shadow-sm hover:shadow-md"
              title={getCommandLabel(cmdId)}
            >
              {getCommandLabel(cmdId)}
            </button>
          ))}
          
          {pinnedCommands.length > 6 && (
            <span className="px-2 py-1 text-xs font-semibold text-slate-500 bg-slate-100 rounded-md">
              +{pinnedCommands.length - 6}
            </span>
          )}
        </div>
      ) : (
        <span className="text-xs text-slate-400 italic">{t('pinnedCommands.noFavorites')}</span>
      )}
    </div>
  );
}
