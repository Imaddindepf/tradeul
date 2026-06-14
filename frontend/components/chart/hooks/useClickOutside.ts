'use client';

import { useEffect, type RefObject } from 'react';

/**
 * Dismiss-on-outside-interaction for floating chart UI (dialogs, popovers).
 *
 * Why a shared hook: the chart had several ad-hoc copies of this pattern, and
 * the ones that mattered most (the drawing style dialog, settings dialog) had
 * none at all — so clicking the chart or another panel left them stuck open.
 * One implementation now, used everywhere a floating layer should close when
 * you interact elsewhere — matching TradingView's feel.
 *
 *  - Listens on `pointerdown` (capture) so dismissal fires at the same moment a
 *    chart pan/drag would begin, and before inner handlers can stopPropagation.
 *  - The lightweight-charts canvas does not swallow document events, so a click
 *    on the chart bubbles up and dismisses the layer.
 *  - Escape also dismisses (toggle via `escape`).
 *  - Attachment is deferred one frame so the same click/double-click that
 *    opened the layer can't immediately close it again.
 */
export function useClickOutside(
    ref: RefObject<HTMLElement | null>,
    onDismiss: () => void,
    options: { enabled?: boolean; escape?: boolean } = {},
): void {
    const { enabled = true, escape = true } = options;

    useEffect(() => {
        if (!enabled) return;

        let armed = false;
        const raf = requestAnimationFrame(() => { armed = true; });

        const onPointerDown = (e: PointerEvent) => {
            if (!armed) return;
            const el = ref.current;
            if (el && !el.contains(e.target as Node)) onDismiss();
        };
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onDismiss();
        };

        document.addEventListener('pointerdown', onPointerDown, true);
        if (escape) document.addEventListener('keydown', onKey);

        return () => {
            cancelAnimationFrame(raf);
            document.removeEventListener('pointerdown', onPointerDown, true);
            if (escape) document.removeEventListener('keydown', onKey);
        };
    }, [ref, onDismiss, enabled, escape]);
}
