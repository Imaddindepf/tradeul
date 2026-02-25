'use client';

import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useFloatingWindow, type LinkGroup } from '@/contexts/FloatingWindowContext';

const LINK_GROUPS: { value: LinkGroup; color: string; label: string }[] = [
  { value: null,     color: '#94A3B8', label: 'None' },
  { value: 'red',    color: '#EF4444', label: 'Red' },
  { value: 'green',  color: '#22C55E', label: 'Green' },
  { value: 'blue',   color: '#3B82F6', label: 'Blue' },
  { value: 'yellow', color: '#EAB308', label: 'Yellow' },
];

export const LINK_GROUP_COLORS: Record<string, string> = {
  red: '#EF4444',
  green: '#22C55E',
  blue: '#3B82F6',
  yellow: '#EAB308',
};

/** Chain link SVG icon */
function ChainIcon({ color, size = 12 }: { color: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M6.5 8.5h3M9.5 6H11a2.5 2.5 0 0 1 0 5H9.5M6.5 11H5a2.5 2.5 0 0 1 0-5h1.5"
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

interface LinkGroupSelectorProps {
  windowId: string;
  currentLinkGroup: LinkGroup;
}

export function LinkGroupSelector({ windowId, currentLinkGroup }: LinkGroupSelectorProps) {
  const { setWindowLinkGroup } = useFloatingWindow();
  const [isOpen, setIsOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [dropdownPos, setDropdownPos] = useState({ top: 0, left: 0 });

  const currentColor = LINK_GROUPS.find(g => g.value === currentLinkGroup)?.color ?? '#94A3B8';

  // Position dropdown when opening
  useEffect(() => {
    if (!isOpen || !buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    setDropdownPos({
      top: rect.bottom + 2,
      left: rect.right - 100, // align right edge of dropdown with button
    });
  }, [isOpen]);

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        buttonRef.current && !buttonRef.current.contains(e.target as Node) &&
        dropdownRef.current && !dropdownRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const dropdown = isOpen
    ? createPortal(
        <div
          ref={dropdownRef}
          className="fixed bg-white border border-slate-200 rounded-lg shadow-xl p-1 min-w-[100px]"
          style={{ top: dropdownPos.top, left: dropdownPos.left, zIndex: 99999 }}
        >
          {LINK_GROUPS.map(group => (
            <button
              key={group.label}
              onMouseDown={e => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                setWindowLinkGroup(windowId, group.value);
                setIsOpen(false);
              }}
              className={`flex items-center gap-2 w-full px-2 py-1 rounded text-[11px] hover:bg-slate-100 transition-colors ${
                currentLinkGroup === group.value ? 'bg-slate-50 font-semibold' : ''
              }`}
            >
              <ChainIcon color={group.color} size={11} />
              <span className="text-slate-600">{group.label}</span>
            </button>
          ))}
        </div>,
        document.body
      )
    : null;

  return (
    <>
      <button
        ref={buttonRef}
        onMouseDown={e => e.stopPropagation()}
        onClick={e => { e.stopPropagation(); setIsOpen(!isOpen); }}
        className="p-0.5 rounded hover:bg-slate-200/60 transition-colors flex items-center"
        title={`Link: ${currentLinkGroup ?? 'None'}`}
      >
        <ChainIcon color={currentColor} size={13} />
      </button>
      {dropdown}
    </>
  );
}
