'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, X } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import i18n from '@/lib/i18n';

const POLL_INTERVAL_MS = 5 * 60 * 1000; // 5 min
const FOCUS_CHECK_THROTTLE_MS = 60 * 1000; // máx. 1 check/min al volver a la pestaña

/**
 * UpdateNotifier
 *
 * Detecta despliegues nuevos en producción comparando el BUILD_ID con el que
 * se cargó la página contra el que sirve /api/version, y muestra una franja
 * estilo Chrome anclada justo debajo del navbar (top-10 = altura del navbar).
 * No fuerza la recarga: el usuario puede estar en mitad de una operación.
 *
 * Complementa a ChunkLoadErrorHandler (reactivo, recarga cuando un chunk ya no
 * existe); esto es proactivo: avisa antes de que algo falle.
 */
export function UpdateNotifier() {
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const baselineRef = useRef<string | null>(null);
  const lastCheckRef = useRef(0);

  const checkVersion = useCallback(async () => {
    lastCheckRef.current = Date.now();
    try {
      const res = await fetch('/api/version', { cache: 'no-store' });
      if (!res.ok) return;
      const { buildId } = await res.json();
      if (!buildId || buildId === 'dev') return;
      if (baselineRef.current === null) {
        baselineRef.current = buildId;
      } else if (buildId !== baselineRef.current) {
        setUpdateAvailable(true);
      }
    } catch {
      // Sin red o deploy en curso: lo reintentará el siguiente ciclo
    }
  }, []);

  useEffect(() => {
    // ?preview-update=1 fuerza el banner para revisar el diseño sin deploy
    if (new URLSearchParams(window.location.search).has('preview-update')) {
      setUpdateAvailable(true);
    }
    checkVersion();
    const interval = setInterval(checkVersion, POLL_INTERVAL_MS);

    const onVisible = () => {
      if (
        document.visibilityState === 'visible' &&
        Date.now() - lastCheckRef.current > FOCUS_CHECK_THROTTLE_MS
      ) {
        checkVersion();
      }
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [checkVersion]);

  if (!updateAvailable || dismissed) return null;

  const es = (i18n.language || 'en').startsWith('es');

  return (
    <div
      role="alert"
      className="fixed top-10 left-0 right-0 animate-slide-down border-b border-border bg-surface shadow-lg shadow-black/10"
      // Bajo NAVBAR_POPOVER (9000) para no tapar los popovers del navbar,
      // pero sobre paneles y ventanas flotantes (max 8500)
      style={{ zIndex: Z_INDEX.NAVBAR_POPOVER - 10 }}
    >
      {/* Línea de acento superior, sello visual Tradeul */}
      <div className="h-[2px] w-full bg-gradient-to-r from-transparent via-primary to-transparent" />

      <div className="relative flex h-9 items-center justify-center gap-3 px-3">
        {/* Punto de estado animado */}
        <span className="relative flex h-1.5 w-1.5 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
        </span>

        <span className="text-xs font-medium text-foreground">
          {es ? 'Nueva versión de Tradeul disponible' : 'A new version of Tradeul is available'}
        </span>
        <span className="hidden text-xs text-muted-fg sm:inline">
          {es ? 'Recarga para obtener las últimas mejoras' : 'Reload to get the latest improvements'}
        </span>

        <button
          onClick={() => window.location.reload()}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1 text-xs font-semibold text-white transition-colors hover:bg-primary-hover"
        >
          <RefreshCw className="h-3 w-3" />
          {es ? 'Recargar' : 'Reload'}
        </button>
        <button
          onClick={() => setDismissed(true)}
          className="rounded-md px-2 py-1 text-xs font-medium text-muted-fg transition-colors hover:bg-surface-hover hover:text-foreground"
        >
          {es ? 'Más tarde' : 'Later'}
        </button>

        {/* Cierre a la derecha, estilo barra de aviso */}
        <button
          onClick={() => setDismissed(true)}
          aria-label={es ? 'Cerrar' : 'Dismiss'}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-fg transition-colors hover:bg-surface-hover hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
