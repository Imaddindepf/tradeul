'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export type TooltipPlacement = 'top' | 'bottom' | 'left' | 'right';

interface TooltipProps {
    /** Tooltip text content. If empty/null, tooltip is disabled. */
    content: React.ReactNode;
    /** Optional keyboard shortcut shown in muted text after the content. */
    shortcut?: string;
    /** Preferred placement. Falls back automatically near viewport edges. */
    placement?: TooltipPlacement;
    /** Delay in ms before showing on hover. Default 250ms. */
    delay?: number;
    /** Optional className passed to the wrapper span. */
    className?: string;
    children: React.ReactElement;
}

const VIEWPORT_PADDING = 8;
const ARROW_SIZE = 4;

function resolvePlacement(
    preferred: TooltipPlacement,
    triggerRect: DOMRect,
    tooltipRect: { width: number; height: number },
): TooltipPlacement {
    const { innerWidth: vw, innerHeight: vh } = window;
    const fits = {
        top: triggerRect.top - tooltipRect.height - ARROW_SIZE >= VIEWPORT_PADDING,
        bottom: triggerRect.bottom + tooltipRect.height + ARROW_SIZE <= vh - VIEWPORT_PADDING,
        left: triggerRect.left - tooltipRect.width - ARROW_SIZE >= VIEWPORT_PADDING,
        right: triggerRect.right + tooltipRect.width + ARROW_SIZE <= vw - VIEWPORT_PADDING,
    };
    if (fits[preferred]) return preferred;
    const fallbackOrder: TooltipPlacement[] =
        preferred === 'top' || preferred === 'bottom'
            ? ['bottom', 'top', 'right', 'left']
            : ['right', 'left', 'bottom', 'top'];
    for (const p of fallbackOrder) if (fits[p]) return p;
    return preferred;
}

function computeCoords(
    placement: TooltipPlacement,
    triggerRect: DOMRect,
    tooltipRect: { width: number; height: number },
): { top: number; left: number } {
    let top = 0;
    let left = 0;
    switch (placement) {
        case 'top':
            top = triggerRect.top - tooltipRect.height - ARROW_SIZE;
            left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
            break;
        case 'bottom':
            top = triggerRect.bottom + ARROW_SIZE;
            left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
            break;
        case 'left':
            top = triggerRect.top + triggerRect.height / 2 - tooltipRect.height / 2;
            left = triggerRect.left - tooltipRect.width - ARROW_SIZE;
            break;
        case 'right':
            top = triggerRect.top + triggerRect.height / 2 - tooltipRect.height / 2;
            left = triggerRect.right + ARROW_SIZE;
            break;
    }
    const { innerWidth: vw, innerHeight: vh } = window;
    left = Math.max(VIEWPORT_PADDING, Math.min(left, vw - tooltipRect.width - VIEWPORT_PADDING));
    top = Math.max(VIEWPORT_PADDING, Math.min(top, vh - tooltipRect.height - VIEWPORT_PADDING));
    return { top, left };
}

export function Tooltip({
    content,
    shortcut,
    placement = 'bottom',
    delay = 250,
    className,
    children,
}: TooltipProps) {
    const id = useId();
    const triggerRef = useRef<HTMLSpanElement>(null);
    const tooltipRef = useRef<HTMLDivElement>(null);
    const timerRef = useRef<number | null>(null);
    const [visible, setVisible] = useState(false);
    const [resolvedPlacement, setResolvedPlacement] = useState<TooltipPlacement>(placement);
    const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

    const disabled = !content;

    const open = () => {
        if (disabled) return;
        if (timerRef.current) window.clearTimeout(timerRef.current);
        timerRef.current = window.setTimeout(() => setVisible(true), delay);
    };

    const close = () => {
        if (timerRef.current) {
            window.clearTimeout(timerRef.current);
            timerRef.current = null;
        }
        setVisible(false);
    };

    useEffect(() => () => {
        if (timerRef.current) window.clearTimeout(timerRef.current);
    }, []);

    useEffect(() => {
        if (!visible) return;
        const trigger = triggerRef.current;
        const tooltip = tooltipRef.current;
        if (!trigger || !tooltip) return;
        const triggerRect = trigger.getBoundingClientRect();
        const tooltipRect = { width: tooltip.offsetWidth, height: tooltip.offsetHeight };
        const resolved = resolvePlacement(placement, triggerRect, tooltipRect);
        setResolvedPlacement(resolved);
        setCoords(computeCoords(resolved, triggerRect, tooltipRect));
    }, [visible, placement, content]);

    useEffect(() => {
        if (!visible) return;
        const onScroll = () => close();
        window.addEventListener('scroll', onScroll, true);
        window.addEventListener('resize', onScroll);
        return () => {
            window.removeEventListener('scroll', onScroll, true);
            window.removeEventListener('resize', onScroll);
        };
    }, [visible]);

    return (
        <>
            <span
                ref={triggerRef}
                className={className}
                onMouseEnter={open}
                onMouseLeave={close}
                onFocus={open}
                onBlur={close}
                aria-describedby={visible ? id : undefined}
            >
                {children}
            </span>
            {visible && typeof document !== 'undefined' && createPortal(
                <div
                    id={id}
                    ref={tooltipRef}
                    role="tooltip"
                    data-placement={resolvedPlacement}
                    style={{
                        position: 'fixed',
                        top: coords.top,
                        left: coords.left,
                        zIndex: 9999,
                        pointerEvents: 'none',
                    }}
                    className="px-2 py-1 rounded text-[10.5px] font-medium leading-tight whitespace-nowrap bg-[color:var(--color-fg)] text-[color:var(--color-bg)] shadow-lg border border-[color:var(--color-border)]"
                >
                    <span>{content}</span>
                    {shortcut && (
                        <span className="ml-2 opacity-60 font-mono text-[9.5px]">{shortcut}</span>
                    )}
                </div>,
                document.body,
            )}
        </>
    );
}
