'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import i18n from '@/lib/i18n';

const POLL_INTERVAL_MS = 5 * 60 * 1000; // 5 min
const FOCUS_CHECK_THROTTLE_MS = 60 * 1000; // máx. 1 check/min al volver a la pestaña

/**
 * UpdateNotifier
 *
 * Detecta despliegues nuevos en producción comparando el BUILD_ID con el que
 * se cargó la página contra el que sirve /api/version, y muestra un aviso
 * recomendando recargar. No fuerza la recarga: el usuario puede estar en mitad
 * de una operación.
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
      className="fixed bottom-4 right-4 z-[9999] flex items-center gap-3 rounded-lg border border-blue-500/30 bg-[#0f172a] px-4 py-3 shadow-xl shadow-black/40"
    >
      <span className="relative flex h-2 w-2 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-500" />
      </span>
      <div className="text-sm text-slate-200">
        {es ? 'Nueva versión de Tradeul disponible' : 'A new version of Tradeul is available'}
      </div>
      <button
        onClick={() => window.location.reload()}
        className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
      >
        {es ? 'Recargar' : 'Reload'}
      </button>
      <button
        onClick={() => setDismissed(true)}
        aria-label={es ? 'Cerrar' : 'Dismiss'}
        className="rounded-md px-2 py-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200"
      >
        {es ? 'Más tarde' : 'Later'}
      </button>
    </div>
  );
}
