'use client';

import { Pin, Settings } from 'lucide-react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { usePinnedCommands } from '@/hooks/usePinnedCommands';
import { SettingsContent } from '@/components/settings/SettingsContent';

interface PinnedCommandsProps {
  onCommandClick?: (commandId: string) => void;
}

// Mapeo de IDs a labels (solo comandos principales)
const COMMAND_LABELS: Record<string, string> = {
  'sc': 'SC',
  'dt': 'DT',
  'settings': 'SET',
};

export function PinnedCommands({ onCommandClick }: PinnedCommandsProps) {
  const { openWindow } = useFloatingWindow();
  const { pinnedCommands, loaded } = usePinnedCommands();

  const handleOpenSettings = () => {
    const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;
    
    openWindow({
      title: 'Settings',
      content: <SettingsContent />,
      width: 900,
      height: 750,
      x: screenWidth / 2 - 450,
      y: screenHeight / 2 - 375,
      minWidth: 700,
      minHeight: 600,
    });
  };

  if (!loaded) {
    return null; // Evitar flash mientras carga
  }

  return (
    <div className="flex items-center gap-2">
      {/* Pin Icon Button - Abre Settings */}
      <button
        onClick={handleOpenSettings}
        className="p-2 rounded-lg hover:bg-blue-50 transition-colors group"
        title="Configurar favoritos"
      >
        <Pin className="w-5 h-5 text-blue-500 group-hover:text-blue-600 transition-colors" />
      </button>

      {/* Pinned Commands (Favoritos configurados por el usuario) */}
      {pinnedCommands.length > 0 ? (
        <div className="flex items-center gap-1.5">
          {pinnedCommands.slice(0, 6).map((cmdId) => (
            <button
              key={cmdId}
              onClick={() => onCommandClick?.(cmdId)}
              className="px-3 py-1.5 text-xs font-semibold bg-blue-500 text-white 
                       rounded-md hover:bg-blue-600 transition-colors
                       shadow-sm hover:shadow-md"
              title={`Abrir/cerrar ${COMMAND_LABELS[cmdId] || cmdId}`}
            >
              {COMMAND_LABELS[cmdId] || cmdId}
            </button>
          ))}
          
          {pinnedCommands.length > 6 && (
            <span className="px-2 py-1 text-xs font-semibold text-slate-500 bg-slate-100 rounded-md">
              +{pinnedCommands.length - 6}
            </span>
          )}
        </div>
      ) : (
        <span className="text-xs text-slate-400 italic">Sin favoritos</span>
      )}
    </div>
  );
}

