'use client';

import { usePinnedCommands } from '@/hooks/usePinnedCommands';
import { Pin } from 'lucide-react';

// Solo comandos principales pueden ser pinneados
const AVAILABLE_COMMANDS = [
  { id: 'sc', label: 'SC - Scanner' },
  { id: 'dt', label: 'DT - Dilution Tracker' },
  { id: 'settings', label: 'SET - Settings' },
];

export function SettingsContent() {
  const { togglePin, isPinned } = usePinnedCommands();

  return (
    <div className="flex flex-col h-full p-6">
      <h3 className="text-base font-semibold text-slate-900 mb-4">Comandos Favoritos</h3>

      <div className="space-y-1">
        {AVAILABLE_COMMANDS.map((cmd) => {
          const pinned = isPinned(cmd.id);
          
          return (
            <button
              key={cmd.id}
              onClick={() => togglePin(cmd.id)}
              className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors text-left group"
            >
              <Pin 
                className={`w-4 h-4 flex-shrink-0 transition-colors ${
                  pinned 
                    ? 'text-blue-600 fill-blue-600' 
                    : 'text-slate-300 group-hover:text-slate-400'
                }`} 
              />
              <span className="text-sm text-slate-700">{cmd.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

