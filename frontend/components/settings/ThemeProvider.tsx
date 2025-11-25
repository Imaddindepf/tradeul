/**
 * Theme Provider
 * 
 * Aplica las preferencias de usuario (colores, fuentes) como CSS variables
 * Se actualiza automáticamente cuando cambian las preferencias
 * 
 * IMPORTANTE: 
 * - Hidrata el store de Zustand y aplica estilos solo en cliente
 * - Sincroniza preferencias con el backend (PostgreSQL) via Clerk
 */

'use client';

import { useEffect, useState } from 'react';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { useClerkSync } from '@/hooks/useClerkSync';

interface ThemeProviderProps {
  children: React.ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [hydrated, setHydrated] = useState(false);
  const colors = useUserPreferencesStore((state) => state.colors);
  const theme = useUserPreferencesStore((state) => state.theme);

  // Sincronización con backend (PostgreSQL)
  // Este hook se encarga de:
  // - Cargar preferencias del servidor al login
  // - Guardar cambios automáticamente (debounced)
  useClerkSync();

  // Hidratar el store de Zustand en el cliente
  useEffect(() => {
    // Rehydrate the persisted store
    useUserPreferencesStore.persist.rehydrate();
    setHydrated(true);
  }, []);

  // Aplicar CSS variables cuando cambian las preferencias (solo después de hidratación)
  useEffect(() => {
    if (!hydrated) return;

    const root = document.documentElement;

    // Colores
    root.style.setProperty('--color-tick-up', colors.tickUp);
    root.style.setProperty('--color-tick-down', colors.tickDown);
    root.style.setProperty('--color-background', colors.background);
    root.style.setProperty('--color-primary', colors.primary);

    // Fuente mono
    const fontMap: Record<string, string> = {
      'oxygen-mono': 'var(--font-oxygen-mono)',
      'ibm-plex-mono': 'var(--font-ibm-plex-mono)',
      'jetbrains-mono': 'var(--font-jetbrains-mono)',
      'fira-code': 'var(--font-fira-code)',
    };
    root.style.setProperty('--font-mono-selected', fontMap[theme.font] || fontMap['jetbrains-mono']);

    // Aplicar color de fondo al body
    document.body.style.backgroundColor = colors.background;

  }, [hydrated, colors, theme]);

  return <>{children}</>;
}

export default ThemeProvider;
