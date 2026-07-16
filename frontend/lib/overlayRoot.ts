/**
 * Raíz para overlays portaleados (popovers, tooltips, menús).
 *
 * Normalmente es document.body, PERO cuando hay un elemento en pantalla
 * completa el navegador solo pinta el subárbol de ese elemento: cualquier
 * portal a body se vuelve invisible (el popover "se abre" pero no se ve ni
 * recibe clicks). Portalear al fullscreenElement mantiene los overlays
 * visibles dentro y fuera del modo pantalla completa.
 *
 * Llamar en render/evento (client-only), nunca en módulo-scope SSR.
 */
export function getOverlayRoot(): HTMLElement {
    return (document.fullscreenElement as HTMLElement | null) ?? document.body;
}
