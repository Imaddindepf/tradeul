'use client';

/**
 * TradeulLogo — wordmark "Tradeul" para el chart TVC, en el mismo sitio que
 * el logo de TradingView que retiramos (featuresets widget_logo /
 * library_branding): esquina inferior izquierda del pane.
 *
 * Solo wordmark (sin glifo), fuerte y casi blanco sobre tema oscuro; el color
 * se decide por la luminancia de --color-bg para seguir siendo legible en
 * tema claro. La v31 no ofrece logo propio, así que va por overlay DOM
 * (decorativo: pointer-events none) y se ESTAMPA también en los PNG
 * descargados (cámara de celda y de layout) vía drawTradeulLogoOnCanvas.
 */

/** viewBox 0 0 76 20 → relación de aspecto del wordmark. */
export const TRADEUL_LOGO_RATIO = 76 / 20;

/** Color según tema: casi blanco en oscuro, gris carbón en claro. */
export function tradeulLogoColor(): string {
    const dark = '#eef1f5';
    if (typeof window === 'undefined') return dark;
    const bg = getComputedStyle(document.documentElement).getPropertyValue('--color-bg').trim();
    const m = /^#?([0-9a-f]{6})$/i.exec(bg.replace('#', ''));
    if (!m) return dark;
    const n = parseInt(m[1], 16);
    const luminance =
        (0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255;
    return luminance < 0.5 ? dark : '#3f434c';
}

/** SVG serializado con color explícito (para overlay, data-URL y canvas). */
export function tradeulLogoSvg(color: string): string {
    return (
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 76 20" width="76" height="20">` +
        `<text x="0" y="15.5" font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" ` +
        `font-size="17" font-weight="800" letter-spacing="0.4" fill="${color}">Tradeul</text>` +
        `</svg>`
    );
}

/**
 * Inyecta el wordmark DENTRO del documento del iframe de la CL (same-origin),
 * en el mismo emplazamiento y capa que el logo de TradingView que ocultamos:
 * bottom-left sobre el eje de tiempo, con z-index bajo para que los paneles
 * de la librería (búsqueda de símbolo, indicadores, menús…) queden POR
 * ENCIMA. Un overlay en el documento padre siempre taparía esos diálogos —
 * por eso va dentro. Idempotente por id; el iframe muere con la celda.
 */
export function injectTradeulLogo(doc: Document | null | undefined): void {
    try {
        if (!doc || !doc.body || doc.getElementById('tradeul-logo')) return;
        const el = doc.createElement('div');
        el.id = 'tradeul-logo';
        el.setAttribute('aria-hidden', 'true');
        el.style.cssText =
            'position:absolute;left:8px;bottom:34px;z-index:2;pointer-events:none;' +
            'user-select:none;opacity:.85;line-height:0;';
        el.innerHTML = tradeulLogoSvg(tradeulLogoColor()).replace(
            'width="76" height="20"',
            'width="91" height="24"',
        );
        doc.body.appendChild(el);
    } catch { /* iframe inaccesible */ }
}

const logoImgCache = new Map<string, Promise<HTMLImageElement>>();

function logoImage(color: string): Promise<HTMLImageElement> {
    let p = logoImgCache.get(color);
    if (!p) {
        p = new Promise<HTMLImageElement>((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => {
                logoImgCache.delete(color);
                reject(new Error('logo svg'));
            };
            img.src = `data:image/svg+xml;utf8,${encodeURIComponent(tradeulLogoSvg(color))}`;
        });
        logoImgCache.set(color, p);
    }
    return p;
}

/**
 * Estampa el wordmark en un canvas de captura (PNG de descarga). Coordenadas
 * en píxeles del canvas (aplicar devicePixelRatio fuera). Color por tema si
 * no se indica. Nunca lanza: una captura sin logo es mejor que una rota.
 */
export async function drawTradeulLogoOnCanvas(
    ctx: CanvasRenderingContext2D,
    opts: { x: number; y: number; height: number; color?: string; opacity?: number },
): Promise<void> {
    try {
        const img = await logoImage(opts.color ?? tradeulLogoColor());
        ctx.save();
        ctx.globalAlpha = opts.opacity ?? 0.95;
        ctx.drawImage(img, opts.x, opts.y, opts.height * TRADEUL_LOGO_RATIO, opts.height);
        ctx.restore();
    } catch { /* sin logo */ }
}
