'use client';

import { HelpCircle, AlertTriangle } from 'lucide-react';
import { Tooltip, type TooltipPlacement } from '@/components/chart/Tooltip';

/**
 * Small "?" help bubble (or amber warning bubble). Shows a wrapped,
 * viewport-aware tooltip on hover/focus. Renders nothing when there is no
 * content, so it's safe to use unconditionally.
 */
export function InfoTooltip({
  content,
  placement = 'top',
  size = 12,
  className,
  variant = 'info',
}: {
  content: React.ReactNode;
  placement?: TooltipPlacement;
  size?: number;
  className?: string;
  variant?: 'info' | 'warn';
}) {
  if (!content) return null;
  const isWarn = variant === 'warn';
  const Icon = isWarn ? AlertTriangle : HelpCircle;
  const color = isWarn
    ? 'text-amber-500 hover:text-amber-400 focus:text-amber-400'
    : 'text-muted-fg/40 hover:text-muted-fg focus:text-muted-fg';
  return (
    <Tooltip content={content} placement={placement} maxWidth={280} delay={120}>
      <span
        tabIndex={0}
        role="img"
        aria-label={isWarn ? 'Warning' : 'More information'}
        className={`inline-flex items-center justify-center cursor-help outline-none flex-shrink-0 ${color} ${className ?? ''}`}
      >
        <Icon style={{ width: size, height: size }} />
      </span>
    </Tooltip>
  );
}
