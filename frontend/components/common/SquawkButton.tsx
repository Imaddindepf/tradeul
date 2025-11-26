'use client';

import React from 'react';
import { Volume2, VolumeX } from 'lucide-react';

interface SquawkButtonProps {
  isEnabled: boolean;
  isSpeaking: boolean;
  queueSize: number;
  onToggle: () => void;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function SquawkButton({
  isEnabled,
  isSpeaking,
  queueSize,
  onToggle,
  size = 'md',
  className = '',
}: SquawkButtonProps) {
  const iconSize = size === 'sm' ? 'w-3 h-3' : size === 'lg' ? 'w-5 h-5' : 'w-4 h-4';
  const padding = size === 'sm' ? 'px-1.5 py-0.5' : size === 'lg' ? 'px-4 py-2' : 'px-2.5 py-1.5';
  const textSize = size === 'sm' ? 'text-xs' : size === 'lg' ? 'text-base' : 'text-sm';

  const baseClasses = `flex items-center justify-center gap-1 rounded-md font-medium transition-colors relative ${padding} ${textSize}`;
  const stateClasses = isEnabled
    ? 'bg-violet-600 text-white hover:bg-violet-700'
    : 'bg-slate-200 text-slate-600 hover:bg-slate-300';
  const animationClasses = isSpeaking ? 'animate-pulse' : '';

  return (
    <button
      onClick={onToggle}
      className={`${baseClasses} ${stateClasses} ${animationClasses} ${className}`}
      aria-label={isEnabled ? "Desactivar squawk" : "Activar squawk"}
      title={isEnabled ? "Squawk activo - Click para desactivar" : "Click para activar squawk de noticias"}
    >
      {isEnabled ? (
        <Volume2 className={`${iconSize} ${isSpeaking ? 'animate-bounce' : ''}`} />
      ) : (
        <VolumeX className={iconSize} />
      )}
      <span className="hidden sm:inline">Squawk</span>
      
      {/* Badge de cola */}
      {queueSize > 0 && (
        <span className="absolute -top-1 -right-1 bg-amber-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
          {queueSize}
        </span>
      )}
    </button>
  );
}

