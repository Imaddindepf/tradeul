'use client';

import { useState, useCallback } from 'react';
import { Pause, Play } from 'lucide-react';

interface StreamPauseButtonProps {
    isPaused: boolean;
    onToggle: (paused: boolean) => void;
    className?: string;
    size?: 'sm' | 'md';
}

/**
 * Botón reutilizable para pausar/reanudar streams en tiempo real
 * Usado en SEC Filings, Benzinga News, etc.
 */
export function StreamPauseButton({
    isPaused,
    onToggle,
    className = '',
    size = 'sm'
}: StreamPauseButtonProps) {
    const handleClick = useCallback(() => {
        onToggle(!isPaused);
    }, [isPaused, onToggle]);

    const sizeClasses = size === 'sm'
        ? 'px-2 py-0.5 text-xs gap-1'
        : 'px-3 py-1 text-sm gap-1.5';

    const iconSize = size === 'sm' ? 'w-3 h-3' : 'w-4 h-4';

    return (
        <button
            onClick={handleClick}
            className={`
                flex items-center font-medium rounded transition-colors
                ${isPaused
                    ? 'bg-emerald-600 hover:bg-emerald-700 text-white'
                    : 'bg-amber-600 hover:bg-amber-700 text-white'
                }
                ${sizeClasses}
                ${className}
            `}
            title={isPaused ? 'Resume stream' : 'Pause stream'}
        >
            {isPaused ? (
                <>
                    <Play className={iconSize} />
                    <span>Play</span>
                </>
            ) : (
                <>
                    <Pause className={iconSize} />
                    <span>Pause</span>
                </>
            )}
        </button>
    );
}

