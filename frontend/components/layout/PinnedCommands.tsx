'use client';

import { useTranslation } from 'react-i18next';
import { usePinnedCommands } from '@/hooks/usePinnedCommands';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { getCommandLabel } from '@/lib/commands';

interface PinnedCommandsProps {
  /** Callback para abrir CommandPalette con un valor inicial (para SC) */
  onOpenCommandPalette?: (initialValue: string) => void;
}

/** Inline pin SVG — tilted 45° for a professional look */
function PinIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{ transform: 'rotate(45deg)' }}
    >
      <path d="M9.5 2.5L13.5 6.5L11 9L11.5 13L8 9.5L4.5 13L5 9L2.5 6.5L6.5 2.5L9.5 2.5Z" />
      <line x1="4.5" y1="13" x2="2" y2="15.5" />
    </svg>
  );
}

export function PinnedCommands({ onOpenCommandPalette }: PinnedCommandsProps) {
  const { t } = useTranslation();
  const { pinnedCommands, loaded } = usePinnedCommands();
  const { executeCommand } = useCommandExecutor();

  const handleClick = (cmdId: string) => {
    if (cmdId === 'sc') {
      onOpenCommandPalette?.('SC ');
      return;
    }
    if (cmdId === 'evn') {
      onOpenCommandPalette?.('EVN ');
      return;
    }
    executeCommand(cmdId);
  };

  if (!loaded) {
    return null;
  }

  return (
    <div className="flex items-center gap-1">
      {/* Pinned Commands */}
      {pinnedCommands.length > 0 ? (
        <div className="flex items-center gap-0.5">
          {pinnedCommands.slice(0, 6).map((cmdId) => (
            <button
              key={cmdId}
              onClick={() => handleClick(cmdId)}
              className="px-2 py-0.5 text-[10px] font-medium tracking-wide text-blue-600
                       bg-blue-50 hover:bg-blue-100 hover:text-blue-700
                       rounded-sm transition-colors"
              title={getCommandLabel(cmdId)}
            >
              {getCommandLabel(cmdId)}
            </button>
          ))}

          {pinnedCommands.length > 6 && (
            <span className="px-1.5 py-0.5 text-[10px] font-medium text-slate-400">
              +{pinnedCommands.length - 6}
            </span>
          )}
        </div>
      ) : (
        <span className="text-[10px] text-slate-400 italic">{t('pinnedCommands.noFavorites')}</span>
      )}

      {/* Pin Icon — right side, opens Settings */}
      <button
        onClick={() => executeCommand('settings')}
        className="p-1 rounded-sm hover:bg-slate-100 transition-colors group ml-0.5"
        title={t('settings.title')}
      >
        <PinIcon className="w-3 h-3 text-slate-400 group-hover:text-blue-500 transition-colors" />
      </button>
    </div>
  );
}
