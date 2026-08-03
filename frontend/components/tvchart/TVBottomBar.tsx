'use client';

/**
 * TVBottomBar — la barra inferior de la ventana TC, bajo la rejilla de celdas.
 * Cierra la L igual que en tradingview.com:
 *
 *   ┌──────────────────────────────────────────┐
 *   │  TVToolbar                               │
 *   ├──────┬───────────────────────────────────┤
 *   │ Draw │  TVLayoutGrid                     │
 *   │ Bar  │                                   │
 *   ├──────┴───────────────────────────────────┤
 *   │  TVBottomBar                        ⤢    │  ← esto
 *   └──────────────────────────────────────────┘
 *
 * La barra de TradingView lleva, de izquierda a derecha: pestañas de rango,
 * "ir a fecha", separador, reloj/zona horaria, sesión (RTH/ETH), separador y,
 * pegado al borde derecho, el maximizar. Aquí solo está ese último control;
 * la mitad izquierda queda como hueco para que los rangos entren después sin
 * mover nada de lo que ya funciona.
 */

import { useTranslation } from 'react-i18next';

/*
  Los dos iconos oficiales del botón `[data-name="layoutFullscreen"]` de
  TradingView: caja de 18x18, un solo path relleno, sin trazo. Van aquí y no
  en `tvIcons.ts` porque ese fichero está generado automáticamente desde los
  bundles de la Charting Library y lleva un "no editar a mano".

  TradingView intercambia el path entre estados (flechas fuera → flechas
  dentro); su gemelo por chart mantiene un glifo e invierte el fondo del
  botón. Seguimos el intercambio: se lee solo, sin depender de una pastilla.
*/
const MAXIMIZE_PATH = 'M15 8V3h-5V2h6v6h-1ZM3 10v5h5v1H2v-6h1Z';
const RESTORE_PATH = 'M11 2v5h5v1h-6V2h1ZM7 16v-5H2v-1h6v6H7Z';

/** Texto bilingüe, mismo patrón que TVToolbar. */
interface Bi {
    en: string;
    es: string;
}
const bi = (en: string, es: string): Bi => ({ en, es });

interface TVBottomBarProps {
    /** Nº de celdas del layout actual. */
    cellCount: number;
    /** Si hay una celda maximizada ahora mismo. */
    maximized: boolean;
    /** Alterna el maximizado sobre la celda enfocada. */
    onToggleMaximize: () => void;
}

export function TVBottomBar({
    cellCount,
    maximized,
    onToggleMaximize,
}: TVBottomBarProps) {
    const { i18n } = useTranslation();
    const lang: keyof Bi = i18n.language?.toLowerCase().startsWith('es') ? 'es' : 'en';
    const L = (b: Bi) => b[lang];

    /*
      TradingView condiciona este control a que haya más de un chart: con uno
      solo no hay nada que maximizar y el botón ni se renderiza (comprobado:
      el nodo no está en el DOM, y su `requestFullscreen` interno es un no-op
      tras la misma condición). Hacemos lo mismo en vez de pintarlo desactivado.
    */
    const canMaximize = cellCount > 1;

    const title = maximized
        ? L(bi('Restore chart', 'Restaurar chart'))
        : L(bi('Maximize chart', 'Maximizar chart'));

    /*
      `pr-5` = los 20px del tirador de redimensionar de la ventana flotante
      (`absolute bottom-0 right-0 w-5 h-5 ... z-[100]` en FloatingWindowBase),
      que se pinta ENCIMA del contenido. Sin ese hueco el botón cae justo
      debajo y el ratón se lleva el resize en vez del clic. En tradingview.com
      el maximizar va pegado al borde porque allí no hay ventana que redimen-
      sionar; aquí sí, y el tirador manda.
    */
    return (
        <div className="flex h-7 flex-shrink-0 items-center border-t border-black/10 pl-1 pr-5 dark:border-white/10">
            {/* Hueco izquierdo — aquí entran los rangos y el "ir a fecha". */}

            <div className="flex-1" />

            {canMaximize && (
                <button
                    title={title}
                    aria-label={title}
                    aria-pressed={maximized}
                    onClick={onToggleMaximize}
                    className="flex h-6 w-6 items-center justify-center rounded hover:bg-black/10 dark:hover:bg-white/10"
                >
                    <svg
                        width="18"
                        height="18"
                        viewBox="0 0 18 18"
                        className="block"
                    >
                        <path
                            fill="currentColor"
                            d={maximized ? RESTORE_PATH : MAXIMIZE_PATH}
                        />
                    </svg>
                </button>
            )}
        </div>
    );
}
