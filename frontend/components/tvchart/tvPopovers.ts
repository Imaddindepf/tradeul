'use client';

/**
 * Coordinación de popovers de la ventana TVC (menú de diseños, picker de
 * layouts, dropdowns de la toolbar, flyouts de la barra de dibujo) — flujo
 * calcado de tradingview.com:
 *   • SOLO UNO abierto a la vez: al abrirse uno se anuncia por un CustomEvent
 *     y el resto se cierra.
 *   • Clic fuera SIEMPRE cierra: listener de mousedown en fase de CAPTURA
 *     (los botones de la toolbar hacen stopPropagation en mousedown por la
 *     FloatingWindow y en burbuja el cierre nunca llegaba a ejecutarse).
 *   • Clic dentro de un gráfico también cierra: los mousedown de los iframes
 *     no llegan al documento padre, así que el contenedor llama a
 *     closeAllTVPopovers() desde el mouse_down que reporta la Charting Library.
 *   • Escape cierra (opcional: la barra de dibujo tiene su propio flujo ESC).
 */

import { useEffect, useRef } from 'react';

const OPEN_EVENT = 'tvchart:popover-open';

let seq = 0;

/** Cerrar todos los popovers TVC abiertos (clic en iframe, ESC de celda…). */
export function closeAllTVPopovers() {
    window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: null }));
}

/**
 * Registra un popover en el coordinador mientras `isOpen` sea true.
 * `contains` debe cubrir el panel Y su botón/ancla (así el mousedown del
 * propio trigger no cierra antes de que el click haga el toggle).
 */
export function useTVPopover(
    isOpen: boolean,
    onClose: () => void,
    contains: (target: Node) => boolean,
    { escape = true }: { escape?: boolean } = {},
) {
    const idRef = useRef(0);
    if (idRef.current === 0) idRef.current = ++seq;
    const onCloseRef = useRef(onClose);
    onCloseRef.current = onClose;
    const containsRef = useRef(contains);
    containsRef.current = contains;

    useEffect(() => {
        if (!isOpen) return;
        // Anunciar la apertura ANTES de escuchar: cierra al resto sin cerrarse.
        window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: idRef.current }));

        const onAnnounce = (e: Event) => {
            if ((e as CustomEvent).detail !== idRef.current) onCloseRef.current();
        };
        const onMouseDown = (e: MouseEvent) => {
            if (!containsRef.current(e.target as Node)) onCloseRef.current();
        };
        const onKey = (e: KeyboardEvent) => {
            if (e.key !== 'Escape') return;
            // Consumir el ESC: cierra este popover sin disparar además el
            // flujo ESC de la barra de dibujo (volver al cursor).
            e.stopPropagation();
            onCloseRef.current();
        };
        window.addEventListener(OPEN_EVENT, onAnnounce);
        window.addEventListener('mousedown', onMouseDown, true);
        if (escape) window.addEventListener('keydown', onKey, true);
        return () => {
            window.removeEventListener(OPEN_EVENT, onAnnounce);
            window.removeEventListener('mousedown', onMouseDown, true);
            if (escape) window.removeEventListener('keydown', onKey, true);
        };
    }, [isOpen, escape]);
}
