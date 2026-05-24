'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  useUserPreferencesStore,
  selectPanelLocks,
  type PanelLocks,
} from '@/stores/useUserPreferencesStore';
import { Z_INDEX } from '@/lib/z-index';

interface LockPopoverProps {
  /** Anchor element of the lock icon — popover renders above it */
  anchorEl: HTMLElement | null;
  isOpen: boolean;
  onClose: () => void;
}

const LOCK_OPTIONS: Array<{ key: keyof PanelLocks; label: string }> = [
  { key: 'movement', label: 'Lock Movement' },
  { key: 'open', label: 'Lock Open' },
  { key: 'close', label: 'Lock Close' },
];

/**
 * Compact popover with three toggles that sits directly above the
 * lock icon in the dashboard toolbar. Closes on outside-click and Escape.
 */
export function LockPopover({ anchorEl, isOpen, onClose }: LockPopoverProps) {
  const panelLocks = useUserPreferencesStore(selectPanelLocks);
  const togglePanelLock = useUserPreferencesStore((s) => s.togglePanelLock);

  const popoverRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ top: 0, right: 0 });
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!isOpen || !anchorEl) return;
    const updatePosition = () => {
      const rect = anchorEl.getBoundingClientRect();
      setPosition({
        top: rect.top - 8,
        right: window.innerWidth - rect.right,
      });
    };
    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [isOpen, anchorEl]);

  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (e: MouseEvent) => {
      if (popoverRef.current?.contains(e.target as Node)) return;
      if (anchorEl?.contains(e.target as Node)) return;
      onClose();
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKey);
    };
  }, [isOpen, anchorEl, onClose]);

  if (!isOpen || !mounted) return null;

  const node = (
    <div
      ref={popoverRef}
      role="dialog"
      aria-label="Panel lock options"
      style={{
        position: 'fixed',
        top: `${position.top}px`,
        right: `${position.right}px`,
        transform: 'translateY(-100%)',
        zIndex: Z_INDEX.DASHBOARD_OVERLAY,
        fontFamily: 'var(--font-mono-selected)',
      }}
      className="min-w-[200px] rounded-lg border border-border bg-surface shadow-xl p-2 select-none"
      onMouseDown={(e) => e.stopPropagation()}
    >
      <ul className="flex flex-col gap-1">
        {LOCK_OPTIONS.map(({ key, label }) => {
          const checked = Boolean(panelLocks[key]);
          return (
            <li key={key}>
              <button
                type="button"
                onClick={() => togglePanelLock(key)}
                className="w-full flex items-center gap-3 px-2 py-1.5 rounded hover:bg-foreground/5 transition-colors text-left"
              >
                <span
                  className={`relative inline-flex w-8 h-4 rounded-full transition-colors ${
                    checked ? 'bg-primary' : 'bg-foreground/20'
                  }`}
                  aria-checked={checked}
                  role="switch"
                >
                  <span
                    className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform shadow ${
                      checked ? 'translate-x-4' : 'translate-x-0.5'
                    }`}
                  />
                </span>
                <span className="text-xs text-foreground">{label}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );

  return createPortal(node, document.body);
}
