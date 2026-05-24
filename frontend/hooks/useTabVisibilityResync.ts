/**
 * Hook centralizado para reaccionar al volver de una pestaña inactiva.
 *
 * Cuando el usuario regresa a una pestaña que estuvo en background, los datos
 * pueden estar desactualizados (snapshots stale, eventos perdidos por throttling
 * del navegador, cambios de sesión no procesados). Este hook ejecuta el callback
 * provisto cuando `document.visibilityState` pasa a `visible`, permitiendo a
 * cada componente pedir el refresh que necesite (resync de lista, re-suscripción
 * a eventos, etc.).
 *
 * Reemplaza copias ad-hoc del `visibilitychange` en componentes individuales.
 */

import { useEffect, useRef } from 'react';

export function useTabVisibilityResync(
  onVisible: () => void,
  enabled: boolean = true,
): void {
  // Capturamos el callback en una ref para que el listener no se re-monte en
  // cada render (evita perder eventos durante transiciones rápidas de pestaña).
  const callbackRef = useRef(onVisible);
  callbackRef.current = onVisible;

  useEffect(() => {
    if (!enabled) return;

    const handler = () => {
      if (!document.hidden) {
        callbackRef.current();
      }
    };

    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, [enabled]);
}
